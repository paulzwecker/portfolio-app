"""Import only the documented source fields consumed by canonical Research Rank."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import Company, Listing, ResearchPriorityInput, Security, now
from portfolio_api.legacy_import import MAIN_BOOK, Cell, Workbook, _stable_id
from portfolio_api.settings import Settings


def _source_ref(workbook: Workbook, sheet: str, cell: str) -> str:
    return f"{workbook.path.name}:{sheet}!{cell}#sha256:{workbook.sha256}"


def _cell_value(row: dict[str, Cell], column: str) -> str | None:
    cell = row.get(column)
    return cell.value if cell is not None else None


def research_priority_rows(workbook: Workbook) -> list[dict[str, Any]]:
    """Parse Registry candidate tiers and the linked persistent priority seed."""
    seed_rows: dict[str, list[tuple[Decimal | None, str, str | None]]] = defaultdict(list)
    for row_number, row in workbook.rows("Candidate Ranking", 2):
        ticker = _cell_value(row, "B") or ""
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        seed_cell = row.get("A")
        seed_row_source = _source_ref(workbook, "Candidate Ranking", f"A{row_number}")
        raw_seed = seed_cell.value if seed_cell is not None else None
        if raw_seed is None or raw_seed == "":
            seed_rows[ticker].append((None, seed_row_source, ""))
            continue
        try:
            value = Decimal(raw_seed)
        except (InvalidOperation, TypeError):
            seed_rows[ticker].append((None, seed_row_source, "Priority seed is not numeric."))
            continue
        reason = "Priority seed cannot be negative." if value < 0 else None
        seed_rows[ticker].append((value, seed_row_source, reason))

    registry_rows: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row_number, row in workbook.rows("Universe Registry", 5):
        ticker = _cell_value(row, "A") or ""
        bucket = _cell_value(row, "C") or ""
        ticker = ticker.strip().upper()
        if ticker and bucket.strip().casefold() in {"candidate - high", "candidate - low"}:
            registry_rows[ticker].append(
                (
                    bucket.strip(),
                    _source_ref(workbook, "Universe Registry", f"C{row_number}"),
                )
            )

    result: list[dict[str, Any]] = []
    for ticker, buckets in sorted(registry_rows.items()):
        if len(buckets) != 1:
            result.append(
                {
                    "ticker": ticker,
                    "quality": "DATA_CHECK",
                    "reason": "Canonical ticker occurs more than once in Universe Registry.",
                    "source_ref": buckets[0][1],
                }
            )
            continue
        bucket, bucket_source = buckets[0]
        tier = "HIGH" if bucket.casefold() == "candidate - high" else "LOW"
        seeds = seed_rows.get(ticker, [])
        priority_seed: Decimal | None = None
        resolved_seed_source: str | None = None
        quality = "PASS"
        quality_reason: str | None = None
        if len(seeds) > 1:
            values = {item[0] for item in seeds}
            if len(values) > 1:
                quality = "DATA_CHECK"
                quality_reason = "Persistent priority seed has conflicting source rows."
            else:
                priority_seed, resolved_seed_source, seed_issue = seeds[0]
                if seed_issue:
                    quality = "DATA_CHECK"
                    quality_reason = seed_issue
        elif seeds:
            priority_seed, resolved_seed_source, seed_issue = seeds[0]
            if seed_issue:
                quality = "DATA_CHECK"
                quality_reason = seed_issue
        result.append(
            {
                "ticker": ticker,
                "candidate_tier": tier,
                "priority_seed": priority_seed,
                "input_quality": quality,
                "quality_reason": quality_reason,
                "bucket_source_ref": bucket_source,
                "priority_seed_source_ref": resolved_seed_source,
                "source_digest": workbook.sha256,
            }
        )
    return result


def _company_for_ticker(session: Session, ticker: str) -> Company | None:
    deterministic = session.get(Company, _stable_id("company", ticker))
    if deterministic is not None:
        return deterministic
    company_ids = set(
        session.scalars(
            select(Security.company_id)
            .join(Listing, Listing.security_id == Security.id)
            .where(Listing.ticker == ticker, Security.company_id.is_not(None))
        )
    )
    if len(company_ids) != 1:
        return None
    return session.get(Company, next(iter(company_ids)))


def import_research_priority_inputs(
    session: Session, workbook: Workbook, *, apply: bool, observed_at: datetime
) -> dict[str, Any]:
    rows = research_priority_rows(workbook)
    inserted = 0
    already_present = 0
    unresolved: list[dict[str, str]] = []
    data_checks: list[dict[str, str]] = []
    for row in rows:
        if row.get("quality") == "DATA_CHECK":
            data_checks.append(
                {"ticker": row["ticker"], "reason": row["reason"], "source_ref": row["source_ref"]}
            )
            continue
        if row.get("input_quality") == "DATA_CHECK":
            data_checks.append(
                {
                    "ticker": row["ticker"],
                    "reason": row["quality_reason"] or "Research priority input requires review.",
                    "source_ref": row["priority_seed_source_ref"] or row["bucket_source_ref"],
                }
            )
        company = _company_for_ticker(session, row["ticker"])
        if company is None:
            unresolved.append(
                {
                    "ticker": row["ticker"],
                    "reason": "No unique canonical company identity maps to this source ticker.",
                }
            )
            continue
        existing = session.scalar(
            select(ResearchPriorityInput).where(
                ResearchPriorityInput.company_id == company.id,
                ResearchPriorityInput.source_digest == workbook.sha256,
            )
        )
        if existing is not None:
            already_present += 1
            continue
        if apply:
            session.add(
                ResearchPriorityInput(
                    id=_stable_id("research-priority-input", f"{workbook.sha256}:{row['ticker']}"),
                    company_id=company.id,
                    canonical_ticker=row["ticker"],
                    candidate_tier=row["candidate_tier"],
                    priority_seed=row["priority_seed"],
                    input_quality=row["input_quality"],
                    quality_reason=row["quality_reason"],
                    source_digest=workbook.sha256,
                    bucket_source_ref=row["bucket_source_ref"],
                    priority_seed_source_ref=row["priority_seed_source_ref"],
                    recorded_at=observed_at,
                    actor="IMPORT",
                )
            )
            inserted += 1
    if apply:
        session.flush()
    return {
        "status": "APPLIED" if apply else "DRY_RUN",
        "workbook": workbook.path.name,
        "workbook_sha256": workbook.sha256,
        "observed_at": observed_at.isoformat(),
        "effective_time_policy": (
            "The workbook does not document when candidate buckets or seeds became effective. "
            "Records are usable only at or after this actual import time."
        ),
        "candidate_source_rows": len(rows),
        "would_insert": max(
            0,
            len(rows)
            - already_present
            - len(unresolved)
            - len([r for r in rows if r.get("quality") == "DATA_CHECK"]),
        )
        if not apply
        else 0,
        "inserted": inserted,
        "already_present": already_present,
        "unresolved_identity_count": len(unresolved),
        "unresolved_identities": unresolved,
        "data_check_count": len(data_checks),
        "data_checks": data_checks,
        "missing_priority_seed_count": sum(row.get("priority_seed") is None for row in rows),
        "fallback_policy": (
            "A blank seed uses the documented workbook value 50000 and is flagged per rank entry."
        ),
    }


def run_cli(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook", type=Path, default=repo / "reference" / "workbook" / MAIN_BOOK
    )
    parser.add_argument(
        "--apply", action="store_true", help="Persist inputs; dry-run is the default."
    )
    parser.add_argument("--observed-at", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    workbook = Workbook.read(
        args.workbook, lambda name: name in {"Universe Registry", "Candidate Ranking"}
    )
    observed_at = args.observed_at or now()
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        parser.error("--observed-at must include a timezone")
    engine = create_database_engine(Settings())
    if engine is None:
        parser.error("Configure DATABASE_URL and run database migrations before importing.")
    try:
        with Session(engine) as session, session.begin():
            report = import_research_priority_inputs(
                session, workbook, apply=args.apply, observed_at=observed_at.astimezone(UTC)
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["data_check_count"] else 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli())
