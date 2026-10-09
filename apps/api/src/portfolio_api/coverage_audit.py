# ruff: noqa: E501
"""Build the Milestone 6.1 operational coverage matrix from committed receipts.

This audit intentionally reads the frozen workbook inputs and checked-in applied
reconciliation receipts. It does not connect to or mutate PostgreSQL, provider APIs,
or model state. It joins only exact registry tickers and preserves source/quality
states instead of inferring missing values.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from portfolio_api.consensus_estimates import legacy_estimate_import_plan
from portfolio_api.domain.models import RankingType
from portfolio_api.legacy_import import ImportPlan, build_plan

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
RECONCILIATION_ROOT = REPOSITORY_ROOT / "docs" / "reconciliation"
PORTFOLIO_WORKBOOK = REPOSITORY_ROOT / "reference" / "workbook" / "Portfolio_Watchlist.xlsx"
MARKET_WORKBOOK = REPOSITORY_ROOT / "reference" / "workbook" / "Market Data.xlsx"
YAHOO_LISTINGS = REPOSITORY_ROOT / "reference" / "market-data" / "providers" / "yahoo-listings.json"
DEFAULT_JSON = RECONCILIATION_ROOT / "operational-coverage-matrix-2026-10-06.json"
DEFAULT_MARKDOWN = REPOSITORY_ROOT / "docs" / "operational-coverage-audit.md"

PROVIDER_INGESTION = "provider-ingestion-2026-10-05.json"
PROVIDER_MARKET = "provider-market-data-2026-10-05.json"
MODEL_OUTPUTS = "model-output-2026-10-05.json"
MODEL_INVENTORY = "model-migration-inventory-2026-10-05.json"
NATIVE_INPUTS = "native-model-input-import-2026-10-05.json"
LEGACY_ESTIMATES = "consensus-estimates-legacy-2026-10-05.json"
MARKET_IMPORT = "market-data-2026-10-05.json"

STATES = {
    "COMPLETE",
    "MISSING_SOURCE_DATA",
    "IDENTITY_MAPPING",
    "STALE",
    "METHODOLOGY_MISMATCH",
    "MODEL_NOT_NATIVE",
    "RETURN_NOT_COMPARABLE",
    "DATA_CHECK",
    "NOT_APPLICABLE",
}


@dataclass(frozen=True)
class ListingEvidence:
    venue: str
    ticker: str
    currency: str
    security_type: str
    source: str


def _read_json(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((RECONCILIATION_ROOT / name).read_text(encoding="utf-8")),
    )


def _cell(state: str, reason: str, **evidence: Any) -> dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"Unsupported coverage state: {state}")
    return {"state": state, "reason": reason, **evidence}


def _counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def _active_plan(plan: ImportPlan) -> list[Any]:
    active = [
        company
        for company in plan.companies
        if company.lifecycle is not None and company.lifecycle.value in {"PORTFOLIO", "WATCHLIST"}
    ]
    return sorted(
        active, key=lambda row: (0 if row.lifecycle.value == "PORTFOLIO" else 1, row.ticker)
    )


def _score_coverage(plan: ImportPlan, ticker: str) -> dict[str, dict[str, Any]]:
    dimensions = {
        "DURABILITY_10Y",
        "COMPOUNDER_QUALITY",
        "EXECUTION",
        "RISK",
    }
    found = {row.dimension.value: row for row in plan.scores if row.ticker == ticker}
    coverage: dict[str, dict[str, Any]] = {}
    for dimension in sorted(dimensions):
        row = found.get(dimension)
        if row is None:
            coverage[dimension] = _cell(
                "MISSING_SOURCE_DATA",
                "No assessment was present in the imported workbook snapshot.",
            )
        elif row.status.value == "ASSESSED" and row.score is not None:
            coverage[dimension] = _cell(
                "COMPLETE",
                "A source score assessment was imported; this is not a Portfolio Score.",
                score=str(row.score),
                source=row.source,
            )
        else:
            coverage[dimension] = _cell(
                "DATA_CHECK",
                "A source assessment exists but is null/invalid and cannot satisfy a score gate.",
                source_status=row.status.value,
                source=row.source,
            )
    return coverage


def _model_currency_listing_status(
    *,
    model: dict[str, Any] | None,
    native: dict[str, Any] | None,
    listings: list[Any],
) -> dict[str, Any]:
    if model is None:
        return _cell("MISSING_SOURCE_DATA", "No active model tab is recorded for this company.")
    if not listings:
        return _cell(
            "IDENTITY_MAPPING",
            "No canonical listing is mapped, so per-share output cannot be compared to a quote.",
            model_currency=model.get("model_currency"),
        )

    listing_keys = [
        {
            "venue": row.venue,
            "ticker": row.ticker,
            "currency": row.currency,
            "type": row.security_type,
        }
        for row in listings
    ]
    model_currency = model.get("model_currency")
    if native is not None:
        requirement = native.get("listing_requirement", {})
        exact_match = any(
            row.venue == requirement.get("venue")
            and row.ticker == requirement.get("ticker")
            and row.currency == requirement.get("currency")
            for row in listings
        )
        if exact_match and model_currency == requirement.get("currency"):
            return _cell(
                "COMPLETE",
                "Accepted native model records its exact valuation listing and matching model currency.",
                model_currency=model_currency,
                output_contract_currency_status=model.get("contract_currency_status"),
                exact_listing=requirement,
                canonical_listings=listing_keys,
            )
        return _cell(
            "METHODOLOGY_MISMATCH",
            "Native model currency/listing requirements do not match the current canonical listing identity.",
            model_currency=model_currency,
            exact_listing=requirement,
            canonical_listings=listing_keys,
        )

    if not model_currency:
        return _cell(
            "DATA_CHECK",
            "The model currency is not established in the reviewed source inventory.",
            output_contract_currency_status=model.get("contract_currency_status"),
            canonical_listings=listing_keys,
        )

    listing_currencies = sorted({row.currency for row in listings})
    contract_currency_status = model.get("contract_currency_status")
    if model_currency not in listing_currencies:
        return _cell(
            "METHODOLOGY_MISMATCH",
            "No canonical listing has the model currency; no output-to-price conversion is applied.",
            model_currency=model_currency,
            output_contract_currency_status=contract_currency_status,
            canonical_listings=listing_keys,
        )
    if contract_currency_status != "DOCUMENTED":
        return _cell(
            "DATA_CHECK",
            "A source-unit currency candidate exists, but the normalized output contract does not document currency.",
            model_currency=model_currency,
            output_contract_currency_status=contract_currency_status,
            canonical_listings=listing_keys,
        )
    return _cell(
        "DATA_CHECK",
        "Currency matches a canonical listing, but the legacy output snapshot does not identify its exact valuation listing.",
        model_currency=model_currency,
        output_contract_currency_status=contract_currency_status,
        canonical_listings=listing_keys,
    )


def build_matrix(audit_date: date) -> dict[str, Any]:
    plan = build_plan(PORTFOLIO_WORKBOOK, MARKET_WORKBOOK)
    provider_ingestion = _read_json(PROVIDER_INGESTION)
    provider_market = _read_json(PROVIDER_MARKET)
    model_output_receipt = _read_json(MODEL_OUTPUTS)
    model_inventory = _read_json(MODEL_INVENTORY)
    native_receipt = _read_json(NATIVE_INPUTS)
    legacy_estimate_receipt = _read_json(LEGACY_ESTIMATES)
    market_receipt = _read_json(MARKET_IMPORT)
    estimate_reconciliation, estimate_rows = legacy_estimate_import_plan(PORTFOLIO_WORKBOOK)

    source_dates = {
        "audit_date": audit_date.isoformat(),
        "evidence_cutoff": "2026-10-05",
        "database_snapshot": "not queried; no PostgreSQL listener was available in the workspace",
    }
    if plan.portfolio_workbook.sha256 != model_inventory["source"]["sha256"]:
        raise ValueError("Workbook hash does not match the reviewed model inventory.")
    if plan.portfolio_workbook.sha256 != model_output_receipt["workbook_sha256"]:
        raise ValueError("Workbook hash does not match the applied model-output receipt.")
    if estimate_reconciliation["source_sha256"] != plan.portfolio_workbook.sha256:
        raise ValueError("Estimate-history source does not match the active portfolio workbook.")

    active = _active_plan(plan)
    by_ticker = {company.ticker: company for company in active}
    if len(active) != 92 or sum(row.lifecycle.value == "PORTFOLIO" for row in active) != 21:
        raise ValueError(
            "Active workbook population changed; review the audit scope before regeneration."
        )
    if sum(row.lifecycle.value == "WATCHLIST" for row in active) != 71:
        raise ValueError(
            "Active Watchlist population changed; review the audit scope before regeneration."
        )

    listings_by_ticker: dict[str, list[Any]] = defaultdict(list)
    for row in plan.listings:
        listings_by_ticker[row.canonical_ticker].append(row)
    provider_crosswalk = json.loads(YAHOO_LISTINGS.read_text(encoding="utf-8"))
    companies_by_name = {row.name: row for row in active}
    for mapping in provider_crosswalk.get("mappings", []):
        if mapping.get("identity_status") != "READY_FOR_CANONICAL_IMPORT":
            continue
        company = companies_by_name.get(mapping.get("canonical_company_name"))
        if company is None:
            continue
        existing = listings_by_ticker[company.ticker]
        if any(
            row.venue == mapping["venue"] and row.ticker == mapping["ticker"] for row in existing
        ):
            continue
        existing.append(
            ListingEvidence(
                venue=mapping["venue"],
                ticker=mapping["ticker"],
                currency=mapping["currency"],
                security_type=mapping["security_type"],
                source=mapping.get("identity_source_ref", "Yahoo listing crosswalk"),
            )
        )
    provider_listing_keys = {
        (row.get("venue"), row.get("ticker"), row.get("currency"))
        for row in provider_crosswalk.get("mappings", [])
        if row.get("verification_status") == "VERIFIED"
    }
    active_listing_keys = {
        (row.venue, row.ticker, row.currency)
        for ticker in by_ticker
        for row in listings_by_ticker.get(ticker, [])
    }
    if active_listing_keys - provider_listing_keys:
        raise ValueError("An active canonical listing is missing a verified provider crosswalk.")
    rank_rows: dict[str, dict[str, Any]] = {name: {} for name in ("PORTFOLIO", "WATCHLIST")}
    for ranking_type, rows in plan.rankings.items():
        if ranking_type not in {RankingType.PORTFOLIO, RankingType.WATCHLIST}:
            continue
        for rank_entry in rows:
            rank_rows[ranking_type.value][rank_entry.ticker] = rank_entry

    estimate_counts = Counter(str(row["ticker"]).upper() for row in estimate_rows if "value" in row)
    estimate_date = estimate_reconciliation.get("snapshot_date")
    estimate_age_days = (
        (audit_date - date.fromisoformat(estimate_date)).days if estimate_date else None
    )
    output_models = [
        row for row in model_inventory["models"] if row.get("canonical_ticker") in by_ticker
    ]
    models_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in output_models:
        models_by_ticker[str(row["canonical_ticker"])].append(row)
    native_by_ticker = {row["canonical_ticker"]: row for row in native_receipt.get("models", [])}

    fx_by_currency = {
        row["pair"].split("/", 1)[0]: row for row in provider_market["provider"]["fx_pairs"]
    }
    fx_by_currency["EUR"] = {"pair": "EUR/EUR", "observations": 0, "latest_effective_at": None}
    action_summary = provider_market["provider"]["corporate_actions"]
    latest_quote_date = provider_market["provider"]["prices"]["CURRENT_QUOTE"]["latest"]
    history_coverage = provider_market["provider"]["prices"]["DAILY_CLOSE"]
    if (
        provider_market["provider"]["prices"]["CURRENT_QUOTE"]["distinct_listings"]
        != provider_ingestion["selected_listing_count"]
    ):
        raise ValueError(
            "Current quote coverage does not match the applied provider listing selection."
        )
    if history_coverage["distinct_listings"] != provider_ingestion["selected_listing_count"]:
        raise ValueError(
            "Daily history coverage does not match the applied provider listing selection."
        )
    quote_age = (audit_date - date.fromisoformat(latest_quote_date)).days
    fresh_quote = quote_age <= 5
    active_company_count = len(active)
    active_tickers = set(by_ticker)
    no_listing = active_tickers - set(listings_by_ticker)
    source_unmapped_names = {
        row["company"] for row in provider_ingestion.get("active_company_without_listing", [])
    }
    actual_no_listing_names = {by_ticker[ticker].name for ticker in no_listing}
    if source_unmapped_names != actual_no_listing_names:
        raise ValueError(
            "Workbook listing map and provider-ingestion unresolved identities diverged."
        )

    companies: list[dict[str, Any]] = []
    for source_company in active:
        ticker = source_company.ticker
        lifecycle = source_company.lifecycle.value
        listings = listings_by_ticker.get(ticker, [])
        source_models = models_by_ticker.get(ticker, [])
        if len(source_models) > 1:
            raise ValueError(
                f"Multiple current model inventory rows map to {ticker}; audit needs review."
            )
        model = source_models[0] if source_models else None
        native = native_by_ticker.get(ticker)
        rank = rank_rows[lifecycle if lifecycle in rank_rows else "PORTFOLIO"].get(ticker)
        estimate_count = estimate_counts[ticker]
        listing_currencies = sorted({row.currency for row in listings})
        current_model_output_status = (model or {}).get("current_output_status")
        published_fields = (model or {}).get("published_numeric_fields", [])
        irr_available = "expected_cash_flow_irr" in published_fields

        if not listings:
            identity_state = _cell(
                "IDENTITY_MAPPING",
                "No exact canonical listing mapping exists in the applied provider universe.",
                listing_candidates=[],
            )
            current_prices = _cell(
                "IDENTITY_MAPPING",
                "Price observations cannot be joined without a listing identity.",
            )
            history_prices = _cell(
                "IDENTITY_MAPPING", "Historical prices cannot be joined without a listing identity."
            )
            dated_fx = _cell(
                "IDENTITY_MAPPING", "Listing currency is unknown until exact identity is resolved."
            )
            corporate_actions = _cell(
                "IDENTITY_MAPPING",
                "Listing-specific action coverage cannot be attributed without an exact listing.",
            )
        else:
            identity_state = _cell(
                "COMPLETE",
                "An exact canonical venue, ticker, instrument and quote-currency listing mapping exists.",
                listings=[
                    {
                        "venue": row.venue,
                        "ticker": row.ticker,
                        "currency": row.currency,
                        "type": row.security_type,
                    }
                    for row in listings
                ],
            )
            price_state = "COMPLETE" if fresh_quote else "STALE"
            current_prices = _cell(
                price_state,
                "Provider current quote is within the documented five-calendar-day freshness window."
                if fresh_quote
                else "Provider current quote is older than the documented five-calendar-day freshness window.",
                latest_quote_date=latest_quote_date,
                age_days=quote_age,
                fresh_quote_listing_count=provider_market["provider"]["prices"]["CURRENT_QUOTE"][
                    "distinct_listings"
                ],
            )
            history_prices = _cell(
                "COMPLETE",
                "Provider daily-close history covers the reviewed active listing universe; one source-workbook regime row remains a separate DATA_CHECK.",
                first_observation=history_coverage["earliest"],
                latest_observation=history_coverage["latest"],
                rows=history_coverage["rows"],
                distinct_listings=history_coverage["distinct_listings"],
            )
            fx_cells = [fx_by_currency.get(currency) for currency in listing_currencies]
            if all(currency == "EUR" for currency in listing_currencies):
                dated_fx = _cell(
                    "NOT_APPLICABLE",
                    "Listing currency already matches the EUR portfolio base currency.",
                )
            else:
                twd_thin = any(
                    currency != "EUR"
                    and fx_by_currency.get(currency, {}).get("observations", 0) <= 2
                    for currency in listing_currencies
                )
                dated_fx = _cell(
                    "DATA_CHECK" if twd_thin else "COMPLETE",
                    "At least one listing currency has only two dated FX observations; this supports a current point but not historical comparisons."
                    if twd_thin
                    else "Dated listing-currency/EUR history is present for every mapped listing currency.",
                    pairs=[
                        {
                            "pair": row["pair"],
                            "observations": row["observations"],
                            "latest_effective_at": row["latest_effective_at"],
                        }
                        for row in fx_cells
                        if row is not None
                    ],
                )
            corporate_actions = _cell(
                "DATA_CHECK",
                "Provider actions exist but all captured events are unverified; no event does not establish that no action occurred.",
                provider_event_counts=action_summary,
                issuer_verified=False,
                per_listing_counts_in_receipt=False,
            )

        estimate_coverage = (
            _cell(
                "DATA_CHECK",
                "Legacy estimate values are present, but provider, currency and absolute fiscal periods are unknown.",
                legacy_observations=estimate_count,
                source_snapshot_date=estimate_date,
                age_days_at_audit=estimate_age_days,
                freshness_policy="not defined; age alone is not classified STALE",
                primary_provider_observations=0,
            )
            if estimate_count
            else _cell(
                "MISSING_SOURCE_DATA",
                "No usable legacy estimate observations or primary-provider observations are recorded.",
                legacy_observations=0,
                primary_provider_observations=0,
            )
        )

        if model is None:
            model_output = _cell(
                "MISSING_SOURCE_DATA",
                "No model-output inventory row is mapped to this active company.",
            )
            native_status = _cell(
                "MODEL_NOT_NATIVE", "No accepted native model revision is recorded."
            )
            return_status = _cell(
                "MISSING_SOURCE_DATA",
                "No model output is available to assess for return comparability.",
            )
            output_freshness = _cell("NOT_APPLICABLE", "No model output snapshot is available.")
        else:
            output_state = {
                "PUBLISHED": "COMPLETE",
                "DATA_CHECK": "DATA_CHECK",
                "NOT_MAPPED": "IDENTITY_MAPPING",
                "NO_CONTRACT": "MISSING_SOURCE_DATA",
            }.get(str(current_model_output_status), "DATA_CHECK")
            model_output = _cell(
                output_state,
                "Normalized current-contract output is published from the reviewed legacy model tab."
                if output_state == "COMPLETE"
                else "Current model output is unavailable, unresolved or flagged for source/layout review.",
                model_tab=model["model_tab"],
                contract_status=current_model_output_status,
                output_quality=model.get("output_quality"),
                available_numeric_fields=published_fields,
                expected_cash_flow_irr_available=irr_available,
            )
            native_status = (
                _cell(
                    "COMPLETE",
                    "Accepted native inputs and revision passed the tab-specific parity assessment.",
                    model_key=native["model_key"],
                    model_type=native["model_type"],
                    model_currency=native["model_currency"],
                    listing_requirement=native["listing_requirement"],
                    status=native.get("status"),
                )
                if native is not None
                else _cell(
                    "MODEL_NOT_NATIVE",
                    "Legacy output is not an accepted native model revision; its inputs/projections remain legacy-owned or unmigrated.",
                    model_tab=model["model_tab"],
                    migration_status=model.get("migration_status"),
                    methodology_family=model.get("methodology_family"),
                )
            )
            return_status = (
                _cell(
                    "RETURN_NOT_COMPARABLE",
                    "A legacy Expected Cash-Flow IRR is published, but its method has not been bridged to one common shareholder-cash-flow definition.",
                    model_tab=model["model_tab"],
                    methodology_family=model.get("methodology_family"),
                    legacy_return_warning=model_inventory["summary"]["expected_return_semantics"][
                        "legacy_contract_warning"
                    ],
                )
                if irr_available
                else _cell(
                    "MISSING_SOURCE_DATA",
                    "No Expected Cash-Flow IRR value is published for this model tab.",
                    model_tab=model["model_tab"],
                )
            )
            output_freshness = _cell(
                "DATA_CHECK",
                "The legacy current-output contract has no trustworthy effective date; no staleness SLA is defined for model assumptions.",
                observed_at=model_output_receipt.get("observed_at"),
                effective_date=None,
            )

        currency_listing = _model_currency_listing_status(
            model=model, native=native, listings=listings
        )
        if lifecycle == "PORTFOLIO":
            portfolio_rank_row = rank
            portfolio_rank_source = _cell(
                "COMPLETE"
                if portfolio_rank_row and portfolio_rank_row.status.value == "RANKED"
                else "DATA_CHECK",
                "Cached workbook source position exists; it is not a current calculated rank."
                if portfolio_rank_row and portfolio_rank_row.status.value == "RANKED"
                else "Cached source Portfolio Rank position is unavailable.",
                source_status=portfolio_rank_row.status.value if portfolio_rank_row else None,
                source_position=portfolio_rank_row.position if portfolio_rank_row else None,
            )
            portfolio_rank = _cell(
                "MISSING_SOURCE_DATA",
                "Canonical Portfolio Rank is not generated because its Portfolio Score input is not migrated.",
                required_input="Portfolio Score",
                source_snapshot=portfolio_rank_source,
            )
            watchlist_rank_source = _cell(
                "NOT_APPLICABLE", "Company is not in the explicit Watchlist lifecycle."
            )
            watchlist_rank = _cell(
                "NOT_APPLICABLE", "Company is not in the explicit Watchlist lifecycle."
            )
            strategic_target = (
                _cell(
                    "COMPLETE",
                    "An explicit positive strategic company target is present in the accepted source allocation set.",
                    target_weight=str(plan.targets[ticker]),
                    currency=plan.base_currency,
                )
                if ticker in plan.targets
                else _cell(
                    "MISSING_SOURCE_DATA",
                    "No explicit company target allocation is present; absence is not interpreted as a zero target.",
                )
            )
        else:
            portfolio_rank_source = _cell(
                "NOT_APPLICABLE", "Company is not in the Portfolio lifecycle."
            )
            portfolio_rank = _cell("NOT_APPLICABLE", "Company is not in the Portfolio lifecycle.")
            watchlist_rank_row = rank_rows["WATCHLIST"].get(ticker)
            watchlist_rank_source = _cell(
                "COMPLETE"
                if watchlist_rank_row and watchlist_rank_row.status.value == "RANKED"
                else "DATA_CHECK",
                "Cached workbook source position exists; it is not a current calculated rank."
                if watchlist_rank_row and watchlist_rank_row.status.value == "RANKED"
                else "Cached source Watchlist Rank position is unavailable.",
                source_status=watchlist_rank_row.status.value if watchlist_rank_row else None,
                source_position=watchlist_rank_row.position if watchlist_rank_row else None,
            )
            watchlist_rank = _cell(
                "MISSING_SOURCE_DATA",
                "Canonical Watchlist Rank is not generated until expected-return values share a comparable method.",
                required_input="Comparable Expected Cash-Flow IRR",
                source_snapshot=watchlist_rank_source,
            )
            strategic_target = _cell(
                "NOT_APPLICABLE",
                "Strategic company targets are defined for the Portfolio population.",
            )

        score_coverage = _score_coverage(plan, ticker)
        integrity_flags: list[dict[str, str]] = []
        if not listings:
            integrity_flags.append({"state": "IDENTITY_MAPPING", "code": "NO_CANONICAL_LISTING"})
        if estimate_count:
            integrity_flags.append(
                {"state": "DATA_CHECK", "code": "LEGACY_ESTIMATES_UNMAPPED_TO_PROVIDER_PERIODS"}
            )
        if model is not None and model.get("contract_currency_status") != "DOCUMENTED":
            integrity_flags.append(
                {"state": "DATA_CHECK", "code": "OUTPUT_CONTRACT_CURRENCY_UNKNOWN"}
            )
        if irr_available:
            integrity_flags.append(
                {"state": "RETURN_NOT_COMPARABLE", "code": "LEGACY_RETURN_METHOD_NOT_BRIDGED"}
            )
        if native is None:
            integrity_flags.append(
                {"state": "MODEL_NOT_NATIVE", "code": "NATIVE_INPUTS_NOT_ACCEPTED"}
            )
        if lifecycle == "PORTFOLIO" and ticker not in plan.targets:
            integrity_flags.append(
                {"state": "MISSING_SOURCE_DATA", "code": "STRATEGIC_TARGET_ABSENT"}
            )
        if ticker == "TSM" and any(row.currency == "TWD" for row in listings):
            integrity_flags.append(
                {
                    "state": "DATA_CHECK",
                    "code": "TWD_EUR_HISTORY_INSUFFICIENT_FOR_LONGITUDINAL_COMPARISON",
                }
            )
        if ticker == "6146":
            integrity_flags.append(
                {"state": "DATA_CHECK", "code": "LEGACY_MARKET_REGIME_SOURCE_CHECK"}
            )

        companies.append(
            {
                "ticker": ticker,
                "company": source_company.name,
                "lifecycle": lifecycle,
                "universe_identity": _cell(
                    "COMPLETE",
                    "Company identity and lifecycle resolve from the exact Universe Registry ticker.",
                    source=source_company.source,
                ),
                "listing_identity": identity_state,
                "market_prices": {"current_quote": current_prices, "daily_history": history_prices},
                "dated_fx": dated_fx,
                "corporate_actions": corporate_actions,
                "reported_fundamentals": _cell(
                    "MISSING_SOURCE_DATA",
                    "No reviewed SEC CIK mappings or canonical reported-fundamental observations are recorded for the active universe.",
                    active_mapped_companies=0,
                    active_observations=0,
                    source="docs/reported-fundamentals.md; docs/verification.md",
                ),
                "consensus_estimates": estimate_coverage,
                "filings_and_sources": _cell(
                    "MISSING_SOURCE_DATA",
                    "No reviewed SEC identity mappings or canonical source-document rows are recorded.",
                    active_mapped_companies=0,
                    active_source_documents=0,
                    source="docs/verification.md",
                ),
                "model_outputs": model_output,
                "native_model": native_status,
                "model_currency_listing_comparability": currency_listing,
                "return_method_comparability": return_status,
                "strategic_target": strategic_target,
                "portfolio_rank": portfolio_rank,
                "portfolio_rank_source": portfolio_rank_source,
                "watchlist_rank": watchlist_rank,
                "watchlist_rank_source": watchlist_rank_source,
                "portfolio_score_input": _cell(
                    "MISSING_SOURCE_DATA" if lifecycle == "PORTFOLIO" else "NOT_APPLICABLE",
                    "Canonical Portfolio Score is not a migrated source dimension."
                    if lifecycle == "PORTFOLIO"
                    else "Portfolio Score is not an input for this lifecycle.",
                ),
                "source_score_assessments": score_coverage,
                "estimate_momentum": _cell(
                    "MISSING_SOURCE_DATA",
                    "One legacy snapshot is insufficient; no primary-provider point-in-time history or canonical momentum output exists.",
                    primary_provider="not configured",
                    usable_legacy_snapshot_date=estimate_date if estimate_count else None,
                    age_days_at_audit=estimate_age_days if estimate_count else None,
                    freshness_policy="not defined; repeated point-in-time observations are required",
                ),
                "execution_pace": _cell(
                    "MISSING_SOURCE_DATA",
                    "Execution Pace is not implemented; the separate Execution score is not an execution-timing output.",
                    execution_score_state=score_coverage["EXECUTION"]["state"],
                ),
                "output_source_freshness": output_freshness,
                "integrity_flags": integrity_flags,
            }
        )

    status_summary: dict[str, Any] = {}
    domain_keys = [
        "listing_identity",
        "dated_fx",
        "corporate_actions",
        "reported_fundamentals",
        "consensus_estimates",
        "filings_and_sources",
        "model_outputs",
        "native_model",
        "model_currency_listing_comparability",
        "return_method_comparability",
        "strategic_target",
        "portfolio_rank",
        "portfolio_rank_source",
        "watchlist_rank",
        "watchlist_rank_source",
        "estimate_momentum",
        "execution_pace",
    ]
    for domain in domain_keys:
        status_summary[domain] = {}
        for lifecycle in ("PORTFOLIO", "WATCHLIST"):
            selected = [row for row in companies if row["lifecycle"] == lifecycle]
            cells = [row[domain] for row in selected]
            status_summary[domain][lifecycle] = {
                "total": len(selected),
                "states": dict(sorted(Counter(cell["state"] for cell in cells).items())),
            }

    for market_domain in ("current_quote", "daily_history"):
        status_summary[market_domain] = {}
        for lifecycle in ("PORTFOLIO", "WATCHLIST"):
            selected = [row for row in companies if row["lifecycle"] == lifecycle]
            cells = [row["market_prices"][market_domain] for row in selected]
            status_summary[market_domain][lifecycle] = {
                "total": len(selected),
                "states": dict(sorted(Counter(cell["state"] for cell in cells).items())),
            }

    portfolio_valuation = provider_market["portfolio_valuation_reconciliation"]
    source_cutoff = provider_ingestion["end_date"]
    matrix: dict[str, Any] = {
        "schema_version": "1.0.0",
        "audit": {
            **source_dates,
            "title": "Milestone 6.1 operational coverage and integrity audit",
            "scope_order": ["PORTFOLIO", "WATCHLIST"],
            "scope_counts": {
                "PORTFOLIO": sum(row["lifecycle"] == "PORTFOLIO" for row in companies),
                "WATCHLIST": sum(row["lifecycle"] == "WATCHLIST" for row in companies),
                "total": len(companies),
            },
            "database_currentness": "Snapshot based on checked-in applied receipts; live canonical DB was unavailable.",
            "source_snapshot_cutoff": source_cutoff,
        },
        "source_receipts": {
            "portfolio_workbook": {
                "path": "reference/workbook/Portfolio_Watchlist.xlsx",
                "sha256": plan.portfolio_workbook.sha256,
            },
            "market_workbook": {
                "path": "reference/workbook/Market Data.xlsx",
                "sha256": plan.market_workbook.sha256,
                "source_as_of": market_receipt["source_as_of"],
            },
            "applied_provider_ingestion": {
                "path": f"docs/reconciliation/{PROVIDER_INGESTION}",
                "status": provider_ingestion["status"],
                "end_date": provider_ingestion["end_date"],
                "verified_listing_mapping_count": provider_ingestion[
                    "verified_listing_mapping_count"
                ],
            },
            "provider_market_observations": {
                "path": f"docs/reconciliation/{PROVIDER_MARKET}",
                "generated_at": provider_market["generated_at"],
                "current_quotes": provider_market["provider"]["prices"]["CURRENT_QUOTE"],
                "daily_closes": provider_market["provider"]["prices"]["DAILY_CLOSE"],
                "corporate_actions": action_summary,
            },
            "provider_listing_crosswalk": {
                "path": "reference/market-data/providers/yahoo-listings.json",
                "provider_id": provider_crosswalk["provider_id"],
                "verified_at": provider_crosswalk["verified_at"],
                "mapping_count": len(provider_crosswalk.get("mappings", [])),
            },
            "model_output_receipt": {
                "path": f"docs/reconciliation/{MODEL_OUTPUTS}",
                "status": model_output_receipt["status"],
                "observed_at": model_output_receipt["observed_at"],
                "persisted_output_values_compared": model_output_receipt[
                    "persisted_output_values_compared"
                ],
                "persisted_output_value_mismatches": model_output_receipt[
                    "persisted_output_value_mismatches"
                ],
            },
            "model_migration_inventory": {
                "path": f"docs/reconciliation/{MODEL_INVENTORY}",
                "inventory_date": model_inventory["inventory_date"],
            },
            "native_model_input_receipt": {
                "path": f"docs/reconciliation/{NATIVE_INPUTS}",
                "mode": native_receipt["mode"],
                "parity_pass_models": sorted(
                    native_by_ticker for native_by_ticker in native_by_ticker
                ),
            },
            "legacy_estimate_receipt": {
                "path": f"docs/reconciliation/{LEGACY_ESTIMATES}",
                "status": legacy_estimate_receipt["import_result"]["status"],
                "observations": legacy_estimate_receipt["import_result"]["observations_imported"],
                "source_snapshot_date": legacy_estimate_receipt["source_reconciliation"][
                    "snapshot_date"
                ],
            },
            "fundamentals_and_filings_coverage": {
                "reported_fundamentals_source": "docs/reported-fundamentals.md",
                "filing_source": "docs/verification.md",
                "reviewed_sec_cik_mappings": 0,
                "reported_fundamental_observations": 0,
                "source_document_rows": 0,
            },
        },
        "portfolio_valuation": {
            "state": portfolio_valuation["status"],
            "base_currency": portfolio_valuation["currency"],
            "positions": portfolio_valuation["position_count"],
            "valued_positions": portfolio_valuation["valued_position_count"],
            "cash_statuses": portfolio_valuation["cash_statuses"],
            "valuation_gaps": portfolio_valuation["valuation_gaps"],
            "market_value": portfolio_valuation["api_base_market_value"],
        },
        "fx_pairs": sorted(
            [
                {
                    "pair": row["pair"],
                    "observations": row["observations"],
                    "earliest_effective_at": row["earliest_effective_at"],
                    "latest_effective_at": row["latest_effective_at"],
                    "state": "DATA_CHECK" if row["observations"] <= 2 else "COMPLETE",
                }
                for row in provider_market["provider"]["fx_pairs"]
            ],
            key=lambda row: row["pair"],
        ),
        "coverage_summary": status_summary,
        "companies": companies,
        "audit_limitations": [
            "PostgreSQL was not available at the configured local address; current state is reconstructed from checked-in applied receipts and the current workbook snapshots.",
            "Provider price history is summarized per universe in the receipt; per-listing rows are not embedded in that receipt. Exact ticker/listing joins are sourced from the workbook mapping and provider selection report.",
            "Provider corporate-action counts are aggregate only and all recorded events are unverified; absence of an event is not proof of no corporate action.",
            "No freshness SLA is established for model assumptions, filings, reported facts or consensus estimates; STALE is used only for the documented five-day market quote rule.",
            "Model-output currencies are not substituted from listing currencies. Legacy Expected Cash-Flow IRR is preserved but not called comparable without a method-specific bridge.",
        ],
    }
    if active_company_count != matrix["audit"]["scope_counts"]["total"]:
        raise ValueError("Active scope count changed while building the audit.")
    return matrix


def _domain_counts(
    matrix: dict[str, Any], domain: str, lifecycle: str, states: tuple[str, ...]
) -> str:
    summary = matrix["coverage_summary"][domain][lifecycle]["states"]
    return ", ".join(f"{state}: {summary.get(state, 0)}" for state in states)


def render_markdown(matrix: dict[str, Any]) -> str:
    counts = matrix["audit"]["scope_counts"]
    portfolio = counts["PORTFOLIO"]
    watchlist = counts["WATCHLIST"]
    source = matrix["source_receipts"]
    model_output_receipt = source["model_output_receipt"]
    fx = {row["pair"]: row for row in matrix["fx_pairs"]}
    twd = fx.get("TWD/EUR", {})
    rank_portfolio_source = matrix["coverage_summary"]["portfolio_rank_source"]["PORTFOLIO"][
        "states"
    ]
    rank_watchlist_source = matrix["coverage_summary"]["watchlist_rank_source"]["WATCHLIST"][
        "states"
    ]
    rank_portfolio = matrix["coverage_summary"]["portfolio_rank"]["PORTFOLIO"]["states"]
    rank_watchlist = matrix["coverage_summary"]["watchlist_rank"]["WATCHLIST"]["states"]
    currency_portfolio = matrix["coverage_summary"]["model_currency_listing_comparability"][
        "PORTFOLIO"
    ]["states"]
    currency_watchlist = matrix["coverage_summary"]["model_currency_listing_comparability"][
        "WATCHLIST"
    ]["states"]
    native_portfolio = matrix["coverage_summary"]["native_model"]["PORTFOLIO"]["states"]
    native_watchlist = matrix["coverage_summary"]["native_model"]["WATCHLIST"]["states"]
    outputs_portfolio = matrix["coverage_summary"]["model_outputs"]["PORTFOLIO"]["states"]
    outputs_watchlist = matrix["coverage_summary"]["model_outputs"]["WATCHLIST"]["states"]
    returns_portfolio = matrix["coverage_summary"]["return_method_comparability"]["PORTFOLIO"][
        "states"
    ]
    returns_watchlist = matrix["coverage_summary"]["return_method_comparability"]["WATCHLIST"][
        "states"
    ]
    targets = matrix["coverage_summary"]["strategic_target"]["PORTFOLIO"]["states"]
    estimate_portfolio = matrix["coverage_summary"]["consensus_estimates"]["PORTFOLIO"]["states"]
    estimate_watchlist = matrix["coverage_summary"]["consensus_estimates"]["WATCHLIST"]["states"]
    listing_gaps = [
        f"{row['ticker']} ({row['company']})"
        for row in matrix["companies"]
        if row["listing_identity"]["state"] == "IDENTITY_MAPPING"
    ]
    missing_irr = [
        row["ticker"]
        for row in matrix["companies"]
        if row["lifecycle"] == "WATCHLIST"
        and row["return_method_comparability"]["state"] == "MISSING_SOURCE_DATA"
    ]
    model_currency_mismatches = []
    for row in matrix["companies"]:
        comparability = row["model_currency_listing_comparability"]
        if comparability["state"] == "METHODOLOGY_MISMATCH":
            listing_currencies = sorted(
                {item["currency"] for item in comparability.get("canonical_listings", [])}
            )
            model_currency_mismatches.append(
                f"{row['ticker']} ({comparability.get('model_currency')} model / {'+'.join(listing_currencies)} listing)"
            )
    market_state = matrix["portfolio_valuation"]
    return "\n".join(
        [
            "# Milestone 6.1 — Operational coverage and integrity audit",
            "",
            f"Audit date: {matrix['audit']['audit_date']}  ",
            f"Evidence cutoff: {matrix['audit']['evidence_cutoff']}  ",
            f"Scope: {portfolio} Portfolio companies first, then {watchlist} Watchlist companies ({counts['total']} total).",
            "",
            "This is a snapshot-based audit of the checked-in workbook and applied reconciliation receipts through October 5, 2026. The workspace database was not running, so the matrix does not claim a live PostgreSQL read. The full company-level matrix is in [operational-coverage-matrix-2026-10-06.json](reconciliation/operational-coverage-matrix-2026-10-06.json).",
            "",
            "## Coverage by domain",
            "",
            "| Domain | Portfolio | Watchlist |",
            "| --- | ---: | ---: |",
            f"| Exact listing identity | {_domain_counts(matrix, 'listing_identity', 'PORTFOLIO', ('COMPLETE', 'IDENTITY_MAPPING'))} | {_domain_counts(matrix, 'listing_identity', 'WATCHLIST', ('COMPLETE', 'IDENTITY_MAPPING'))} |",
            f"| Current quote | {_domain_counts(matrix, 'current_quote', 'PORTFOLIO', ('COMPLETE', 'STALE', 'IDENTITY_MAPPING'))} | {_domain_counts(matrix, 'current_quote', 'WATCHLIST', ('COMPLETE', 'STALE', 'IDENTITY_MAPPING'))} |",
            f"| Historical daily prices | {_domain_counts(matrix, 'daily_history', 'PORTFOLIO', ('COMPLETE', 'IDENTITY_MAPPING'))} | {_domain_counts(matrix, 'daily_history', 'WATCHLIST', ('COMPLETE', 'IDENTITY_MAPPING'))} |",
            f"| Dated FX (portfolio base EUR) | 8 of 9 required currency crosses have multi-year history; Portfolio valuation {market_state['state']} ({market_state['valued_positions']}/{market_state['positions']} positions) | Same FX source coverage; TWD/EUR has {twd.get('observations', 0)} observations and is DATA_CHECK |",
            "| Corporate actions | DATA_CHECK: provider actions are unverified | DATA_CHECK: provider actions are unverified |",
            f"| Reported fundamentals | 0/{portfolio} | 0/{watchlist} |",
            f"| Consensus history | DATA_CHECK: {estimate_portfolio.get('DATA_CHECK', 0)}/{portfolio}; primary-provider coverage 0 | DATA_CHECK: {estimate_watchlist.get('DATA_CHECK', 0)}/{watchlist}; primary-provider coverage 0 |",
            f"| Filings/source documents | 0/{portfolio} | 0/{watchlist} |",
            f"| Published normalized model outputs | {outputs_portfolio.get('COMPLETE', 0)}/{portfolio} | {outputs_watchlist.get('COMPLETE', 0)}/{watchlist} |",
            f"| Accepted native models | {native_portfolio.get('COMPLETE', 0)}/{portfolio} | {native_watchlist.get('COMPLETE', 0)}/{watchlist} |",
            f"| Model currency/listing comparability | COMPLETE: {currency_portfolio.get('COMPLETE', 0)}, DATA_CHECK: {currency_portfolio.get('DATA_CHECK', 0)} | COMPLETE: {currency_watchlist.get('COMPLETE', 0)}, DATA_CHECK: {currency_watchlist.get('DATA_CHECK', 0)}, IDENTITY_MAPPING: {currency_watchlist.get('IDENTITY_MAPPING', 0)}, METHODOLOGY_MISMATCH: {currency_watchlist.get('METHODOLOGY_MISMATCH', 0)} |",
            f"| Expected IRR values with comparable method | {returns_portfolio.get('RETURN_NOT_COMPARABLE', 0)} published, 0 comparable | {returns_watchlist.get('RETURN_NOT_COMPARABLE', 0)} published, 0 comparable |",
            f"| Strategic targets | {targets.get('COMPLETE', 0)}/{portfolio}; {targets.get('MISSING_SOURCE_DATA', 0)} absent | NOT_APPLICABLE |",
            f"| Cached source rank positions | {rank_portfolio_source.get('COMPLETE', 0)}/{portfolio} | {rank_watchlist_source.get('COMPLETE', 0)}/{watchlist}; {rank_watchlist_source.get('DATA_CHECK', 0)} unavailable |",
            f"| Canonical recalculated ranks | {rank_portfolio.get('COMPLETE', 0)}/{portfolio} calculated; {rank_portfolio.get('MISSING_SOURCE_DATA', 0)} unavailable | {rank_watchlist.get('COMPLETE', 0)}/{watchlist} calculated; {rank_watchlist.get('MISSING_SOURCE_DATA', 0)} unavailable |",
            f"| Estimate Momentum / Execution Pace | 0/{portfolio} / 0/{portfolio} | 0/{watchlist} / 0/{watchlist} |",
            "",
            "Current quote observations are dated October 5, within the documented five-day window as of the audit date. No active listing quote is classified STALE. `6146` retains a legacy source-regime DATA_CHECK; that does not override the provider-backed daily price series. Corporate-action events are counted in aggregate (856 dividends and 22 splits), but the receipts do not give per-company action coverage and all captured events are unverified.",
            "",
            "## Biggest blockers",
            "",
            "1. **Return comparability:** 80 active tabs publish an Expected Cash-Flow IRR, but 0 are certified under one comparable shareholder-cash-flow method. The DCF, owner-cash-flow and financial-company return conventions differ.",
            "2. **Company facts and source documents:** there are no reviewed SEC CIK mappings, reported-fundamental observations or source-document rows in the latest recorded state.",
            "3. **Native model coverage:** only GOOGL and TOST have accepted native inputs with tab-specific parity. The other 90 active outputs are legacy output-only.",
            f"4. **Watchlist identity:** ten Watchlist companies lack exact canonical listings: {', '.join(listing_gaps)}. That blocks price, FX, filing and model/listing joins for those companies.",
            "5. **Estimates and momentum:** 18 companies have one legacy estimate snapshot dated September 12 (24 days before this audit; no freshness SLA is defined); all 67 values are DATA_CHECK, primary-provider coverage is zero, and one snapshot cannot establish Estimate Momentum.",
            "6. **Ranking inputs:** cached source positions exist, but no canonical rank calculation is generated. Portfolio Score is unmigrated; Watchlist expected returns are missing or method-incomparable.",
            "7. **Target completeness:** five Portfolio companies have no explicit strategic target allocation. No zero target is inferred.",
            "",
            "## Highest-leverage remediation batches",
            "",
            f"1. Resolve exact listing identities for {', '.join(listing_gaps)} from issuer/exchange evidence, then add reviewed provider crosswalks. This removes a shared upstream blocker for prices, source mapping and currency comparisons.",
            "2. Map primary filing/fundamental sources for active Portfolio companies by jurisdiction, beginning with exact legal issuer identities and evidence. Use SEC CIKs only where applicable; record unsupported jurisdictions explicitly.",
            "3. Establish a common return-method bridge on representative DCF, owner-cash and residual-income models before comparing IRRs. Then review the active Portfolio DCF cohort and separate financial/bespoke methods under their own parity batches.",
            "4. Select one consensus provider, map provider continuity and currency/listing identity, then backfill repeated point-in-time estimates for Portfolio first. Keep Estimate Momentum unavailable until sufficient history exists.",
            "5. Review explicit targets for the five Portfolio companies without one. After Portfolio Score and comparable Expected IRR inputs are accepted, produce versioned Portfolio/Watchlist rank runs.",
            f"6. Resolve the model/listing currency bridge for {', '.join(model_currency_mismatches)}, backfill TWD/EUR history, and review issuer-confirmed corporate actions before local-ordinary TSM comparisons or action-driven shareholder returns.",
            "",
            "## Expected usability impact",
            "",
            f"The Portfolio can currently value its recorded holdings in EUR and has a published normalized model output for every active Portfolio company. Decision use is still constrained by non-comparable returns, only one accepted native model, absent reported facts/filings, and five missing strategic targets. The Watchlist has published outputs for all 71 companies, but ten lack canonical listings, 12 tabs ({', '.join(missing_irr)}) lack an Expected Cash-Flow IRR, none has a return certified as comparable, and only TOST is native. The identity and source-data batches would improve factual research coverage; the return bridge and rank-input work would improve decision ordering. Estimate Momentum and Execution Pace remain unavailable across both populations.",
            "",
            "## Verification and unresolved data quality",
            "",
            f"The matrix generator checked workbook hashes against the applied model-output and estimate receipts, validated the 21/71 active scope, and joined model, estimate and listing data by exact registry ticker. Applied receipts report model output persistence reconciliation over {model_output_receipt['persisted_output_values_compared']} values with {model_output_receipt['persisted_output_value_mismatches']} mismatches, and portfolio valuation reconciliation {market_state['state']} with {len(market_state['valuation_gaps'])} gaps.",
            "",
            f"Unresolved quality issues are the ten Watchlist listing identities; 51 active output contracts with undocumented model currency; the {', '.join(model_currency_mismatches)} model/listing currency mismatch; legacy model effective dates unavailable; method-specific IRR semantics; 67 consensus values lacking provider/currency/absolute periods; TWD/EUR history limited to two observations; and unverified corporate actions. No remediation or next milestone was started.",
            "",
            "## Rebuild",
            "",
            "```sh",
            "node scripts/uv.mjs run --locked --project apps/api --no-sync python -m portfolio_api.coverage_audit --audit-date 2026-10-06",
            "```",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-date", default="2026-10-06", help="Evidence assessment date (YYYY-MM-DD)."
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    audit_date = date.fromisoformat(args.audit_date)
    matrix = build_matrix(audit_date)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(matrix), encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(args.json_output),
                "markdown": str(args.markdown_output),
                "companies": len(matrix["companies"]),
                "scope": matrix["audit"]["scope_counts"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
