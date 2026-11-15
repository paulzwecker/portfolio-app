"""One private, offline source-to-investor rehearsal using the existing importers.

The sole held listing is Amazon with fictional quantities. The independently
verified SEC issuer remains separate; no price, forecast or model is invented
for it. Browser access starts only after ingestion and remains read-only.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from browser_public_market_data import PublicMarketReplay
from browser_real_estimates import prepare_real_estimates
from browser_real_sec_data import SecRecording
from browser_refresh_data import RefreshRehearsal
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import Actor, Company
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.settings import Settings


def prepare_integrated_sources(
    engine: Engine,
    settings: Settings,
    market_manifest: Path,
    consensus_receipt: Path,
    sec_manifest: Path,
) -> dict[str, Any]:
    """Reuse reviewed private recordings; no provider network or production state."""
    market = PublicMarketReplay(engine, settings, market_manifest)
    with Session(engine) as session, session.begin():
        services.transition_lifecycle(
            session,
            UUID(market.metadata["company_id"]),
            s.LifecycleChange(
                new_state="WATCHLIST",
                expected_event_id=None,
                actor=Actor.IMPORT,
                effective_at=datetime.now(UTC),
                reason="Fictional active research scope for the combined private rehearsal",
                source="private-integrated-source-rehearsal",
            ),
        )
    market_baseline = market.protected_state()
    with market.running(), Session(engine) as session:
        for phase in ("initial", "incremental"):
            market.phase = phase
            market.run_recorded(
                session,
                market.settings,
                domains=[ExternalDataDomain.MARKET_DATA, ExternalDataDomain.FX],
            )
            session.commit()
    market_readback = market.readback()
    expected_market = market.metadata["expected"]
    if (
        market_readback["counts"]["price_observations"] != expected_market["final_prices"]
        or market_readback["counts"]["fx_observations"] != expected_market["final_fx"]
        or market_readback["worker_errors"]
        or market.protected_state() != market_baseline
    ):
        raise AssertionError(
            f"Combined market ingestion did not reconcile: {market_readback['counts']}"
        )

    estimates = prepare_real_estimates(engine, settings, consensus_receipt, context=market.metadata)
    recording = SecRecording(sec_manifest)
    issuer = recording.manifest.issuer
    if issuer.ticker == "AMZN" or str(issuer.company_id) == market.metadata["company_id"]:
        raise ValueError("SEC evidence must retain its separate reviewed issuer identity")
    with Session(engine) as session, session.begin():
        company = Company(
            id=issuer.company_id, name=issuer.name, reporting_currency=issuer.currency
        )
        session.add(company)
        session.flush()
        security = services.create_security(
            session, company.id, s.SecurityCreate(name=issuer.name, security_type="COMMON_STOCK")
        )
        listing = services.create_listing(
            session,
            security.id,
            s.ListingCreate(ticker=issuer.ticker, venue=issuer.venue, currency=issuer.currency),
        )
        services.transition_lifecycle(
            session,
            company.id,
            s.LifecycleChange(
                new_state="WATCHLIST",
                expected_event_id=None,
                actor=Actor.IMPORT,
                effective_at=datetime.now(UTC),
                reason="Fictional research context for independently recorded SEC issuer",
                source="private-integrated-source-rehearsal",
            ),
        )
        sec_metadata = {
            **recording.metadata(),
            "company_id": str(company.id),
            "stock_listing_id": str(listing.id),
            "portfolio_id": market.metadata["portfolio_id"],
        }
    sec = RefreshRehearsal(engine, settings, sec_metadata, recording=recording)
    sec_baseline = sec.protected_state()
    with sec.running(), Session(engine) as session:
        run_scheduled(
            session,
            sec.settings,
            domains=[ExternalDataDomain.REPORTED_FUNDAMENTALS, ExternalDataDomain.SOURCE_DOCUMENTS],
            company_ids={issuer.company_id},
            sec_research_scope=True,
        )
        session.commit()
    sec_readback = sec.readback()
    sec_counts = cast(dict[str, int], sec_readback["counts"])
    expected_sec = recording.manifest.expected
    if (
        sec_counts["reported_fundamental_observations"] != expected_sec["fundamental_observations"]
        or sec_counts["source_documents"] != expected_sec["source_documents"]
        or sec_readback["worker_errors"]
        or sec.protected_state() != sec_baseline
    ):
        raise AssertionError("Combined SEC ingestion did not reconcile")
    return {
        "scenario": "integrated-real-sources",
        "company_id": market.metadata["company_id"],
        "listing_id": market.metadata["listing_id"],
        "portfolio_id": market.metadata["portfolio_id"],
        "fixture_context": (
            "Recorded real sources; fictional portfolio quantities and research context. "
            "No accepted valuation models; no production data or live provider requests."
        ),
        "market": {**market.metadata, "readback": market_readback},
        "estimates": estimates,
        "sec": {**sec_metadata, "readback": sec_readback},
    }
