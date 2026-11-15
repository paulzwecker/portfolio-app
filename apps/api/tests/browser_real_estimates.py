"""Private real-source estimate replay; no network fallback or production inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.consensus_estimates import add_provider_mapping
from portfolio_api.database import Base
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import (
    Actor,
    Company,
    ConsensusEstimateObservation,
    ConsensusEstimateSourceRole,
    Listing,
    Portfolio,
    Security,
)
from portfolio_api.eodhd_consensus import EodhdConsensusProvider
from portfolio_api.external_data import ExternalDataDomain, ProviderQuery
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.settings import Settings

WRITTEN_TABLES = {
    "consensus_estimate_batches",
    "consensus_estimate_observations",
    "external_raw_payloads",
    "external_ingestion_runs",
    "external_ingestion_attempts",
}


def protected_estimate_state(engine: Engine) -> str:
    with engine.connect() as connection:
        state = {
            table.name: connection.scalar(
                text(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), "
                    f"'[]'::jsonb)::text FROM \"{table.name}\" t"
                )
            )
            for table in Base.metadata.sorted_tables
            if table.name not in WRITTEN_TABLES
        }
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def prepare_real_estimates(
    engine: Engine,
    settings: Settings,
    receipt_path: Path,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_bytes())
    path = Path(receipt["file"]).resolve()
    if (
        not path.is_relative_to(receipt_path.parent.resolve())
        or receipt.get("production") is not False
    ):
        raise ValueError("A private isolated capture in the receipt directory is required")
    raw = path.read_bytes()
    captured = datetime.fromisoformat(receipt["retrieved_at"])
    if (
        hashlib.sha256(raw).hexdigest() != receipt["sha256"]
        or captured.tzinfo is None
        or captured > datetime.now(UTC)
    ):
        raise ValueError("Private capture hash or retrieval time is invalid")
    from portfolio_api.eodhd_consensus import EODHD_CONSENSUS_URL

    if receipt["url"] != EODHD_CONSENSUS_URL:
        raise ValueError("The recorded estimate URL is not the reviewed fixed endpoint")
    settings = settings.model_copy(update={"consensus_provider": "eodhd_demo_estimates"})
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if context is None:
            company = services.create_company(
                session, s.CompanyCreate(name="Amazon", reporting_currency="USD")
            )
            security = services.create_security(
                session,
                company.id,
                s.SecurityCreate(name="Amazon common stock", security_type="COMMON_STOCK"),
            )
            listing = services.create_listing(
                session, security.id, s.ListingCreate(ticker="AMZN", venue="NASDAQ", currency="USD")
            )
            services.transition_lifecycle(
                session,
                company.id,
                s.LifecycleChange(
                    new_state="WATCHLIST",
                    expected_event_id=None,
                    actor=Actor.IMPORT,
                    effective_at=datetime.now(UTC),
                    reason="Fictional isolated research context; genuine recorded estimates",
                    source="private-estimate-rehearsal",
                ),
            )
            portfolio = services.create_portfolio(
                session,
                s.PortfolioCreate(name="Isolated expectations research", base_currency="EUR"),
            )
        else:
            existing_company = session.get(Company, UUID(context["company_id"]))
            existing_listing = session.get(Listing, UUID(context["listing_id"]))
            existing_portfolio = session.get(Portfolio, UUID(context["portfolio_id"]))
            existing_security = (
                session.get(Security, existing_listing.security_id) if existing_listing else None
            )
            if (
                existing_company is None
                or existing_listing is None
                or existing_portfolio is None
                or existing_security is None
                or existing_company.name != "Amazon"
                or existing_company.reporting_currency != "USD"
                or existing_security.company_id != existing_company.id
                or existing_security.security_type != "COMMON_STOCK"
                or (existing_listing.ticker, existing_listing.venue, existing_listing.currency)
                != ("AMZN", "NASDAQ", "USD")
            ):
                raise ValueError("Combined rehearsal requires the exact existing Amazon identity")
            company, listing, portfolio = existing_company, existing_listing, existing_portfolio
        mapping = add_provider_mapping(
            session,
            company_id=company.id,
            listing_id=listing.id,
            provider_id="eodhd_demo_estimates",
            provider_symbol="AMZN.US",
            role=ConsensusEstimateSourceRole.PRIMARY,
            effective_from=captured,
            evidence_source="https://www.sec.gov/Archives/edgar/data/1018724/000101872426000040/R1.htm",
            currency="USD",
            currency_evidence_source="https://raw.githubusercontent.com/EodHistoricalData/eodhd-claude-skills/main/skills/eodhd-api/references/endpoints/fundamentals-data.md",
        )
    before = protected_estimate_state(engine)
    calls = 0
    original_fetch = EodhdConsensusProvider.fetch

    async def fetch(_provider: EodhdConsensusProvider, query: ProviderQuery) -> Any:
        nonlocal calls
        calls += 1

        def transport(url: str) -> bytes:
            if url != receipt["url"]:
                raise AssertionError("Exact recorded URL required; network is forbidden")
            return raw

        provider = EodhdConsensusProvider(
            settings, mapping, transport=transport, clock=lambda: captured
        )
        return await original_fetch(provider, query)

    with patch.object(EodhdConsensusProvider, "fetch", fetch), Session(engine) as session:
        options: dict[str, Any] = {
            "domains": [ExternalDataDomain.CONSENSUS_ESTIMATES],
            "company_ids": {company.id},
        }
        first = run_scheduled(session, settings, **options)
        session.commit()
        repeated = run_scheduled(session, settings, **options)
        session.commit()
        if calls != 1:
            raise AssertionError("Same-day scope unexpectedly fetched again")
        # A delayed scheduler replay uses the identical real capture: it cannot invent
        # a new observation time, a changed forecast or another historical snapshot.
        delayed = run_scheduled(
            session, settings, **options, run_date=captured.date() + timedelta(days=3)
        )
        session.commit()
        count = session.scalar(select(func.count()).select_from(ConsensusEstimateObservation))
    if protected_estimate_state(engine) != before:
        raise AssertionError("Estimate ingestion altered unrelated canonical state")
    source = json.loads(raw, parse_float=Decimal)
    samples = []
    for group, period_type in [("Annual", "ANNUAL"), ("Quarterly", "QUARTERLY")]:
        for end, row in source["Earnings::Trend"][group].items():
            if date.fromisoformat(end) <= captured.date():
                continue
            for metric, prefix in [("REVENUE", "revenueEstimate"), ("EPS", "earningsEstimate")]:
                samples.append(
                    {
                        "metric": metric,
                        "period_type": period_type,
                        "period_end": end,
                        "value": str(row[f"{prefix}Avg"]),
                        "low_value": str(row[f"{prefix}Low"]),
                        "high_value": str(row[f"{prefix}High"]),
                        "analyst_count": int(Decimal(row[f"{prefix}NumberOfAnalysts"])),
                        "currency": "USD",
                        "unit": "currency" if metric == "REVENUE" else "currency/share",
                        "data_quality": "PASS" if metric == "REVENUE" else "DATA_CHECK",
                    }
                )
    if count != len(samples) or count != 8:
        raise AssertionError("Real forward-period observation count did not reconcile")
    return {
        "scenario": "real-consensus",
        "company_id": str(company.id),
        "portfolio_id": str(portfolio.id),
        "listing_id": str(listing.id),
        "captured_at": captured.isoformat(),
        "source_payload_sha256": receipt["sha256"],
        "fixture_context": "Real demo estimates; fictional research context",
        "expected": {"observations": count, "samples": samples},
        "offline_transport_calls": calls,
        "ingestion_runs": [first, repeated, delayed],
        "all_protected_state_sha256": before,
    }
