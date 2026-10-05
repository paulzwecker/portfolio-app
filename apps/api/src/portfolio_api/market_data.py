"""Provider-neutral market facts and deterministic legacy Market Data import."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import stdev
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    CorporateAction,
    Listing,
    MarketDataBatch,
    PriceObservation,
    PriceRegimeSnapshot,
    now,
)
from portfolio_api.legacy_import import MARKET_BOOK, Workbook
from portfolio_api.settings import Settings

NAMESPACE = UUID("8f0af02a-2175-49a2-8944-13d10cf5d6f1")
EXCEL_EPOCH = date(1899, 12, 30)
FRESH_DAYS = 5
WORKBOOK_NORMALIZER_VERSION = "legacy-workbook-market-data-v1"


def _date(serial: str | None) -> date | None:
    if not serial:
        return None
    try:
        return EXCEL_EPOCH + timedelta(days=int(Decimal(serial)))
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _stable_id(source_digest: str, source_ref: str) -> UUID:
    return uuid5(NAMESPACE, f"{source_digest}:{source_ref}")


def _cells(row: dict[str, Any]) -> dict[str, str | None]:
    return {key: cell.value for key, cell in row.items()}


def _listing_crosswalk(
    workbook: Workbook, session: Session
) -> tuple[dict[str, Listing], list[dict[str, str]]]:
    by_identity = {
        (item.venue.casefold(), item.ticker.casefold(), (item.currency or "").upper()): item
        for item in session.scalars(select(Listing))
    }
    mapped: dict[str, Listing] = {}
    issues: list[dict[str, str]] = []
    for row_number, row in workbook.rows("Listings", 5):
        values = _cells(row)
        canonical = (values.get("A") or "").strip().upper()
        status = (values.get("K") or "").strip().upper()
        market_symbol = values.get("C")
        venue = values.get("D")
        currency = values.get("E")
        if not canonical:
            continue
        if status != "READY":
            if status:
                issues.append(
                    {
                        "code": "LISTING_NOT_READY",
                        "source": f"Listings!K{row_number}",
                        "ticker": canonical,
                        "status": status,
                    }
                )
            continue
        if not market_symbol or not venue or not currency:
            issues.append(
                {
                    "code": "LISTING_IDENTITY_INCOMPLETE",
                    "source": f"Listings!A{row_number}:O{row_number}",
                    "ticker": canonical,
                }
            )
            continue
        if ":" not in market_symbol:
            issues.append(
                {
                    "code": "INVALID_MARKET_SYMBOL",
                    "source": f"Listings!C{row_number}",
                    "ticker": canonical,
                }
            )
            continue
        provider_venue, market_ticker = market_symbol.split(":", 1)
        if provider_venue.casefold() != venue.casefold():
            issues.append(
                {
                    "code": "LISTING_VENUE_CONFLICT",
                    "source": f"Listings!C{row_number}",
                    "ticker": canonical,
                }
            )
            continue
        # All three fields identify the application listing. Canonical ticker is not a listing key.
        listing = by_identity.get((venue.casefold(), market_ticker.casefold(), currency.upper()))
        if listing is None:
            issues.append(
                {
                    "code": "UNSUPPORTED_LISTING",
                    "source": f"Listings!A{row_number}:O{row_number}",
                    "ticker": canonical,
                    "identity": f"{venue}:{market_ticker} {currency}",
                }
            )
            continue
        if canonical in mapped:
            issues.append(
                {
                    "code": "DUPLICATE_CANONICAL_MAPPING",
                    "source": f"Listings!A{row_number}",
                    "ticker": canonical,
                }
            )
            continue
        mapped[canonical] = listing
    return mapped, issues


def _regime_metrics(closes: list[float]) -> dict[str, float | str | None]:
    if not closes:
        return {
            key: None
            for key in (
                "dma_20",
                "dma_50",
                "dma_200",
                "high_52w",
                "drawdown_52w",
                "vs_dma_20",
                "vs_dma_50",
                "vs_dma_200",
                "return_1m",
                "return_3m",
                "return_6m",
                "realized_vol_20d",
                "trend_state",
                "correction_state",
            )
        }
    close = closes[-1]
    dma = {n: sum(closes[-n:]) / n if len(closes) >= n else None for n in (20, 50, 200)}
    window = closes[-252:]
    high = max(window) if len(window) >= 252 else None
    drawdown = close / high - 1 if high else None
    distance = {n: close / value - 1 if value else None for n, value in dma.items()}
    returns = {
        "return_1m": close / closes[-22] - 1 if len(closes) >= 22 else None,
        "return_3m": close / closes[-64] - 1 if len(closes) >= 64 else None,
        "return_6m": close / closes[-127] - 1 if len(closes) >= 127 else None,
    }
    day_returns = [
        closes[index] / closes[index - 1] - 1
        for index in range(max(1, len(closes) - 20), len(closes))
    ]
    volatility = stdev(day_returns) * math.sqrt(252) if len(day_returns) == 20 else None
    if dma[50] is None or dma[200] is None:
        trend = None
    elif close > dma[50] and dma[50] > dma[200]:
        trend = "STRONG UPTREND" if (returns["return_3m"] or 0) >= 0.10 else "UPTREND"
    elif close > dma[50]:
        trend = "RECOVERING"
    elif dma[50] > dma[200]:
        trend = "WEAKENING"
    else:
        trend = "DOWNTREND"
    if drawdown is None:
        correction = None
    elif drawdown <= -0.20:
        correction = "DEEP CORRECTION"
    elif drawdown <= -0.10:
        correction = "CORRECTION"
    elif drawdown <= -0.05:
        correction = "PULLBACK"
    else:
        correction = "NEAR HIGHS"
    return {
        "dma_20": dma[20],
        "dma_50": dma[50],
        "dma_200": dma[200],
        "high_52w": high,
        "drawdown_52w": drawdown,
        "vs_dma_20": distance[20],
        "vs_dma_50": distance[50],
        "vs_dma_200": distance[200],
        **returns,
        "realized_vol_20d": volatility,
        "trend_state": trend,
        "correction_state": correction,
    }


def _quality(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized == "PASS":
        return "PASS"
    if normalized in {"PASS - VERIFIED FALLBACK", "PASS_VERIFIED_FALLBACK"}:
        return "PASS_VERIFIED_FALLBACK"
    if not normalized:
        return "UNSPECIFIED"
    return "INVALID"


def build_import(session: Session, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workbook = Workbook.read(
        path,
        lambda name: (
            name in {"Listings", "Daily Prices", "Corporate Actions", "Price Regime", "Data QA"}
        ),
    )
    digest = hashlib.sha256(f"market-data:{workbook.sha256}".encode("ascii")).hexdigest()
    mapped, issues = _listing_crosswalk(workbook, session)
    source_listing: dict[str, dict[str, str | None]] = {}
    for _, row in workbook.rows("Listings", 5):
        values = _cells(row)
        key = (values.get("A") or "").strip().upper()
        if key and key in mapped:
            source_listing[key] = values
    observations: list[dict[str, Any]] = []
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    providers: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()
    skipped_rows = 0
    daily_price_rows = workbook.rows("Daily Prices", 4)
    for row_number, row in daily_price_rows:
        values = _cells(row)
        ticker = (values.get("B") or "").strip().upper()
        listing = mapped.get(ticker)
        source = source_listing.get(ticker)
        if listing is None or source is None:
            skipped_rows += 1
            continue
        market_date = _date(values.get("A"))
        provider_symbol = (values.get("I") or "").strip()
        listed_symbol = (source.get("O") or "").strip()
        currency = (values.get("G") or "").strip().upper()
        if not market_date:
            issues.append(
                {
                    "code": "INVALID_MARKET_DATE",
                    "source": f"Daily Prices!A{row_number}",
                    "ticker": ticker,
                }
            )
            skipped_rows += 1
            continue
        if not provider_symbol:
            # Listings!O is the workbook's explicit provider-symbol mapping for this exact listing.
            if listed_symbol:
                provider_symbol = listed_symbol
                issues.append(
                    {
                        "code": "PROVIDER_SYMBOL_FROM_LISTING_MAPPING",
                        "source": f"Daily Prices!I{row_number}",
                        "ticker": ticker,
                        "provider_symbol": listed_symbol,
                    }
                )
            else:
                issues.append(
                    {
                        "code": "PROVIDER_SYMBOL_MISSING",
                        "source": f"Daily Prices!I{row_number}",
                        "ticker": ticker,
                    }
                )
                skipped_rows += 1
                continue
        if provider_symbol != listed_symbol or currency != (listing.currency or "").upper():
            issues.append(
                {
                    "code": "PRICE_IDENTITY_MISMATCH",
                    "source": f"Daily Prices!B{row_number}:I{row_number}",
                    "ticker": ticker,
                    "provider_symbol": provider_symbol,
                }
            )
            skipped_rows += 1
            continue
        provider_close = _decimal(values.get("C"))
        adjusted = _decimal(values.get("D"))
        if adjusted is None or adjusted <= 0:
            issues.append(
                {
                    "code": "INVALID_ADJUSTED_CLOSE",
                    "source": f"Daily Prices!D{row_number}",
                    "ticker": ticker,
                }
            )
            skipped_rows += 1
            continue
        quality = _quality(values.get("N"))
        source_ref = f"market-data:{workbook.sha256}:Daily Prices!A{row_number}:N{row_number}"
        observations.append(
            {
                "id": _stable_id(digest, source_ref),
                "listing_id": listing.id,
                "batch_id": _stable_id(digest, "batch"),
                "market_date": datetime.combine(market_date, time.min, UTC),
                "recorded_at": now(),
                "provider_close": provider_close,
                "split_adjusted_close": adjusted,
                "total_return_close": _decimal(values.get("E")),
                "volume": _decimal(values.get("F")),
                "currency": currency,
                "provider_currency": currency,
                "source_price_multiplier": Decimal(1),
                "provider": (values.get("H") or "UNSPECIFIED").strip(),
                "provider_symbol": provider_symbol,
                "adjustment_basis": (values.get("J") or "Unspecified").strip(),
                "data_quality": quality,
                "source_ref": source_ref,
            }
        )
        series[ticker].append((market_date, float(adjusted)))
        providers[(values.get("H") or "UNSPECIFIED").strip()] += 1
        quality_counts[quality] += 1
    regime_inputs = {key: sorted(value) for key, value in series.items()}
    regime_rows: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []
    state_discrepancies: list[dict[str, str]] = []
    expected_metrics = {
        "E": "dma_20",
        "F": "dma_50",
        "G": "dma_200",
        "H": "high_52w",
        "I": "drawdown_52w",
        "J": "vs_dma_20",
        "K": "vs_dma_50",
        "L": "vs_dma_200",
        "M": "return_1m",
        "N": "return_3m",
        "O": "return_6m",
        "P": "realized_vol_20d",
    }
    regime_count = 0
    compared_metric_values = 0
    compared_states = 0
    regime_source_rows = workbook.rows("Price Regime", 4)
    for row_number, row in regime_source_rows:
        values = _cells(row)
        ticker = (values.get("A") or "").strip().upper()
        listing = mapped.get(ticker)
        if listing is None:
            continue
        points = regime_inputs.get(ticker, [])
        as_of = _date(values.get("B"))
        metrics = _regime_metrics([price for day, price in points if as_of is None or day <= as_of])
        for column, metric in expected_metrics.items():
            source_value = _decimal(values.get(column))
            calculated = metrics.get(metric)
            if source_value is None or not isinstance(calculated, float):
                continue
            compared_metric_values += 1
            delta = abs(Decimal(str(calculated)) - source_value)
            if delta > Decimal("0.0000001"):
                discrepancies.append(
                    {
                        "ticker": ticker,
                        "metric": metric,
                        "source": str(source_value),
                        "calculated": str(calculated),
                        "absolute_delta": str(delta),
                    }
                )
        for column, metric in (("Q", "trend_state"), ("R", "correction_state")):
            source_state = values.get(column)
            calculated_state = metrics.get(metric)
            if source_state and calculated_state:
                compared_states += 1
                if source_state.strip().upper() != str(calculated_state).upper():
                    state_discrepancies.append(
                        {
                            "ticker": ticker,
                            "metric": metric,
                            "source": source_state.strip(),
                            "calculated": str(calculated_state),
                        }
                    )
        if not as_of:
            issues.append(
                {
                    "code": "REGIME_DATE_MISSING",
                    "source": f"Price Regime!B{row_number}",
                    "ticker": ticker,
                }
            )
            continue
        quality_value = (values.get("T") or "").strip().upper()
        regime_quality = (
            "PASS"
            if quality_value == "PASS"
            else "DATA_CHECK"
            if quality_value == "DATA CHECK"
            else "UNSPECIFIED"
        )
        source_ref = f"market-data:{workbook.sha256}:Price Regime!A{row_number}:V{row_number}"
        record: dict[str, Any] = {
            "id": _stable_id(digest, source_ref),
            "listing_id": listing.id,
            "batch_id": _stable_id(digest, "batch"),
            "as_of": datetime.combine(as_of, time.min, UTC),
            "provider_close": _decimal(values.get("C")),
            "split_adjusted_close": _decimal(values.get("D")),
            "trend_state": metrics.get("trend_state") or values.get("Q"),
            "correction_state": metrics.get("correction_state") or values.get("R"),
            # This source label is preserved as observed: its full decision rule is not specified.
            "regime": values.get("S"),
            "data_quality": regime_quality,
            "quality_reason": values.get("V") if regime_quality != "PASS" else None,
            "methodology_version": "legacy-cache-v1; numeric-metrics-v1",
            "source_ref": source_ref,
        }
        record.update(
            {
                key: Decimal(str(value)) if isinstance(value, float) else None
                for key, value in metrics.items()
                if key not in {"trend_state", "correction_state"}
            }
        )
        if regime_quality == "DATA_CHECK":
            # Preserve source values that could not be recomputed due to incomplete history,
            # while keeping their quality state and source note explicit.
            for column, metric in expected_metrics.items():
                if record.get(metric) is None:
                    source_metric = _decimal(values.get(column))
                    if source_metric is not None:
                        record[metric] = source_metric
        regime_rows.append(record)
        regime_count += 1
    actions: list[dict[str, Any]] = []
    corporate_action_rows = workbook.rows("Corporate Actions", 4)
    for row_number, row in corporate_action_rows:
        values = _cells(row)
        ticker = (values.get("C") or "").strip().upper()
        listing = mapped.get(ticker)
        if listing is None:
            continue
        effective = values.get("B")
        try:
            effective_date = date.fromisoformat(effective or "")
        except ValueError:
            issues.append(
                {
                    "code": "CORPORATE_ACTION_DATE_INVALID",
                    "source": f"Corporate Actions!B{row_number}",
                    "ticker": ticker,
                }
            )
            continue
        ratio = values.get("E") or ""
        split_ratio: Decimal | None = None
        if ":" in ratio:
            try:
                left, right = ratio.split(":", 1)
                split_ratio = Decimal(left) / Decimal(right)
            except (InvalidOperation, ZeroDivisionError):
                pass
        action_id = (values.get("A") or f"row-{row_number}").strip()
        source_ref = f"market-data:{workbook.sha256}:Corporate Actions!A{row_number}:P{row_number}"
        actions.append(
            {
                "id": _stable_id(digest, source_ref),
                "listing_id": listing.id,
                "source_action_id": action_id,
                "effective_date": datetime.combine(effective_date, time.min, UTC),
                "action_type": (values.get("D") or "UNSPECIFIED").strip(),
                "ratio_before": Decimal(1) if split_ratio else None,
                "ratio_after": split_ratio,
                "old_symbol": values.get("F"),
                "new_symbol": values.get("G"),
                "old_exchange": values.get("H"),
                "new_exchange": values.get("I"),
                "currency_before": values.get("J"),
                "currency_after": values.get("K"),
                "source_url": values.get("N"),
                "verified": (values.get("O") or "").strip() == "1",
                "notes": values.get("P"),
                "batch_id": _stable_id(digest, "batch"),
            }
        )
    as_ofs = [_date(_cells(row).get("B")) for _, row in workbook.rows("Price Regime", 4)]
    as_of = max((item for item in as_ofs if item), default=date.today())
    qa_timestamp = next(
        (
            _cells(row).get("F")
            for _, row in workbook.rows("Data QA", 4)
            if (_cells(row).get("A") or "").strip() == "Unique listing keys"
        ),
        None,
    )
    report: dict[str, Any] = {
        "status": "DRY_RUN",
        "normalizer_version": WORKBOOK_NORMALIZER_VERSION,
        "workbook_sha256": workbook.sha256,
        "source_digest": digest,
        "source_as_of": as_of.isoformat(),
        "source_updated_text": qa_timestamp,
        "listed_identities_matched": len(mapped),
        "daily_price_source_rows": len(daily_price_rows),
        "observations_ready": len(observations),
        "observation_rows_skipped": skipped_rows,
        "price_regime_source_rows": len(regime_source_rows),
        "price_regime_rows": regime_count,
        "corporate_action_source_rows": len(corporate_action_rows),
        "corporate_actions": len(actions),
        "providers": dict(providers),
        "price_quality": dict(quality_counts),
        "calculated_metric_reconciliation": {
            "compared_metric_values": compared_metric_values,
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies[:50],
            "compared_states": compared_states,
            "state_discrepancy_count": len(state_discrepancies),
            "state_discrepancies": state_discrepancies[:50],
        },
        "unresolved_issues": issues,
        "notes": [
            "Daily rows use the Listings exact venue/ticker/currency and provider-symbol mapping.",
            "Blank source quality remains UNSPECIFIED; it is not upgraded to PASS.",
            "The Price Regime label is retained as an observed legacy value because its full "
            "classification rule is not documented.",
            "No FX observations are present in the Market Data workbook.",
        ],
    }
    batch_id = _stable_id(digest, "batch")
    batch_values = {
        "id": batch_id,
        "source_digest": digest,
        "normalizer_version": WORKBOOK_NORMALIZER_VERSION,
        "workbook_sha256": workbook.sha256,
        "source_as_of": datetime.combine(as_of, time.min, UTC),
        "source_updated_text": qa_timestamp,
        "recorded_at": now(),
        "provider_summary": {"providers": dict(providers), "quality": dict(quality_counts)},
        "reconciliation": report,
    }
    return report, [batch_values, *observations, *actions, *regime_rows]


def apply_import(
    session: Session, report: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    existing = session.scalar(
        select(MarketDataBatch).where(
            MarketDataBatch.source_digest == report["source_digest"],
            MarketDataBatch.normalizer_version == WORKBOOK_NORMALIZER_VERSION,
        )
    )
    if existing:
        saved = existing.reconciliation
        return {
            **(saved if isinstance(saved, dict) else report),
            "status": "ALREADY_APPLIED",
            "batch_id": str(existing.id),
        }
    batch = rows[0]
    report = {**report, "status": "APPLIED"}
    batch = {**batch, "reconciliation": report}
    session.execute(insert(MarketDataBatch), [batch])
    observations = [row for row in rows[1:] if "provider_symbol" in row]
    actions = [row for row in rows[1:] if "source_action_id" in row]
    regimes = [row for row in rows[1:] if "methodology_version" in row]
    for group, model in (
        (observations, PriceObservation),
        (actions, CorporateAction),
        (regimes, PriceRegimeSnapshot),
    ):
        for offset in range(0, len(group), 2000):
            session.execute(insert(model), group[offset : offset + 2000])
    expected_counts = {
        "price_observations": len(observations),
        "corporate_actions": len(actions),
        "price_regime_snapshots": len(regimes),
    }
    table_counts = (
        ("price_observations", PriceObservation),
        ("corporate_actions", CorporateAction),
        ("price_regime_snapshots", PriceRegimeSnapshot),
    )
    stored_counts = {
        table_name: int(
            session.scalar(
                select(func.count()).select_from(model).where(model.batch_id == batch["id"])
            )
            or 0
        )
        for table_name, model in table_counts
    }
    report["persistence_reconciliation"] = {
        "status": "MATCHED" if expected_counts == stored_counts else "MISMATCH",
        "expected": expected_counts,
        "stored": stored_counts,
    }
    if expected_counts != stored_counts:
        raise RuntimeError("Market-data batch count did not match inserted observations")
    return {
        **report,
        "batch_id": str(batch["id"]),
        "imported": expected_counts,
    }


def run_cli(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook", type=Path, default=repo / "reference" / "workbook" / MARKET_BOOK
    )
    parser.add_argument(
        "--apply", action="store_true", help="Persist the verified workbook snapshot."
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    engine = create_database_engine(Settings())
    if engine is None:
        parser.error("DATABASE_URL is required to resolve exact listing identities")
    try:
        with Session(engine) as session:
            report, rows = build_import(session, args.workbook)
            session.rollback()
            if args.apply:
                parity = report["calculated_metric_reconciliation"]
                if parity["discrepancy_count"] or parity["state_discrepancy_count"]:
                    raise ValueError(
                        "Workbook price-regime outputs do not reconcile; import was not applied"
                    )
                with session.begin():
                    report = apply_import(session, report, rows)
            output = json.dumps(report, indent=2, sort_keys=True)
    finally:
        engine.dispose()
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    parity = report["calculated_metric_reconciliation"]
    failed_parity = parity["discrepancy_count"] or parity["state_discrepancy_count"]
    persistence = report.get("persistence_reconciliation", {}).get("status", "MATCHED")
    return 0 if not failed_parity and persistence == "MATCHED" else 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
