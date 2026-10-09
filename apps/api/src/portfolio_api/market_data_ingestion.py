"""Repeatable provider-backed market and FX ingestion for exact active identities."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    CashPosition,
    Company,
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
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    NormalizationDisposition,
    ProviderQuery,
    RawProviderRecord,
    raw_batch_fingerprint,
)
from portfolio_api.settings import REPOSITORY_PATH, Settings
from portfolio_api.yahoo_finance import (
    FX_SYMBOLS,
    YAHOO_PROVIDER_ID,
    YahooChartNormalizer,
    YahooCorporateActionFact,
    YahooFinanceProvider,
    YahooFxNormalizer,
    YahooListingCrosswalk,
    YahooListingFacts,
    YahooListingMapping,
    load_yahoo_crosswalk,
    yahoo_mapping_for_listing,
)

CROSSWALK_PATH = REPOSITORY_PATH / "reference" / "market-data" / "providers" / "yahoo-listings.json"
DEFAULT_LOOKBACK_DAYS = 365 * 10
DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS = 90
INSERT_CHUNK_SIZE = 1000


def active_market_listings(
    session: Session,
) -> tuple[list[tuple[Listing, Security, Company]], set[UUID]]:
    lifecycle = {
        event.company_id: event.new_state
        for event in session.scalars(
            select(LifecycleEvent).join(
                CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id
            )
        )
    }
    latest_snapshot = session.scalar(
        select(HoldingSnapshot)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    held_ids = (
        set(
            session.scalars(
                select(HoldingPosition.listing_id).where(
                    HoldingPosition.snapshot_id == latest_snapshot.id
                )
            )
        )
        if latest_snapshot
        else set()
    )
    rows = session.execute(
        select(Listing, Security, Company)
        .join(Security, Listing.security_id == Security.id)
        .outerjoin(Company, Security.company_id == Company.id)
        .order_by(Listing.venue, Listing.ticker)
    ).all()
    selected = [
        (listing, security, company)
        for listing, security, company in rows
        if (company is not None and lifecycle.get(company.id) in {"PORTFOLIO", "WATCHLIST"})
        or listing.id in held_ids
    ]
    return selected, held_ids


def portfolio_fx_requirements(session: Session) -> tuple[str | None, set[tuple[str, str]]]:
    portfolio = session.scalar(select(Portfolio).order_by(Portfolio.created_at).limit(1))
    if portfolio is None:
        return None, set()
    snapshot = session.scalar(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.portfolio_id == portfolio.id)
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    if snapshot is None:
        return portfolio.base_currency, set()
    currencies = set(
        session.scalars(
            select(Listing.currency)
            .join(HoldingPosition, HoldingPosition.listing_id == Listing.id)
            .where(HoldingPosition.snapshot_id == snapshot.id, Listing.currency.is_not(None))
        )
    )
    currencies.update(
        currency
        for currency in session.scalars(
            select(CashPosition.currency).where(CashPosition.snapshot_id == snapshot.id)
        )
    )
    required = {
        (currency, portfolio.base_currency)
        for currency in currencies
        if currency is not None and currency != portfolio.base_currency
    }
    return portfolio.base_currency, required


def _batch_id(digest: str, normalizer_version: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"market-data-provider:{digest}:{normalizer_version}")


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _raw_payload_row(batch_id: UUID, record: RawProviderRecord) -> dict[str, object]:
    if record.payload is None or record.source_record_id is None:
        raise ValueError("Provider persistence requires inline raw payload bytes and a record ID")
    return {
        "id": uuid5(NAMESPACE_URL, f"external-raw:{batch_id}:{record.source_record_id}"),
        "batch_id": batch_id,
        "provider_id": record.provider_id,
        "domain": record.domain.value,
        "source_record_id": record.source_record_id,
        "source_url": str(record.source_url) if record.source_url else None,
        "media_type": record.media_type,
        "content_encoding": "gzip",
        "payload_sha256": record.payload_sha256,
        "retrieved_at": record.retrieved_at,
        "payload_bytes": gzip.compress(record.payload, mtime=0),
    }


def _market_batch_plan(
    query: ProviderQuery,
    records: list[RawProviderRecord],
    normalizer: YahooChartNormalizer,
) -> dict[str, Any] | None:
    if not records:
        return None
    digest = raw_batch_fingerprint(YAHOO_PROVIDER_ID, query, records)
    batch_id = _batch_id(digest, YahooChartNormalizer.version)
    normalized: list[tuple[RawProviderRecord, YahooListingFacts]] = []
    rejected: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for record in records:
        result = normalizer.normalize(record)
        if result.disposition == NormalizationDisposition.REJECTED:
            rejected.append(
                {
                    "source_record_id": record.source_record_id or "",
                    "code": result.issues[0].code,
                    "message": result.issues[0].message,
                }
            )
            continue
        if result.observation is None:
            raise RuntimeError("Accepted Yahoo normalization returned no market observation")
        normalized.append((record, result.observation))
        warnings.extend(
            {
                "source_record_id": record.source_record_id or "",
                "code": issue.code,
                "message": issue.message,
            }
            for issue in result.issues
        )
    price_rows: list[dict[str, object]] = []
    action_rows: list[dict[str, object]] = []
    for record, facts in normalized:
        for fact in (*facts.prices, *((facts.current_quote,) if facts.current_quote else ())):
            price_rows.append(
                {
                    "id": uuid5(NAMESPACE_URL, f"{digest}:{fact.source_ref}"),
                    "listing_id": facts.listing_id,
                    "batch_id": batch_id,
                    "price_kind": fact.price_kind,
                    "market_date": fact.market_date,
                    "observed_at": fact.observed_at,
                    "recorded_at": record.retrieved_at,
                    "provider_close": fact.provider_close,
                    "split_adjusted_close": fact.split_adjusted_close,
                    "total_return_close": fact.total_return_close,
                    "volume": fact.volume,
                    "currency": fact.currency,
                    "provider_currency": fact.provider_currency,
                    "source_price_multiplier": fact.source_price_multiplier,
                    "provider": YAHOO_PROVIDER_ID,
                    "provider_symbol": fact.provider_symbol,
                    "adjustment_basis": fact.adjustment_basis,
                    "data_quality": "PASS",
                    "source_ref": fact.source_ref,
                }
            )
        action_rows.extend(
            _action_row(batch_id, facts.listing_id, record, action)
            for action in facts.corporate_actions
        )
    item_summary = [
        {
            "source_record_id": record.source_record_id,
            "provider_symbol": facts.provider_symbol,
            "listing_id": str(facts.listing_id),
            "history_rows": len(facts.prices),
            "provider_current_quote": str(facts.current_quote.provider_close)
            if facts.current_quote
            else None,
            "current_quote": str(facts.current_quote.split_adjusted_close)
            if facts.current_quote
            else None,
            "quote_observed_at": facts.current_quote.observed_at.isoformat()
            if facts.current_quote and facts.current_quote.observed_at
            else None,
            "latest_history_date": max(
                (fact.market_date.date() for fact in facts.prices), default=date.min
            ).isoformat()
            if facts.prices
            else None,
            "earliest_history_date": min(
                (fact.market_date.date() for fact in facts.prices), default=date.min
            ).isoformat()
            if facts.prices
            else None,
            "corporate_actions": len(facts.corporate_actions),
            "missing_close_count": facts.missing_close_count,
            "in_progress_bar_count": facts.in_progress_bar_count,
            "duplicate_session_bar_count": facts.duplicate_session_bar_count,
            "provider_exchange": facts.returned_exchange,
        }
        for record, facts in normalized
    ]
    report: dict[str, Any] = {
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": "yahoo-chart-v8",
        "normalizer_version": YahooChartNormalizer.version,
        "source_digest": digest,
        "query_scope": query.model_dump(mode="json", exclude={"requested_at"}),
        "requested_subjects": len(query.subjects),
        "raw_responses": len(records),
        "accepted_subjects": len(normalized),
        "rejected_subjects": rejected,
        "normalization_warnings": warnings,
        "mapped_listings": item_summary,
        "daily_price_rows": sum(len(facts.prices) for _, facts in normalized),
        "current_quote_rows": sum(facts.current_quote is not None for _, facts in normalized),
        "corporate_action_rows": len(action_rows),
        "in_progress_bar_rows_skipped": sum(facts.in_progress_bar_count for _, facts in normalized),
        "duplicate_session_bars_collapsed": sum(
            facts.duplicate_session_bar_count for _, facts in normalized
        ),
    }
    batch_values = {
        "id": batch_id,
        "source_digest": digest,
        "source_kind": "PROVIDER_RESPONSE",
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": "yahoo-chart-v8",
        "normalizer_version": YahooChartNormalizer.version,
        "query_scope": report["query_scope"],
        "source_as_of": None,
        "source_updated_text": None,
        "recorded_at": datetime.now(UTC),
        "provider_summary": {"response_count": len(records), "accepted_subjects": len(normalized)},
        "reconciliation": report,
    }
    return {
        "batch": batch_values,
        "records": records,
        "prices": price_rows,
        "actions": action_rows,
        "fx": [],
        "report": report,
    }


def _action_row(
    batch_id: UUID,
    listing_id: UUID,
    record: RawProviderRecord,
    fact: YahooCorporateActionFact,
) -> dict[str, object]:
    return {
        "id": uuid5(NAMESPACE_URL, fact.source_action_id),
        "listing_id": listing_id,
        "source_action_id": fact.source_action_id,
        "provider": YAHOO_PROVIDER_ID,
        "effective_date": fact.effective_date,
        "observed_at": fact.observed_at,
        "action_type": fact.action_type,
        "ratio_before": fact.ratio_before,
        "ratio_after": fact.ratio_after,
        "cash_amount": fact.cash_amount,
        "cash_currency": fact.cash_currency,
        "provider_cash_amount": fact.provider_cash_amount,
        "provider_cash_currency": fact.provider_cash_currency,
        "source_url": fact.source_url,
        "verified": False,
        "notes": fact.notes,
        "batch_id": batch_id,
    }


def _fx_batch_plan(
    query: ProviderQuery,
    records: list[RawProviderRecord],
    normalizer: YahooFxNormalizer,
) -> dict[str, Any] | None:
    if not records:
        return None
    digest = raw_batch_fingerprint(YAHOO_PROVIDER_ID, query, records)
    batch_id = _batch_id(digest, YahooFxNormalizer.version)
    fx_rows: list[dict[str, object]] = []
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, str]] = []
    for record in records:
        result = normalizer.normalize(record)
        if result.disposition == NormalizationDisposition.REJECTED:
            rejected.append(
                {
                    "source_record_id": record.source_record_id or "",
                    "code": result.issues[0].code,
                    "message": result.issues[0].message,
                }
            )
            continue
        facts = result.observation
        if facts is None:
            raise RuntimeError("Accepted Yahoo FX normalization returned no rate observations")
        accepted.append(
            {
                "pair": f"{facts.base_currency}/{facts.quote_currency}",
                "provider_symbol": facts.provider_symbol,
                "rows": len(facts.observations),
                "latest_effective_at": max(
                    item.effective_at for item in facts.observations
                ).isoformat(),
            }
        )
        fx_rows.extend(
            {
                "id": uuid5(NAMESPACE_URL, f"{digest}:{observation.source_ref}"),
                "base_currency": observation.base_currency,
                "quote_currency": observation.quote_currency,
                "rate": observation.rate,
                "data_quality": "PASS",
                "effective_at": observation.effective_at,
                "observed_at": observation.observed_at,
                "recorded_at": record.retrieved_at,
                "provider": YAHOO_PROVIDER_ID,
                "source": str(record.source_url)
                if record.source_url
                else observation.provider_symbol,
                "source_ref": observation.source_ref,
                "actor": "SYSTEM",
                "reason": f"Yahoo {observation.provider_symbol} dated observed exchange rate",
                "batch_id": batch_id,
            }
            for observation in facts.observations
        )
    report: dict[str, Any] = {
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": "yahoo-chart-v8",
        "normalizer_version": YahooFxNormalizer.version,
        "source_digest": digest,
        "query_scope": query.model_dump(mode="json", exclude={"requested_at"}),
        "requested_subjects": len(query.subjects),
        "raw_responses": len(records),
        "accepted_pairs": accepted,
        "rejected_pairs": rejected,
        "fx_observation_rows": len(fx_rows),
    }
    batch_values = {
        "id": batch_id,
        "source_digest": digest,
        "source_kind": "PROVIDER_RESPONSE",
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": "yahoo-chart-v8",
        "normalizer_version": YahooFxNormalizer.version,
        "query_scope": report["query_scope"],
        "source_as_of": None,
        "source_updated_text": None,
        "recorded_at": datetime.now(UTC),
        "provider_summary": {"response_count": len(records), "accepted_pairs": len(accepted)},
        "reconciliation": report,
    }
    return {
        "batch": batch_values,
        "records": records,
        "prices": [],
        "actions": [],
        "fx": fx_rows,
        "report": report,
    }


def _group_market_queries(
    session: Session,
    listing_maps: dict[UUID, YahooListingMapping],
    *,
    default_start: date,
    end_date: date,
    forced_start: date | None,
    corporate_action_overlap_days: int = DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS,
) -> list[tuple[date, list[UUID]]]:
    grouped: dict[date, list[UUID]] = defaultdict(list)
    for listing_id in listing_maps:
        start = forced_start
        if start is None:
            latest_yahoo = session.scalar(
                select(func.max(PriceObservation.market_date)).where(
                    PriceObservation.listing_id == listing_id,
                    PriceObservation.provider == YAHOO_PROVIDER_ID,
                    PriceObservation.price_kind == "DAILY_CLOSE",
                )
            )
            start = latest_yahoo.date() + timedelta(days=1) if latest_yahoo else default_start
            if latest_yahoo is not None:
                action_refresh_start = max(
                    default_start,
                    end_date - timedelta(days=corporate_action_overlap_days),
                )
                start = min(start, action_refresh_start)
        if start <= end_date:
            grouped[start].append(listing_id)
        else:
            # A future end-date still needs a current quote; a one-day range carries it.
            grouped[end_date].append(listing_id)
    return [(start, ids) for start, ids in sorted(grouped.items())]


def _fx_start(
    session: Session, pair: tuple[str, str], default_start: date, forced_start: date | None
) -> date:
    if forced_start is not None:
        return forced_start
    latest = session.scalar(
        select(func.max(FxObservation.effective_at)).where(
            FxObservation.provider == YAHOO_PROVIDER_ID,
            FxObservation.base_currency == pair[0],
            FxObservation.quote_currency == pair[1],
        )
    )
    return latest.date() + timedelta(days=1) if latest else default_start


async def build_provider_import(
    session: Session,
    *,
    provider: YahooFinanceProvider,
    crosswalk: YahooListingCrosswalk,
    end_date: date,
    start_date: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    scope: str = "active",
    listing_keys: set[tuple[str, str]] | None = None,
    fx_pairs: set[tuple[str, str]] | None = None,
    corporate_action_overlap_days: int = DEFAULT_CORPORATE_ACTION_OVERLAP_DAYS,
) -> dict[str, Any]:
    selected, held_ids = active_market_listings(session)
    selection_issues: list[dict[str, str]] = []
    if listing_keys is not None:
        selected_by_key = {
            (listing.venue.casefold(), listing.ticker.casefold()): (listing, security, company)
            for listing, security, company in selected
        }
        selection_issues = [
            {"identity": f"{venue}:{ticker}", "issue": "REQUESTED_LISTING_NOT_ACTIVE_OR_HELD"}
            for venue, ticker in sorted(listing_keys)
            if (venue, ticker) not in selected_by_key
        ]
        selected = [selected_by_key[key] for key in sorted(listing_keys) if key in selected_by_key]
        held_ids.intersection_update(listing.id for listing, _, _ in selected)
    company_lifecycle = {
        event.company_id: event.new_state
        for event in session.scalars(
            select(LifecycleEvent).join(
                CurrentLifecycle, CurrentLifecycle.event_id == LifecycleEvent.id
            )
        )
    }
    active_companies = {
        company.id: (company.name, company_lifecycle[company.id])
        for company in session.scalars(select(Company))
        if company.id in company_lifecycle
        and company_lifecycle[company.id] in {"PORTFOLIO", "WATCHLIST"}
    }
    active_company_ids_with_listing = {
        company.id
        for _, _, company in selected
        if company is not None and company.id in active_companies
    }
    active_companies_without_listing = [
        {"company_id": str(company_id), "company": name, "lifecycle": state}
        for company_id, (name, state) in sorted(
            active_companies.items(), key=lambda item: item[1][0]
        )
        if company_id not in active_company_ids_with_listing
    ]
    listing_maps: dict[UUID, YahooListingMapping] = {}
    unresolved: list[dict[str, str]] = []
    for listing, security, company in selected:
        state = (
            company_lifecycle.get(company.id, "HELD_STANDALONE") if company else "HELD_STANDALONE"
        )
        mapping = yahoo_mapping_for_listing(
            crosswalk,
            venue=listing.venue,
            ticker=listing.ticker,
            currency=listing.currency,
            security_type=security.security_type,
        )
        if mapping is None:
            unresolved.append(
                {
                    "listing_id": str(listing.id),
                    "identity": f"{listing.venue}:{listing.ticker}:{listing.currency}",
                    "security_type": security.security_type,
                    "lifecycle": state,
                    "held": str(listing.id in held_ids).lower(),
                    "issue": "VERIFIED_PROVIDER_MAPPING_MISSING",
                }
            )
            continue
        listing_maps[listing.id] = mapping
    provider.bind_listing_ids(listing_maps)
    default_start = start_date or (end_date - timedelta(days=lookback_days))
    market_plans: list[dict[str, Any]] = []
    market_failures: list[dict[str, object]] = []
    for start, listing_ids in _group_market_queries(
        session,
        listing_maps,
        default_start=default_start,
        end_date=end_date,
        forced_start=start_date,
        corporate_action_overlap_days=corporate_action_overlap_days,
    ):
        subjects = tuple(
            CanonicalSubjectRef(kind=CanonicalSubjectKind.LISTING, id=listing_id)
            for listing_id in listing_ids
        )
        query = ProviderQuery(
            domain=ExternalDataDomain.MARKET_DATA,
            subjects=subjects,
            start_date=start,
            end_date=end_date,
            requested_at=datetime.now(UTC),
        )
        records = list(await provider.fetch(query))
        market_failures.extend(
            {
                "source_record_id": failure.source_record_id,
                "provider_symbol": failure.provider_symbol,
                "message": failure.message,
                "code": failure.code,
                "retryable": failure.retryable,
            }
            for failure in provider.failures
        )
        mapping_by_record = {
            f"LISTING:{listing_id}": (listing_id, listing_maps[listing_id])
            for listing_id in listing_ids
        }
        normalizer = YahooChartNormalizer(
            mapping_by_record, requested_start=start, requested_end=end_date
        )
        plan = _market_batch_plan(query, records, normalizer)
        if plan:
            market_plans.append(plan)

    base_currency, portfolio_pairs = portfolio_fx_requirements(session)
    required_fx_pairs = set(fx_pairs) if fx_pairs is not None else portfolio_pairs
    if fx_pairs is None and base_currency is not None:
        required_fx_pairs.update(
            (mapping.currency, base_currency)
            for mapping in listing_maps.values()
            if mapping.currency != base_currency
        )
    fx_unmapped = sorted(pair for pair in required_fx_pairs if pair not in FX_SYMBOLS)
    fx_plans: list[dict[str, Any]] = []
    fx_failures: list[dict[str, object]] = []
    fx_normalizer = YahooFxNormalizer()
    fx_groups: dict[date, list[tuple[str, str]]] = defaultdict(list)
    fx_pairs_not_due: list[str] = []
    for pair in sorted(required_fx_pairs):
        pair_start = _fx_start(session, pair, default_start, start_date)
        if pair_start > end_date:
            # We already have an observation for this provider business date.
            # Avoid creating an invalid start-after-end query on same-day replays.
            fx_pairs_not_due.append(f"{pair[0]}/{pair[1]}")
        else:
            fx_groups[pair_start].append(pair)
    for start, pairs in sorted(fx_groups.items()):
        query = ProviderQuery(
            domain=ExternalDataDomain.FX,
            subjects=tuple(
                CanonicalSubjectRef(
                    kind=CanonicalSubjectKind.CURRENCY_PAIR,
                    base_currency=base,
                    quote_currency=quote,
                )
                for base, quote in pairs
            ),
            start_date=start,
            end_date=end_date,
            requested_at=datetime.now(UTC),
        )
        records = list(await provider.fetch(query))
        fx_failures.extend(
            {
                "source_record_id": failure.source_record_id,
                "provider_symbol": failure.provider_symbol,
                "message": failure.message,
                "code": failure.code,
                "retryable": failure.retryable,
            }
            for failure in provider.failures
        )
        plan = _fx_batch_plan(query, records, fx_normalizer)
        if plan:
            fx_plans.append(plan)
    return {
        "status": "DRY_RUN",
        "provider_id": YAHOO_PROVIDER_ID,
        "provider_schema_version": "yahoo-chart-v8",
        "end_date": end_date.isoformat(),
        "lookback_start": default_start.isoformat(),
        "scope": scope,
        "selection_issues": selection_issues,
        "active_company_count": len(active_companies),
        "active_company_with_listing_count": len(active_company_ids_with_listing),
        "active_company_without_listing": active_companies_without_listing,
        "company_listing_coverage_by_lifecycle": {
            state: {
                "total": sum(item_state == state for _, item_state in active_companies.values()),
                "with_listing": sum(
                    company_id in active_company_ids_with_listing and item_state == state
                    for company_id, (_, item_state) in active_companies.items()
                ),
            }
            for state in ("PORTFOLIO", "WATCHLIST")
        },
        "selected_listing_count": len(selected),
        "held_listing_count": len(held_ids),
        "verified_listing_mapping_count": len(listing_maps),
        "unresolved_listings": unresolved,
        "market_data_batches": [plan["report"] for plan in market_plans],
        "provider_fetch_failures": market_failures,
        "portfolio_base_currency": base_currency,
        "required_fx_pairs": [f"{base}/{quote}" for base, quote in sorted(required_fx_pairs)],
        "fx_pairs_not_due": fx_pairs_not_due,
        "unmapped_fx_pairs": [f"{base}/{quote}" for base, quote in fx_unmapped],
        "fx_batches": [plan["report"] for plan in fx_plans],
        "fx_fetch_failures": fx_failures,
        "plans": [*market_plans, *fx_plans],
    }


def apply_provider_import(session: Session, report: dict[str, Any]) -> dict[str, Any]:
    plans = report.pop("plans")
    batch_results: list[dict[str, Any]] = []
    totals = {
        "raw_payloads": 0,
        "price_observations": 0,
        "corporate_actions": 0,
        "fx_observations": 0,
    }
    for plan in plans:
        batch_values = plan["batch"]
        existing = session.scalar(
            select(MarketDataBatch).where(
                MarketDataBatch.source_digest == batch_values["source_digest"],
                MarketDataBatch.normalizer_version == batch_values["normalizer_version"],
            )
        )
        if existing:
            batch_results.append(
                {
                    "source_digest": existing.source_digest,
                    "status": "ALREADY_APPLIED",
                    "batch_id": str(existing.id),
                }
            )
            continue
        session.execute(pg_insert(MarketDataBatch).values(**batch_values))
        raw_rows = [_raw_payload_row(batch_values["id"], record) for record in plan["records"]]
        if raw_rows:
            session.execute(pg_insert(ExternalRawPayload).values(raw_rows))
        inserted = {
            "raw_payloads": len(raw_rows),
            "price_observations": 0,
            "corporate_actions": 0,
            "fx_observations": 0,
        }
        price_rows = plan["prices"]
        if price_rows:
            listing_ids = {row["listing_id"] for row in price_rows}
            first_date = min(row["market_date"] for row in price_rows)
            last_date = max(row["market_date"] for row in price_rows)
            superseding_price = aliased(PriceObservation)
            already_superseded = (
                select(superseding_price.id)
                .where(superseding_price.supersedes_observation_id == PriceObservation.id)
                .exists()
            )
            existing_prices = session.execute(
                select(
                    PriceObservation.id,
                    PriceObservation.listing_id,
                    PriceObservation.provider,
                    PriceObservation.provider_symbol,
                    PriceObservation.price_kind,
                    PriceObservation.market_date,
                    PriceObservation.source_ref,
                )
                .where(
                    PriceObservation.listing_id.in_(listing_ids),
                    PriceObservation.provider == price_rows[0]["provider"],
                    PriceObservation.market_date >= first_date,
                    PriceObservation.market_date <= last_date,
                    ~already_superseded,
                )
                .order_by(PriceObservation.recorded_at.desc())
            )
            old_prices: dict[tuple[UUID, str, str, str, datetime], tuple[UUID, str]] = {}
            for existing_price in existing_prices:
                price_key = (
                    existing_price.listing_id,
                    existing_price.provider,
                    existing_price.provider_symbol,
                    existing_price.price_kind,
                    existing_price.market_date,
                )
                old_prices.setdefault(price_key, (existing_price.id, existing_price.source_ref))
            accepted_prices: list[dict[str, Any]] = []
            for row in price_rows:
                price_key = (
                    row["listing_id"],
                    row["provider"],
                    row["provider_symbol"],
                    row["price_kind"],
                    row["market_date"],
                )
                old_price = old_prices.get(price_key)
                if old_price is not None and old_price[1] == row["source_ref"]:
                    continue
                if old_price is not None:
                    row["supersedes_observation_id"] = old_price[0]
                accepted_prices.append(row)
            inserted["price_observations"] = _bulk_insert_rows(
                session,
                PriceObservation,
                accepted_prices,
                "uq_price_observations_source_ref",
            )

        inserted["corporate_actions"] = _bulk_insert_rows(
            session,
            CorporateAction,
            plan["actions"],
            "uq_corporate_actions_source_action_id",
        )

        fx_rows = plan["fx"]
        if fx_rows:
            superseding_fx = aliased(FxObservation)
            already_superseded_fx = (
                select(superseding_fx.id)
                .where(superseding_fx.supersedes_observation_id == FxObservation.id)
                .exists()
            )
            existing_fx = session.execute(
                select(
                    FxObservation.id,
                    FxObservation.base_currency,
                    FxObservation.quote_currency,
                    FxObservation.provider,
                    FxObservation.effective_at,
                    FxObservation.source_ref,
                )
                .where(
                    FxObservation.provider == fx_rows[0]["provider"],
                    ~already_superseded_fx,
                )
                .order_by(FxObservation.recorded_at.desc())
            )
            old_rates: dict[tuple[str, str, str, datetime], tuple[UUID, str]] = {}
            for existing_rate in existing_fx:
                fx_key = (
                    existing_rate.base_currency,
                    existing_rate.quote_currency,
                    existing_rate.provider,
                    existing_rate.effective_at,
                )
                old_rates.setdefault(fx_key, (existing_rate.id, existing_rate.source_ref or ""))
            accepted_fx: list[dict[str, Any]] = []
            for row in fx_rows:
                fx_key = (
                    row["base_currency"],
                    row["quote_currency"],
                    row["provider"],
                    row["effective_at"],
                )
                old_rate = old_rates.get(fx_key)
                if old_rate is not None and old_rate[1] == row["source_ref"]:
                    continue
                if old_rate is not None:
                    row["supersedes_observation_id"] = old_rate[0]
                accepted_fx.append(row)
            inserted["fx_observations"] = _bulk_insert_rows(
                session, FxObservation, accepted_fx, "uq_fx_observations_source_ref"
            )
        final_batch_report = {
            **plan["report"],
            "status": "APPLIED",
            "inserted": inserted,
            "raw_payload_sha256": [record.payload_sha256 for record in plan["records"]],
        }
        session.execute(
            update(MarketDataBatch)
            .where(MarketDataBatch.id == batch_values["id"])
            .values(reconciliation=final_batch_report)
        )
        for total_key in totals:
            totals[total_key] += inserted[total_key]
        batch_results.append(
            {
                "source_digest": batch_values["source_digest"],
                "status": "APPLIED",
                "batch_id": str(batch_values["id"]),
                "inserted": inserted,
            }
        )
    report["status"] = "APPLIED"
    report["persistence"] = {"batches": batch_results, "inserted_totals": totals}
    return report


def _bulk_insert_rows(
    session: Session,
    model: type[PriceObservation] | type[CorporateAction] | type[FxObservation],
    rows: list[dict[str, Any]],
    conflict_constraint: str,
) -> int:
    """Use bounded PostgreSQL multi-value inserts instead of one query per fact."""
    inserted = 0
    for offset in range(0, len(rows), INSERT_CHUNK_SIZE):
        chunk = rows[offset : offset + INSERT_CHUNK_SIZE]
        columns = set().union(*(row.keys() for row in chunk))
        normalized_chunk = [
            {column: row.get(column) for column in sorted(columns)} for row in chunk
        ]
        result = session.execute(
            pg_insert(model)
            .values(normalized_chunk)
            .on_conflict_do_nothing(constraint=conflict_constraint)
            .returning(model.id)
        )
        inserted += len(result.scalars().all())
    return inserted


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Persist provider responses and normalized facts."
    )
    parser.add_argument(
        "--report", type=Path, help="Write the reconciliation JSON report to this path."
    )
    parser.add_argument(
        "--start-date", type=date.fromisoformat, help="Force a full/incremental start date."
    )
    parser.add_argument("--end-date", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--scope", choices=("active",), default="active")
    parser.add_argument(
        "--listing",
        action="append",
        help="Limit the import to an exact canonical VENUE:TICKER listing; may be repeated.",
    )
    args = parser.parse_args(argv)
    if args.lookback_days < 1:
        parser.error("--lookback-days must be positive")
    if args.start_date is not None and args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    listing_keys: set[tuple[str, str]] | None = None
    if args.listing:
        listing_keys = set()
        for value in args.listing:
            parts = value.split(":", maxsplit=1)
            if len(parts) != 2 or not all(parts):
                parser.error("--listing values must use VENUE:TICKER form")
            listing_keys.add((parts[0].casefold(), parts[1].casefold()))
    engine = create_database_engine(Settings())
    if engine is None:
        parser.error("DATABASE_URL is required to resolve canonical listing identities")
    try:
        crosswalk = load_yahoo_crosswalk(CROSSWALK_PATH)
        provider = YahooFinanceProvider(crosswalk)
        with Session(engine) as session:
            report = asyncio.run(
                build_provider_import(
                    session,
                    provider=provider,
                    crosswalk=crosswalk,
                    end_date=args.end_date,
                    start_date=args.start_date,
                    lookback_days=args.lookback_days,
                    scope=args.scope,
                    listing_keys=listing_keys,
                )
            )
            plans = report.pop("plans")
            report["planned_batches"] = len(plans)
            if args.apply:
                session.rollback()
                with session.begin():
                    report = apply_provider_import(session, {**report, "plans": plans})
            else:
                report["status"] = "DRY_RUN"
            output = json.dumps(report, indent=2, sort_keys=True, default=str)
    finally:
        engine.dispose()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    gaps = (
        report.get("unresolved_listings")
        or report.get("provider_fetch_failures")
        or report.get("unmapped_fx_pairs")
        or report.get("fx_fetch_failures")
        or report.get("selection_issues")
        or any(batch.get("rejected_subjects") for batch in report.get("market_data_batches", []))
        or any(batch.get("rejected_pairs") for batch in report.get("fx_batches", []))
    )
    return 0 if not gaps else 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
