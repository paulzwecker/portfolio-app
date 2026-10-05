"""Reconcile persisted provider market facts to workbook overlap and portfolio use."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    CorporateAction,
    CurrentLifecycle,
    ExternalRawPayload,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    LifecycleEvent,
    Listing,
    MarketDataBatch,
    Portfolio,
    PriceObservation,
    Security,
)
from portfolio_api.domain.queries import overview
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import YAHOO_PROVIDER_ID


def _date_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, UTC)
    return start, start + timedelta(days=1)


def build_reconciliation(session: Session) -> dict[str, Any]:
    workbook_batch = session.scalar(
        select(MarketDataBatch)
        .where(
            MarketDataBatch.source_kind == "WORKBOOK_SNAPSHOT",
            MarketDataBatch.source_as_of.is_not(None),
        )
        .order_by(MarketDataBatch.source_as_of.desc(), MarketDataBatch.recorded_at.desc())
        .limit(1)
    )
    if workbook_batch is None or workbook_batch.source_as_of is None:
        raise ValueError("No dated workbook market-data batch is available for reconciliation")
    comparison_date = workbook_batch.source_as_of.date()
    window_start, window_end = _date_window(comparison_date)

    lifecycle_rows = session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state).join(
            CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id
        )
    ).all()
    active_states = {
        company_id: state
        for company_id, state in lifecycle_rows
        if state in {"PORTFOLIO", "WATCHLIST"}
    }
    active_companies = session.execute(
        select(Security.company_id, Listing.id)
        .join(Listing, Listing.security_id == Security.id)
        .where(Security.company_id.is_not(None))
    ).all()
    companies_with_listing = {company_id for company_id, _ in active_companies}
    unlisted = session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state)
        .join(CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id)
        .where(LifecycleEvent.new_state.in_(["PORTFOLIO", "WATCHLIST"]))
    ).all()
    missing_ids = {company_id for company_id, _ in unlisted} - companies_with_listing
    # Some companies with no Security at all need the Company table for the name.
    from portfolio_api.domain.models import Company

    missing_names = (
        session.execute(select(Company.id, Company.name).where(Company.id.in_(missing_ids))).all()
        if missing_ids
        else []
    )
    state_by_company = dict(unlisted)
    missing_records = [
        {"company": name, "lifecycle": state_by_company[company_id]}
        for company_id, name in sorted(missing_names, key=lambda row: row[1])
    ]

    active_company_listing_count = (
        session.scalar(
            select(func.count(func.distinct(Listing.id)))
            .join(Security, Listing.security_id == Security.id)
            .where(Security.company_id.in_(active_states))
        )
        or 0
    )
    latest_active_snapshot = session.scalar(
        select(HoldingSnapshot)
        .join(Portfolio, HoldingSnapshot.portfolio_id == Portfolio.id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    held_listing_count = (
        session.scalar(
            select(func.count())
            .select_from(HoldingPosition)
            .where(HoldingPosition.snapshot_id == latest_active_snapshot.id)
        )
        if latest_active_snapshot
        else 0
    )

    provider_prices = session.execute(
        select(
            PriceObservation.price_kind,
            func.count(),
            func.count(func.distinct(PriceObservation.listing_id)),
            func.min(PriceObservation.market_date),
            func.max(PriceObservation.market_date),
        )
        .where(PriceObservation.provider == YAHOO_PROVIDER_ID)
        .group_by(PriceObservation.price_kind)
    ).all()
    provider_price_summary = {
        kind: {
            "rows": count,
            "distinct_listings": listing_count,
            "earliest": earliest.date().isoformat() if earliest else None,
            "latest": latest.date().isoformat() if latest else None,
        }
        for kind, count, listing_count, earliest, latest in provider_prices
    }
    provider_action_rows = session.execute(
        select(CorporateAction.action_type, CorporateAction.verified, func.count())
        .where(CorporateAction.provider == YAHOO_PROVIDER_ID)
        .group_by(CorporateAction.action_type, CorporateAction.verified)
    ).all()
    provider_action_summary = {
        f"{action_type}:{'VERIFIED' if verified else 'UNVERIFIED'}": count
        for action_type, verified, count in provider_action_rows
    }
    price_quality_rows = session.execute(
        select(PriceObservation.price_kind, PriceObservation.data_quality, func.count())
        .where(PriceObservation.provider == YAHOO_PROVIDER_ID)
        .group_by(PriceObservation.price_kind, PriceObservation.data_quality)
    ).all()
    fx_rows = session.execute(
        select(
            FxObservation.base_currency,
            FxObservation.quote_currency,
            func.count(),
            func.min(FxObservation.effective_at),
            func.max(FxObservation.effective_at),
        )
        .where(FxObservation.provider == YAHOO_PROVIDER_ID)
        .group_by(FxObservation.base_currency, FxObservation.quote_currency)
    ).all()
    provider_batches = session.scalars(
        select(MarketDataBatch)
        .where(MarketDataBatch.source_kind == "PROVIDER_RESPONSE")
        .order_by(MarketDataBatch.recorded_at)
    ).all()
    raw_count = (
        session.scalar(
            select(func.count())
            .select_from(ExternalRawPayload)
            .join(MarketDataBatch, ExternalRawPayload.batch_id == MarketDataBatch.id)
            .where(MarketDataBatch.source_kind == "PROVIDER_RESPONSE")
        )
        or 0
    )

    raw_market_rows = session.execute(
        select(
            MarketDataBatch.normalizer_version,
            ExternalRawPayload.source_record_id,
            ExternalRawPayload.payload_bytes,
        )
        .join(MarketDataBatch, ExternalRawPayload.batch_id == MarketDataBatch.id)
        .where(
            MarketDataBatch.source_kind == "PROVIDER_RESPONSE",
            ExternalRawPayload.domain == "MARKET_DATA",
            ExternalRawPayload.provider_id == YAHOO_PROVIDER_ID,
        )
    ).all()
    response_session_duplicates: list[dict[str, Any]] = []
    for normalizer_version, source_record_id, payload_bytes in raw_market_rows:
        try:
            chart_results = json.loads(gzip.decompress(payload_bytes))["chart"]["result"]
            result = chart_results[0]
            timezone = ZoneInfo(result["meta"]["exchangeTimezoneName"])
            timestamps = result.get("timestamp") or []
            close = (result.get("indicators") or {}).get("quote", [{}])[0].get("close", [])
            adjusted_rows = (result.get("indicators") or {}).get("adjclose") or []
            adjusted = adjusted_rows[0].get("adjclose", []) if adjusted_rows else []
            volume = (result.get("indicators") or {}).get("quote", [{}])[0].get("volume", [])
            session_indices: dict[str, list[int]] = defaultdict(list)
            for index, timestamp in enumerate(timestamps):
                session_day = datetime.fromtimestamp(timestamp, UTC).astimezone(timezone).date()
                session_indices[session_day.isoformat()].append(index)
            for session_label, indices in session_indices.items():
                if len(indices) < 2:
                    continue
                prices = {
                    (close[index], adjusted[index] if index < len(adjusted) else None)
                    for index in indices
                }
                volumes = {volume[index] if index < len(volume) else None for index in indices}
                response_session_duplicates.append(
                    {
                        "normalizer_version": normalizer_version,
                        "source_record_id": source_record_id,
                        "session_date": session_label,
                        "bar_count": len(indices),
                        "identical_price_values": len(prices) == 1,
                        "identical_volume_values": len(volumes) == 1,
                    }
                )
        except (IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            response_session_duplicates.append(
                {
                    "normalizer_version": normalizer_version,
                    "source_record_id": source_record_id,
                    "parse_error": True,
                }
            )

    legacy_rows = session.execute(
        select(
            PriceObservation.listing_id,
            Listing.venue,
            Listing.ticker,
            Listing.currency,
            PriceObservation.split_adjusted_close,
            PriceObservation.data_quality,
        )
        .join(Listing, PriceObservation.listing_id == Listing.id)
        .join(MarketDataBatch, PriceObservation.batch_id == MarketDataBatch.id)
        .where(
            MarketDataBatch.source_kind == "WORKBOOK_SNAPSHOT",
            PriceObservation.price_kind == "DAILY_CLOSE",
            PriceObservation.market_date >= window_start,
            PriceObservation.market_date < window_end,
            PriceObservation.data_quality.in_(["PASS", "PASS_VERIFIED_FALLBACK"]),
        )
    ).all()
    yahoo_rows = session.execute(
        select(
            PriceObservation.listing_id,
            PriceObservation.split_adjusted_close,
        )
        .where(
            PriceObservation.provider == YAHOO_PROVIDER_ID,
            PriceObservation.price_kind == "DAILY_CLOSE",
            PriceObservation.market_date >= window_start,
            PriceObservation.market_date < window_end,
            PriceObservation.data_quality == "PASS",
        )
        .order_by(PriceObservation.recorded_at, PriceObservation.id)
    ).all()
    legacy_by_listing: dict[Any, tuple[str, str, str | None, Decimal]] = {}
    for listing_id, venue, ticker, currency, close, _quality in legacy_rows:
        if close is not None:
            legacy_by_listing.setdefault(listing_id, (venue, ticker, currency, close))
    # A replay may append several provider observations for one session date.
    # Compare the latest currently-known observation deterministically; historical
    # as-of queries remain available from the canonical query API.
    yahoo_by_listing = {listing_id: close for listing_id, close in yahoo_rows if close is not None}
    overlap: list[dict[str, Any]] = []
    for listing_id in legacy_by_listing.keys() & yahoo_by_listing.keys():
        venue, ticker, currency, legacy_close = legacy_by_listing[listing_id]
        yahoo_close = yahoo_by_listing[listing_id]
        difference = abs(yahoo_close - legacy_close)
        overlap.append(
            {
                "identity": f"{venue}:{ticker}:{currency}",
                "workbook_close": str(legacy_close),
                "provider_close": str(yahoo_close),
                "absolute_difference": str(difference),
                "within_0_0001_currency_units": difference <= Decimal("0.0001"),
            }
        )
    differences = [Decimal(item["absolute_difference"]) for item in overlap]
    relative_differences_bps = [
        Decimal(item["absolute_difference"]) / Decimal(item["workbook_close"]) * Decimal(10000)
        for item in overlap
        if Decimal(item["workbook_close"]) != 0
    ]

    portfolio = session.scalar(select(Portfolio).order_by(Portfolio.created_at).limit(1))
    portfolio_result = None
    if portfolio is not None:
        view = overview(session, portfolio.id)
        holdings = [*view.standalone_positions, *(p for c in view.companies for p in c.positions)]
        position_value_sum = sum(
            (p.base_market_value for p in holdings if p.base_market_value is not None),
            Decimal(0),
        )
        cash_value_sum = sum(
            (cash.base_market_value for cash in view.cash_valuations if cash.base_market_value),
            Decimal(0),
        )
        recomputed_total = position_value_sum + cash_value_sum
        portfolio_result = {
            "status": view.valuation_status,
            "currency": view.valuation_currency,
            "position_count": len(holdings),
            "valued_position_count": sum(p.valuation_status == "VALUED" for p in holdings),
            "position_native_currencies": dict(Counter(p.currency for p in holdings)),
            "position_base_value_sum": str(position_value_sum),
            "cash_base_value_sum": str(cash_value_sum),
            "api_base_market_value": str(view.base_market_value)
            if view.base_market_value is not None
            else None,
            "recomputed_components_total": str(recomputed_total),
            "aggregation_difference": str(
                view.base_market_value - recomputed_total
                if view.base_market_value is not None
                else Decimal(0)
            ),
            "valuation_gaps": [
                {"identity": gap.identity, "reason": gap.reason} for gap in view.valuation_gaps
            ],
            "cash_statuses": {
                cash.currency: cash.valuation_status for cash in view.cash_valuations
            },
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "workbook_reference": {
            "source_digest": workbook_batch.source_digest,
            "as_of": comparison_date.isoformat(),
        },
        "universe_coverage": {
            "active_companies": len(active_states),
            "portfolio_companies": sum(state == "PORTFOLIO" for state in active_states.values()),
            "watchlist_companies": sum(state == "WATCHLIST" for state in active_states.values()),
            "active_companies_with_listing": len(companies_with_listing & active_states.keys()),
            "active_company_listings": active_company_listing_count,
            "held_positions": held_listing_count,
            "unresolved_active_companies": missing_records,
        },
        "provider": {
            "provider_id": YAHOO_PROVIDER_ID,
            "provider_batches": [
                {
                    "id": str(batch.id),
                    "source_digest": batch.source_digest,
                    "normalizer_version": batch.normalizer_version,
                    "recorded_at": batch.recorded_at.isoformat(),
                    "raw_payload_count": session.scalar(
                        select(func.count())
                        .select_from(ExternalRawPayload)
                        .where(ExternalRawPayload.batch_id == batch.id)
                    ),
                }
                for batch in provider_batches
            ],
            "raw_payload_count": raw_count,
            "duplicate_session_bars_in_raw_responses": response_session_duplicates,
            "prices": provider_price_summary,
            "price_quality_counts": {
                f"{kind}:{quality}": count for kind, quality, count in price_quality_rows
            },
            "corporate_actions": provider_action_summary,
            "fx_pairs": [
                {
                    "pair": f"{base}/{quote}",
                    "observations": count,
                    "earliest_effective_at": earliest.isoformat(),
                    "latest_effective_at": latest.isoformat(),
                }
                for base, quote, count, earliest, latest in fx_rows
            ],
        },
        "history_reconciliation": {
            "method": (
                "Exact canonical listing and market date; compare split-adjusted, "
                "non-total-return closes."
            ),
            "comparison_date": comparison_date.isoformat(),
            "overlap_count": len(overlap),
            "tolerance_currency_units": "0.0001",
            "within_tolerance_count": sum(item["within_0_0001_currency_units"] for item in overlap),
            "within_0_01_currency_units_count": sum(
                Decimal(item["absolute_difference"]) <= Decimal("0.01") for item in overlap
            ),
            "within_0_10_currency_units_count": sum(
                Decimal(item["absolute_difference"]) <= Decimal("0.10") for item in overlap
            ),
            "maximum_absolute_difference": str(max(differences, default=Decimal(0))),
            "maximum_relative_difference_basis_points": str(
                max(relative_differences_bps, default=Decimal(0))
            ),
            "representative_samples": sorted(
                overlap,
                key=lambda item: Decimal(item["absolute_difference"]),
                reverse=True,
            )[:10],
        },
        "portfolio_valuation_reconciliation": portfolio_result,
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write reconciliation JSON to this path.")
    args = parser.parse_args(argv)
    engine = create_database_engine(Settings())
    if engine is None:
        parser.error("DATABASE_URL is required to reconcile market facts")
    try:
        with Session(engine) as session:
            report = build_reconciliation(session)
            output = json.dumps(report, indent=2, sort_keys=True, default=str)
    finally:
        engine.dispose()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
