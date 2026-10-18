from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from portfolio_api.research_ranking import research_rank_positions, research_sort_key


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
