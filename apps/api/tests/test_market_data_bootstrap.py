"""Synthetic-provider regression tests for the bounded market-data bootstrap."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.database_write_target import install_database_write_target_guard
from portfolio_api.domain.models import (
    Company,
    CorporateAction,
    CurrentLifecycle,
    ExternalRawPayload,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    LifecycleEvent,
    Listing,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    Portfolio,
    PriceObservation,
    Security,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.market_data_bootstrap import (
    MarketDataBootstrapError,
    _temporal_issues,
    _verify_target,
    _write_private_report,
    execute_market_data_bootstrap,
    prepare_market_data_bootstrap,
    preview_market_data_bootstrap,
    reconcile_market_data_bootstrap,
)
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import (
    ProviderFetchFailure,
    YahooListingCrosswalk,
    YahooListingMapping,
)

START = date(2026, 10, 1)
END = date(2026, 10, 5)
RETRIEVED_AT = datetime(2026, 10, 6, 20, tzinfo=UTC)


def _listing_payload(*, symbol: str = "SYNTH") -> bytes:
    timestamps = [
        int(datetime(2026, 10, 2, 13, 30, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 5, 13, 30, tzinfo=UTC).timestamp()),
    ]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": "USD",
                            "exchangeName": "NMS",
                            "fullExchangeName": "NasdaqGS",
                            "instrumentType": "EQUITY",
                            "exchangeTimezoneName": "America/New_York",
                            "regularMarketPrice": 120.5,
                            "regularMarketTime": int(
                                datetime(2026, 10, 5, 19, 45, tzinfo=UTC).timestamp()
                            ),
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [{"close": [120.125, 121.25], "volume": [1200, 1300]}],
                            "adjclose": [{"adjclose": [119.875, 121.0]}],
                        },
                        "events": {
                            "dividends": {
                                str(int(datetime(2026, 10, 2, 13, 30, tzinfo=UTC).timestamp())): {
                                    "amount": 0.125,
                                }
                            },
                            "splits": {
                                str(int(datetime(2026, 10, 5, 13, 30, tzinfo=UTC).timestamp())): {
                                    "splitRatio": "2:1",
                                }
                            },
                        },
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _fx_payload() -> bytes:
    timestamps = [
        int(datetime(2026, 10, 2, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 5, tzinfo=UTC).timestamp()),
    ]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "EUR=X",
                            "currency": "EUR",
                            "exchangeName": "CCY",
                            "instrumentType": "CURRENCY",
                            "regularMarketPrice": 0.92,
                            "regularMarketTime": int(
                                datetime(2026, 10, 6, 18, tzinfo=UTC).timestamp()
                            ),
                        },
                        "timestamp": timestamps,
                        "indicators": {"quote": [{"close": [0.91, 0.915]}]},
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _empty_payload(domain: ExternalDataDomain) -> bytes:
    symbol = "SYNTH" if domain == ExternalDataDomain.MARKET_DATA else "EUR=X"
    currency = "USD" if domain == ExternalDataDomain.MARKET_DATA else "EUR"
    instrument = "EQUITY" if domain == ExternalDataDomain.MARKET_DATA else "CURRENCY"
    exchange = "NMS" if domain == ExternalDataDomain.MARKET_DATA else "CCY"
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": currency,
                            "exchangeName": exchange,
                            "instrumentType": instrument,
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [],
                        "indicators": {"quote": [{"close": []}]},
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _mapping(company_id: UUID, security_id: UUID, listing_id: UUID) -> YahooListingMapping:
    return YahooListingMapping(
        venue="NASDAQ",
        ticker="SYNTH",
        currency="USD",
        security_type="COMMON_STOCK",
        provider_symbol="SYNTH",
        provider_exchange_code="NMS",
        provider_exchange_name="NasdaqGS",
        provider_instrument_type="EQUITY",
        mapping_basis="SYNTHETIC_TEST_FIXTURE",
        verification_status="VERIFIED",
        canonical_company_id=company_id,
        canonical_security_id=security_id,
        canonical_listing_id=listing_id,
    )


def _crosswalk(mapping: YahooListingMapping) -> tuple[YahooListingCrosswalk, str]:
    crosswalk = YahooListingCrosswalk(
        provider_id="YAHOO_FINANCE",
        provider_schema_version="yahoo-chart-v8",
        verified_at=RETRIEVED_AT,
        mappings=(mapping,),
    )
    digest = hashlib.sha256(crosswalk.model_dump_json().encode()).hexdigest()
    return crosswalk, digest


def _seed_canonical_scope(session: Session) -> tuple[Company, Security, Listing]:
    company_id, security_id, listing_id = uuid4(), uuid4(), uuid4()
    company = Company(id=company_id, name="Synthetic Example Corporation")
    security = Security(
        id=security_id,
        company_id=company_id,
        name="Synthetic Example Common",
        security_type="COMMON_STOCK",
    )
    listing = Listing(
        id=listing_id,
        security_id=security_id,
        venue="NASDAQ",
        ticker="SYNTH",
        currency="USD",
    )
    lifecycle = LifecycleEvent(
        id=uuid4(),
        company_id=company_id,
        sequence=1,
        previous_state=None,
        new_state="PORTFOLIO",
        effective_at=datetime(2026, 10, 1, tzinfo=UTC),
        actor="IMPORT",
        reason="Synthetic integration fixture",
        source="synthetic-test",
    )
    portfolio = Portfolio(id=uuid4(), name="Synthetic Portfolio", base_currency="EUR")
    snapshot = HoldingSnapshot(
        id=uuid4(),
        portfolio_id=portfolio.id,
        effective_at=datetime(2026, 10, 1, tzinfo=UTC),
        actor="IMPORT",
        reason="Synthetic integration fixture",
        source="synthetic-test",
        completeness="COMPLETE",
    )
    session.add(company)
    session.flush()
    session.add(security)
    session.flush()
    session.add(listing)
    session.add(lifecycle)
    session.add(portfolio)
    session.flush()
    session.add(snapshot)
    session.flush()
    session.add(CurrentLifecycle(company_id=company_id, event_id=lifecycle.id))
    session.flush()
    session.info["new_snapshot_ids"] = {snapshot.id}
    try:
        session.add(
            HoldingPosition(
                snapshot_id=snapshot.id,
                listing_id=listing_id,
                quantity=Decimal("2.5"),
            )
        )
        session.flush()
    finally:
        session.info.pop("new_snapshot_ids", None)
    return company, security, listing


class SyntheticProvider:
    def __init__(self, *, mode: str = "valid") -> None:
        self.mode = mode
        self.failures: list[ProviderFetchFailure] = []
        self.calls: list[ProviderQuery] = []
        self.listing_mappings: dict[UUID, YahooListingMapping] = {}

    def bind_listing_ids(self, listing_ids: dict[UUID, YahooListingMapping]) -> None:
        self.listing_mappings = dict(listing_ids)

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        self.calls.append(query)
        self.failures = []
        subject = query.subjects[0]
        if self.mode == "transport_failure":
            key = (
                f"LISTING:{subject.id}"
                if subject.kind == CanonicalSubjectKind.LISTING
                else (f"FX:{subject.base_currency}/{subject.quote_currency}")
            )
            self.failures.append(
                ProviderFetchFailure(
                    source_record_id=key,
                    provider_symbol="SYNTHETIC",
                    message="Synthetic bounded transport failure",
                    code="NETWORK_ERROR",
                    retryable=True,
                )
            )
            return []
        if subject.kind == CanonicalSubjectKind.LISTING:
            listing_id = subject.id
            assert listing_id is not None
            source_record_id = f"LISTING:{listing_id}"
            payload = (
                _empty_payload(query.domain)
                if self.mode == "empty"
                else _listing_payload(symbol="WRONG" if self.mode == "wrong_identity" else "SYNTH")
            )
        else:
            source_record_id = f"FX:{subject.base_currency}/{subject.quote_currency}"
            payload = _empty_payload(query.domain) if self.mode == "empty" else _fx_payload()
        return [
            RawProviderRecord(
                domain=query.domain,
                provider_id="YAHOO_FINANCE",
                provider_schema_version="yahoo-chart-v8",
                source_record_id=source_record_id,
                source_url="https://synthetic.example.invalid/chart",
                media_type="application/json",
                retrieved_at=RETRIEVED_AT,
                payload=payload,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            )
        ]


def _prepare(
    session: Session,
    crosswalk: YahooListingCrosswalk,
    digest: str,
) -> MarketDataBootstrapRun:
    return prepare_market_data_bootstrap(
        session,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        start_date=START,
        end_date=END,
        target_environment="development",
    )


@pytest.mark.integration
def test_bootstrap_preview_is_read_only_and_rejects_duplicate_exact_mappings(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        mapping = _mapping(company.id, security.id, listing.id)
        duplicate = mapping.model_copy()
        crosswalk, _digest = _crosswalk(mapping.model_copy())
        crosswalk = crosswalk.model_copy(update={"mappings": (mapping, duplicate)})
        digest = hashlib.sha256(crosswalk.model_dump_json().encode()).hexdigest()

        preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="development",
        )

        assert preview["status"] == "BLOCKED"
        assert preview["provider_requests"] == 0
        assert preview["database_writes"] == 0
        assert preview["unresolved_listings"][0]["code"] == (
            "VERIFIED_PROVIDER_MAPPING_MISSING_OR_AMBIGUOUS"
        )
        assert session.scalar(select(func.count()).select_from(MarketDataBootstrapRun)) == 0


@pytest.mark.integration
def test_postgres18_market_bootstrap_resumes_and_is_idempotent(
    postgres_engine: Engine,
) -> None:
    from pydantic import SecretStr

    from portfolio_api.database_write_target import verify_database_write_target

    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id
        assert run.status == "PREPARED"
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run.id,
                MarketDataBootstrapCheckpoint.subject_kind == "FX_PAIR",
            )
        )
        assert checkpoint is not None
        checkpoint.status = "RUNNING"
        checkpoint.attempt_count = 1

    target_settings = Settings(
        database_url=SecretStr(postgres_engine.url.render_as_string(hide_password=False)),
        app_env="development",
        database_target_environment="development",
        database_target_database=postgres_engine.url.database,
        database_local_test_writes_authorized=True,
    )
    audit: list[Mapping[str, Any]] = []
    install_database_write_target_guard(
        postgres_engine,
        target_settings,
        operation="market_data_bootstrap_test",
        operation_kind="ingestion",
        audit_sink=audit.append,
    )
    verify_database_write_target(postgres_engine)
    _verify_target(postgres_engine, target_settings, "development")
    assert audit

    provider = SyntheticProvider()
    first = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=1,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == 1
    assert first["pending_checkpoints"] == 1

    final = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == 2
    assert final["status"] == "PARTIAL"  # Yahoo corporate actions remain unverified facts.
    assert final["canonical_totals"] == {
        "raw_payloads": 2,
        "price_observations": 2,
        "corporate_actions": 2,
        "fx_observations": 2,
    }
    assert final["listing_coverage"][0]["currency"] == "USD"
    assert final["listing_coverage"][0]["price_status"] == "AVAILABLE"
    assert final["listing_coverage"][0]["provider_mapping"]["provider_exchange_code"] == "NMS"
    assert final["listing_coverage"][0]["provider_mapping"]["provider_instrument_type"] == "EQUITY"
    assert final["listing_coverage"][0]["provider_current_quote_rows_skipped"] == 1
    assert final["fx_coverage"][0]["pair"] == "USD/EUR"
    assert final["fx_coverage"][0]["current_quote_rows"] == 0

    with Session(postgres_engine) as session:
        prices = list(session.scalars(select(PriceObservation)))
        actions = list(session.scalars(select(CorporateAction)))
        rates = list(session.scalars(select(FxObservation)))
        payloads = list(session.scalars(select(ExternalRawPayload)))
        assert len(prices) == 2 and all(row.price_kind == "DAILY_CLOSE" for row in prices)
        assert {row.provider_close for row in prices} == {
            Decimal("120.125"),
            Decimal("121.25"),
        }
        assert all(row.currency == "USD" and row.provider_symbol == "SYNTH" for row in prices)
        assert len(actions) == 2 and all(not row.verified for row in actions)
        assert len(rates) == 2 and all(
            (row.base_currency, row.quote_currency) == ("USD", "EUR") for row in rates
        )
        assert len(payloads) == 2 and all(row.payload_sha256 for row in payloads)
        assert all(row.retrieved_at == RETRIEVED_AT for row in payloads)
        reconciliation = reconcile_market_data_bootstrap(session, run_id)
        assert reconciliation["reconciliation"]["status"] == "MATCHED"

    count_before = len(provider.calls)
    replay = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == count_before
    assert replay["canonical_totals"] == final["canonical_totals"]

    with Session(postgres_engine) as session, session.begin():
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint)
            .where(MarketDataBootstrapCheckpoint.run_id == run_id)
            .limit(1)
        )
        assert checkpoint is not None
        checkpoint_report = dict(checkpoint.report)
        coverage_value = checkpoint_report["coverage"]
        assert isinstance(coverage_value, dict)
        coverage = dict(coverage_value)
        coverage["canonical_fingerprint"] = "0" * 64
        checkpoint_report["coverage"] = coverage
        checkpoint.report = checkpoint_report
    with Session(postgres_engine) as session:
        tampered = reconcile_market_data_bootstrap(session, run_id)
        assert tampered["reconciliation"]["status"] == "MISMATCH"
        assert any(
            row["code"] == "CANONICAL_FINGERPRINT_MISMATCH"
            for row in tampered["reconciliation"]["differences"]
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "mode,expected_status",
    [("empty", "UNAVAILABLE"), ("transport_failure", "FAILED")],
)
def test_provider_gaps_are_distinguished_from_ingestion_failures(
    postgres_engine: Engine,
    mode: str,
    expected_status: str,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=SyntheticProvider(mode=mode),
        max_checkpoints=1,
        min_request_interval_seconds=0,
    )
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == "FX_PAIR",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == expected_status
        if mode == "transport_failure":
            assert checkpoint.retryable
            assert checkpoint.failure_code == "NETWORK_ERROR"
        else:
            assert not checkpoint.retryable
            assert checkpoint.failure_code == "NO_PROVIDER_DATA"
        assert result["failed_checkpoints"] == (1 if expected_status == "FAILED" else 0)


@pytest.mark.integration
def test_bootstrap_blocks_crosswalk_digest_change_before_provider_calls(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

    provider = SyntheticProvider()
    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256="0" * 64,
        provider=provider,
        min_request_interval_seconds=0,
    )
    assert result["status"] == "BLOCKED"
    assert not provider.calls


@pytest.mark.integration
def test_unallowlisted_required_fx_pair_blocks_preparation_and_provider_access(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        portfolio = session.scalar(select(Portfolio))
        assert portfolio is not None
        portfolio.base_currency = "XXX"
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))

        preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="development",
        )
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

        assert preview["status"] == "BLOCKED"
        assert preview["unmapped_fx_pairs"] == ["USD/XXX"]
        assert run.status == "BLOCKED"

    provider = SyntheticProvider()
    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        min_request_interval_seconds=0,
    )
    assert result["status"] == "BLOCKED"
    assert not provider.calls


@pytest.mark.integration
def test_changed_listing_identity_blocks_its_checkpoint_before_fetch(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id
        session.execute(update(Listing).where(Listing.id == listing.id).values(ticker="CHANGED"))

    provider = SyntheticProvider()
    execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert all(query.domain != ExternalDataDomain.MARKET_DATA for query in provider.calls)
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == "BLOCKED"
        assert checkpoint.failure_code == "CANONICAL_LISTING_IDENTITY_CHANGED"


def test_temporal_validation_rejects_future_observation_and_out_of_window_action() -> None:
    from types import SimpleNamespace

    retrieved_at = datetime(2026, 10, 6, tzinfo=UTC)
    plan = {
        "records": [SimpleNamespace(retrieved_at=retrieved_at)],
        "prices": [],
        "fx": [],
        "actions": [
            {
                "source_action_id": "synthetic-action",
                "observed_at": datetime(2026, 10, 7, tzinfo=UTC),
                "effective_date": datetime(2026, 9, 30, tzinfo=UTC),
            }
        ],
        "report": {},
    }
    issues = _temporal_issues(plan, start_date=START, end_date=END)
    assert {issue["code"] for issue in issues} == {
        "OBSERVATION_AFTER_RETRIEVAL",
        "ACTION_OUTSIDE_REQUESTED_WINDOW",
    }


def test_bootstrap_window_and_production_selection_are_rejected() -> None:
    from portfolio_api.market_data_bootstrap import _validate_date_window

    with pytest.raises(MarketDataBootstrapError, match="ten years"):
        _validate_date_window(date(2010, 1, 1), date(2026, 10, 5))
    with pytest.raises(MarketDataBootstrapError, match="disabled for production"):
        preview_market_data_bootstrap(
            Session(),
            crosswalk=YahooListingCrosswalk(
                provider_id="YAHOO_FINANCE",
                provider_schema_version="yahoo-chart-v8",
                verified_at=RETRIEVED_AT,
                mappings=(),
            ),
            crosswalk_sha256="0" * 64,
            start_date=START,
            end_date=END,
            target_environment="production",
        )


def test_private_report_is_create_only_and_written_outside_the_repository(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "synthetic-market-report.json"
    report = {"status": "COMPLETE", "provider_payload_hash": "a" * 64}

    _write_private_report(report_path, report)

    assert json.loads(report_path.read_text()) == report
    if os.name != "nt":
        assert report_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(MarketDataBootstrapError, match="already exists"):
        _write_private_report(report_path, report)
