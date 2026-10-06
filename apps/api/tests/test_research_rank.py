from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import (
    Company,
    Lifecycle,
    RankingEntry,
    RankingEntryStatus,
    RankingType,
    ResearchPriorityInput,
)
from portfolio_api.domain.seed import seed
from portfolio_api.legacy_import import MAIN_BOOK, Cell, Workbook
from portfolio_api.research_priority_import import research_priority_rows
from portfolio_api.research_ranking import research_rank_positions, research_sort_key


def _cell_value(row: dict[str, Cell], column: str) -> str | None:
    cell = row.get(column)
    return cell.value if cell is not None else None


def test_research_sort_key_uses_only_tier_and_persistent_seed() -> None:
    high, defaulted = research_sort_key("HIGH", Decimal("3"))
    low, low_fallback = research_sort_key("LOW", None)
    assert high == Decimal("199997")
    assert defaulted is False
    assert low == Decimal("50000")
    assert low_fallback is True
    with pytest.raises(ValueError, match="Candidate High/Low"):
        research_sort_key("WATCHLIST", Decimal("1"))


def test_research_rank_ties_use_canonical_ticker_and_start_at_one() -> None:
    zzz, aaa = uuid4(), uuid4()
    assert research_rank_positions(
        [(zzz, "ZZZ", Decimal("99999.75")), (aaa, "AAA", Decimal("99999.75"))]
    ) == {aaa: 1, zzz: 2}


def test_legacy_source_inputs_reconcile_representative_cached_research_ranks() -> None:
    workbook_path = Path(__file__).resolve().parents[3] / "reference" / "workbook" / MAIN_BOOK
    workbook = Workbook.read(
        workbook_path, lambda name: name in {"Universe Registry", "Candidate Ranking"}
    )
    inputs = {row["ticker"]: row for row in research_priority_rows(workbook)}
    cached: dict[str, tuple[str | None, str | None]] = {}
    for _row_number, registry_cells in workbook.rows("Universe Registry", 5):
        ticker = _cell_value(registry_cells, "A") or ""
        if ticker:
            cached[ticker.strip().upper()] = (
                _cell_value(registry_cells, "J"),
                _cell_value(registry_cells, "Q"),
            )
    expected = [
        ("NBIS", "LOW", Decimal("0.25"), 1, Decimal("99999.75")),
        ("PGR", "LOW", Decimal("0.28"), 2, Decimal("99999.72")),
        ("TMUS", "LOW", Decimal("0.285"), 3, Decimal("99999.715")),
        ("CBOE", "LOW", Decimal("0.295"), 4, Decimal("99999.705")),
        ("TXN", "LOW", Decimal("0.297"), 5, Decimal("99999.703")),
    ]
    for ticker, tier, priority, rank, sort_key in expected:
        priority_row = inputs[ticker]
        calculated_key, used_default = research_sort_key(
            priority_row["candidate_tier"], priority_row["priority_seed"]
        )
        assert (priority_row["candidate_tier"], priority_row["priority_seed"]) == (
            tier,
            priority,
        )
        assert (calculated_key, used_default) == (sort_key, False)
        assert Decimal(cached[ticker][0] or "NaN") == rank
        assert Decimal(cached[ticker][1] or "NaN") == sort_key

    blank_seed = inputs["CRL"]
    assert blank_seed["priority_seed"] is None
    assert research_sort_key(blank_seed["candidate_tier"], None) == (Decimal("50000"), True)
    # This source row is a known stale cached rank/key rather than a formula input.
    assert cached["FICO"][0] == "1.0"
    assert research_sort_key(inputs["FICO"]["candidate_tier"], inputs["FICO"]["priority_seed"])[
        0
    ] == Decimal("99997.0")


@pytest.mark.integration
def test_research_run_ranks_candidates_only_and_snapshots_seed_fallback(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        seed(db)
        high = ops.create_company(db, s.CompanyCreate(name="High Priority Research Fixture"))
        missing = ops.create_company(db, s.CompanyCreate(name="Missing Research Input Fixture"))
        for item in (high, missing):
            ops.transition_lifecycle(
                db,
                item.id,
                s.LifecycleChange(
                    new_state=Lifecycle.CANDIDATE,
                    expected_event_id=None,
                    actor="LOCAL_USER",
                    reason="Candidate-only Research Rank test fixture.",
                    effective_at=datetime.now(UTC) - timedelta(seconds=1),
                ),
            )
        as_of = datetime.now(UTC) + timedelta(seconds=5)
        prior_as_of = as_of - timedelta(seconds=3)
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("portfolio_api.domain.services.now", lambda: prior_as_of)
            prior_run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.RESEARCH,
                    actor="LOCAL_USER",
                    reason="Confirm unrecorded source inputs stay unavailable in history.",
                ),
            )
        db.add(
            ResearchPriorityInput(
                id=uuid4(),
                company_id=high.id,
                canonical_ticker="HGH",
                candidate_tier="HIGH",
                priority_seed=Decimal("3"),
                input_quality="PASS",
                quality_reason=None,
                source_digest="a" * 64,
                bucket_source_ref="fixture:Universe Registry!C5",
                priority_seed_source_ref="fixture:Candidate Ranking!A2",
                recorded_at=as_of - timedelta(seconds=2),
                actor="IMPORT",
            )
        )
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("portfolio_api.domain.services.now", lambda: as_of)
            run = ops.create_ranking_run(
                db,
                s.RankingRunCreate(
                    ranking_type=RankingType.RESEARCH,
                    actor="LOCAL_USER",
                    reason="Check documented Research Sort Key and candidate membership.",
                ),
            )
        detail = q.ranking_run_detail(db, run.id)
        entries = {item.company.id: item.entry for item in detail.entries}
        assert entries[high.id].status == RankingEntryStatus.RANKED
        assert entries[high.id].position == 1
        high_snapshot = entries[high.id].input_snapshot
        assert high_snapshot is not None
        assert isinstance(high_snapshot, s.ResearchRankInputSnapshot)
        assert high_snapshot.sort_key == Decimal("199997")
        assert high_snapshot.used_legacy_default is False
        assert entries[missing.id].status == RankingEntryStatus.INPUTS_UNAVAILABLE
        assert entries[missing.id].position is None
        prior_entries = {
            item.company.id: item.entry for item in q.ranking_run_detail(db, prior_run.id).entries
        }
        assert prior_entries[high.id].status == RankingEntryStatus.INPUTS_UNAVAILABLE
        assert prior_entries[high.id].position is None

        cedar = db.scalar(select(Company).where(Company.name.startswith("Cedar")))
        assert cedar is not None
        assert entries[cedar.id].status == RankingEntryStatus.NOT_ELIGIBLE
        stored = db.get(RankingEntry, entries[high.id].id)
        assert stored is not None
        with pytest.raises(ValueError, match="append-only"), db.begin_nested():
            stored.position = 2
            db.flush()
