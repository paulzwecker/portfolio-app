"""End-to-end synthetic BKNG quote → canonical price → live native DCF, with no network."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _listing_payload
from test_model_input_migration import add_company_listing, source_workbook

from portfolio_api.current_model_calculation import current_native_model_calculation
from portfolio_api.database_write_target import (
    ACCEPTED_MODEL_PRICE_WRITE_OPERATION,
    _read_live_identity,
    _write_permission_scope,
)
from portfolio_api.domain.models import (
    CorporateAction,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    FxObservation,
    MarketDataBatch,
    PriceObservation,
)
from portfolio_api.external_data import ExternalDataDomain, ProviderQuery, RawProviderRecord
from portfolio_api.market_data_ingestion import (
    CROSSWALK_PATH,
    _accepted_model_price_scope,
    _assert_accepted_model_price_plan,
    apply_provider_import,
    build_provider_import,
)
from portfolio_api.model_input_migration import import_native_model_inputs
from portfolio_api.yahoo_finance import load_yahoo_crosswalk


class FrozenBkngYahoo:
    """Provider fixture: exact real-company identity, synthetic prices, no HTTP calls."""

    def __init__(self, listing_id, payload: bytes, retrieved_at: datetime) -> None:
        self.listing_id = listing_id
        self.payload = payload
        self.retrieved_at = retrieved_at
        self.failures: list[object] = []
        self.bound: dict = {}

    def bind_listing_ids(self, listing_ids: dict) -> None:
        self.bound = dict(listing_ids)

    async def fetch(self, query: ProviderQuery) -> list[RawProviderRecord]:
        assert query.domain == ExternalDataDomain.MARKET_DATA
        assert len(query.subjects) == 1 and query.subjects[0].id == self.listing_id
        return [
            RawProviderRecord(
                domain=query.domain,
                provider_id="YAHOO_FINANCE",
                provider_schema_version="yahoo-chart-v8",
                source_record_id=f"LISTING:{self.listing_id}",
                source_url="https://query1.finance.yahoo.com/v8/finance/chart/BKNG",
                media_type="application/json",
                retrieved_at=self.retrieved_at,
                payload=self.payload,
                payload_sha256=hashlib.sha256(self.payload).hexdigest(),
            )
        ]


def near_current_bkng_payload(now: datetime) -> bytes:
    data = json.loads(_listing_payload(symbol="BKNG"))
    chart = data["chart"]["result"][0]
    target_day = now.date() - timedelta(days=2)
    old_last = datetime(2026, 10, 5, tzinfo=UTC).date()
    offset = (target_day - old_last).days * 86400
    chart["timestamp"] = [int(item) + offset for item in chart["timestamp"]]
    chart["meta"]["regularMarketTime"] = int(chart["meta"]["regularMarketTime"]) + offset
    chart["events"] = {}  # Price-only; no corporate actions may be written.
    return json.dumps(data, separators=(",", ":")).encode()


@pytest.mark.integration
@pytest.mark.source_data
def test_minimum_acl_price_import_recalculates_accepted_bkng_without_revision_write(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    crosswalk = load_yahoo_crosswalk(CROSSWALK_PATH)
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = connection.execute(text("SELECT current_schema()")).scalar_one()
            assert schema.startswith("test_")
            with Session(bind=connection) as owner:
                company = add_company_listing(
                    owner,
                    name="Booking Holdings",
                    reporting_currency="USD",
                    security_name="Booking Holdings common",
                    ticker="BKNG",
                    venue="NASDAQ",
                    currency="USD",
                )
                applied = import_native_model_inputs(
                    owner,
                    source_workbook(),
                    accepted_at=now,
                    apply=True,
                    model_key="P-BKNG",
                )
                assert applied["input_sets_imported"] == 1
                model = owner.scalar(
                    select(FinancialModel).where(FinancialModel.company_id == company.id)
                )
                assert model is not None and model.current_revision_id is not None
                original_revision_id = model.current_revision_id
                old_output = owner.scalar(
                    select(FinancialModelOutput).where(
                        FinancialModelOutput.revision_id == original_revision_id
                    )
                )
                assert old_output is not None and old_output.status == "PARTIAL"
                assert old_output.current_price is None

                exact_company, listing_id, accepted_revision_id, currency, keys = (
                    _accepted_model_price_scope(owner, model.id)
                )
                assert exact_company == company.id
                assert accepted_revision_id == original_revision_id
                assert keys == {("nasdaq", "bkng")} and currency == "USD"
                role = f"price_only_{uuid4().hex[:12]}"
                connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                connection.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
                permissions = _write_permission_scope(
                    ACCEPTED_MODEL_PRICE_WRITE_OPERATION, "ingestion"
                )
                assert permissions is not None
                for table_name, grants in permissions.items():
                    connection.execute(
                        text(
                            f"GRANT {', '.join(sorted(grants))} "
                            f'ON TABLE "{schema}"."{table_name}" TO "{role}"'
                        )
                    )
                owner.flush()
            # All subsequent ingestion SQL actually executes as the scoped role.
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            identity = _read_live_identity(
                connection, "ingestion", required_write_privileges=permissions
            )
            assert not identity.missing_tables and not identity.missing_privileges
            assert _read_live_identity(connection, "ingestion").missing_privileges

            with Session(bind=connection) as writer:
                provider = FrozenBkngYahoo(listing_id, near_current_bkng_payload(now), now)
                report = asyncio.run(
                    build_provider_import(
                        writer,
                        provider=provider,
                        crosswalk=crosswalk,
                        end_date=now.date(),
                        lookback_days=30,
                        scope="listings",
                        listing_keys=keys,
                        company_ids={company.id},
                        fx_pairs=set(),
                        include_listing_ids={listing_id},
                    )
                )
                plans = report.pop("plans")
                _assert_accepted_model_price_plan(report, plans, listing_id, currency, now.date())
                assert len(plans) == 1 and not plans[0]["actions"] and not plans[0]["fx"]
                assert provider.bound == {listing_id: provider.bound[listing_id]}
                result = apply_provider_import(writer, {**report, "plans": plans})
                assert result["status"] == "APPLIED"
                assert result["persistence"]["inserted_totals"]["price_observations"] >= 2
                writer.flush()

            # The proof includes a true privilege boundary. Only the saved
            # canonical price data may change; accepted model state stays immutable.
            connection.execute(text("RESET ROLE"))
            with Session(bind=connection) as read:
                model = read.get(FinancialModel, model.id)
                rev = read.get(FinancialModelRevision, original_revision_id)
                assert model is not None and rev is not None
                current = current_native_model_calculation(
                    read, model, rev, as_of=now.date(), known_at=now + timedelta(minutes=2)
                )
                assert current is not None
                assert current.read.revision_id == original_revision_id
                assert current.read.market_price.status == "AVAILABLE"
                assert current.outputs.current_price is not None
                assert current.outputs.weighted_upside is not None
                assert current.outputs.expected_cash_flow_irr is not None
                accepted = read.scalar(
                    select(FinancialModelOutput).where(
                        FinancialModelOutput.revision_id == original_revision_id
                    )
                )
                assert accepted is not None
                assert accepted.status == "PARTIAL"
                assert accepted.current_price is None
                assert accepted.weighted_upside is None
                assert read.scalar(select(func.count()).select_from(FinancialModelRevision)) == 1
                assert read.scalar(select(func.count()).select_from(MarketDataBatch)) == 1
                assert read.scalar(select(func.count()).select_from(CorporateAction)) == 0
                assert read.scalar(select(func.count()).select_from(FxObservation)) == 0
                assert read.scalar(select(func.count()).select_from(PriceObservation)) >= 2
        finally:
            transaction.rollback()
