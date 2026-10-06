"""Canonical Research Rank from the documented legacy Research Sort Key."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    LifecycleEvent,
    RankingEntryStatus,
    ResearchPriorityInput,
)

LEGACY_HIGH_BASE = Decimal("200000")
LEGACY_LOW_BASE = Decimal("100000")
LEGACY_DEFAULT_PRIORITY_SEED = Decimal("50000")
RESEARCH_RANK_CONTEXT_VERSION = "research-rank-inputs-v1"


def research_sort_key(candidate_tier: str, priority_seed: Decimal | None) -> tuple[Decimal, bool]:
    """Reproduce Universe Registry!Q, including its explicit blank-seed fallback."""
    if candidate_tier not in {"HIGH", "LOW"}:
        raise ValueError("Research Rank requires the documented Candidate High/Low tier")
    used_fallback = priority_seed is None
    seed = LEGACY_DEFAULT_PRIORITY_SEED if used_fallback else priority_seed
    if seed is None or seed < 0:
        raise ValueError("Research priority seed must be nonnegative")
    tier_base = LEGACY_HIGH_BASE if candidate_tier == "HIGH" else LEGACY_LOW_BASE
    return tier_base - seed, used_fallback


def research_rank_positions(rows: list[tuple[UUID, str, Decimal]]) -> dict[UUID, int]:
    ordered = sorted(rows, key=lambda row: (-row[2], row[1]))
    return {
        company_id: position
        for position, (company_id, _ticker, _key) in enumerate(ordered, start=1)
    }


def build_research_rank_entries(
    session: Session, companies: list[Company], as_of: datetime
) -> list[tuple[UUID, RankingEntryStatus, str, int | None, dict[str, Any] | None]]:
    company_ids = {company.id for company in companies}
    if not company_ids:
        return []
    cutoff = as_of.astimezone(UTC)
    lifecycle_by_company: dict[UUID, str] = {}
    for company_id, observed_lifecycle in session.execute(
        select(LifecycleEvent.company_id, LifecycleEvent.new_state)
        .where(LifecycleEvent.effective_at <= cutoff, LifecycleEvent.recorded_at <= cutoff)
        .order_by(LifecycleEvent.sequence.desc())
    ):
        lifecycle_by_company.setdefault(company_id, observed_lifecycle)

    profile_rows = list(
        session.scalars(
            select(ResearchPriorityInput)
            .where(
                ResearchPriorityInput.company_id.in_(company_ids),
                ResearchPriorityInput.recorded_at <= cutoff,
            )
            .order_by(
                ResearchPriorityInput.company_id,
                ResearchPriorityInput.recorded_at.desc(),
                ResearchPriorityInput.id,
            )
        )
    )
    profiles: dict[UUID, list[ResearchPriorityInput]] = {}
    for profile in profile_rows:
        profiles.setdefault(profile.company_id, []).append(profile)

    statuses: dict[UUID, tuple[RankingEntryStatus, str, int | None, dict[str, Any] | None]] = {}
    sortable: list[tuple[UUID, str, Decimal]] = []
    used_profiles: dict[UUID, dict[str, Any]] = {}
    for company in companies:
        company_lifecycle = lifecycle_by_company.get(company.id)
        if company_lifecycle is None:
            statuses[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "Point-in-time lifecycle is unavailable; Research Rank eligibility cannot "
                "be established.",
                None,
                _research_snapshot(None, None, "MISSING", "Lifecycle is unavailable at this run."),
            )
            continue
        if company_lifecycle != "CANDIDATE":
            statuses[company.id] = (
                RankingEntryStatus.NOT_ELIGIBLE,
                "Research Rank covers explicit CANDIDATE lifecycle only; investment "
                "lifecycle is unchanged.",
                None,
                None,
            )
            continue

        candidates = profiles.get(company.id, [])
        if not candidates:
            statuses[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "Candidate-tier source input is not available as of this run.",
                None,
                _research_snapshot(
                    company_lifecycle,
                    None,
                    "MISSING",
                    "No imported Candidate - High/Low source tier was recorded before this run.",
                ),
            )
            continue
        profile = candidates[0]
        same_recorded_time = [
            item for item in candidates if item.recorded_at == profile.recorded_at
        ]
        distinct_values = {
            (item.candidate_tier, item.priority_seed, item.input_quality, item.canonical_ticker)
            for item in same_recorded_time
        }
        if len(distinct_values) > 1:
            statuses[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "Conflicting candidate research inputs share the latest recorded timestamp.",
                None,
                _research_snapshot(
                    company_lifecycle,
                    None,
                    "DATA_CHECK",
                    "Conflicting source profile revisions require reconciliation.",
                    profile=profile,
                ),
            )
            continue
        if profile.input_quality != "PASS":
            statuses[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                profile.quality_reason or "Candidate research source inputs need a data check.",
                None,
                _research_snapshot(
                    company_lifecycle,
                    None,
                    "DATA_CHECK",
                    profile.quality_reason
                    or "Imported research source input has a data-quality issue.",
                    profile=profile,
                ),
            )
            continue
        try:
            key, used_fallback = research_sort_key(profile.candidate_tier, profile.priority_seed)
        except ValueError as error:
            statuses[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                str(error),
                None,
                _research_snapshot(
                    company_lifecycle, None, "DATA_CHECK", str(error), profile=profile
                ),
            )
            continue
        snapshot = _research_snapshot(
            company_lifecycle,
            key,
            "AVAILABLE",
            (
                "Research Sort Key uses the source's documented 50000 fallback because the "
                "persistent seed is blank."
                if used_fallback
                else "Research Sort Key uses the imported persistent priority seed."
            ),
            profile=profile,
            used_fallback=used_fallback,
        )
        sortable.append((company.id, profile.canonical_ticker, key))
        used_profiles[company.id] = snapshot

    duplicate_tickers = {
        ticker for ticker, count in Counter(row[1] for row in sortable).items() if count > 1
    }
    unique_rows: list[tuple[UUID, str, Decimal]] = []
    for company_id, ticker, key in sortable:
        if ticker in duplicate_tickers:
            statuses[company_id] = (
                RankingEntryStatus.DATA_CHECK,
                f"Canonical research ticker {ticker} is duplicated; the documented "
                "tie-break is ambiguous.",
                None,
                used_profiles[company_id],
            )
        else:
            unique_rows.append((company_id, ticker, key))
    positions = research_rank_positions(unique_rows)
    for company_id, position in positions.items():
        statuses[company_id] = (
            RankingEntryStatus.RANKED,
            "Ranked by the documented Research Sort Key descending, then canonical ticker "
            "ascending. This orders research attention only; it does not change lifecycle "
            "or investment state.",
            position,
            used_profiles[company_id],
        )
    return [
        (
            company.id,
            *statuses.get(
                company.id,
                (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    "Research Rank status could not be established.",
                    None,
                    None,
                ),
            ),
        )
        for company in companies
    ]


def _research_snapshot(
    lifecycle: str | None,
    sort_key: Decimal | None,
    input_quality: str,
    context_note: str,
    *,
    profile: ResearchPriorityInput | None = None,
    used_fallback: bool = False,
) -> dict[str, Any]:
    value = s.ResearchRankInputSnapshot.model_validate(
        {
            "context_version": RESEARCH_RANK_CONTEXT_VERSION,
            "lifecycle": lifecycle,
            "candidate_tier": profile.candidate_tier if profile else None,
            "priority_seed": profile.priority_seed if profile else None,
            "legacy_default_priority_seed": (
                LEGACY_DEFAULT_PRIORITY_SEED if profile and profile.priority_seed is None else None
            ),
            "used_legacy_default": used_fallback,
            "sort_key": sort_key,
            "input_quality": input_quality,
            "source_digest": profile.source_digest if profile else None,
            "bucket_source_ref": profile.bucket_source_ref if profile else None,
            "priority_seed_source_ref": profile.priority_seed_source_ref if profile else None,
            "context_note": context_note,
        }
    )
    return value.model_dump(mode="json")
