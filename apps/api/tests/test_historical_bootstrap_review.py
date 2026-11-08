"""Synthetic read-only review of bounded bootstrap batch evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _seed_canonical_scope

from portfolio_api.domain.models import (
    MarketDataBatch,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    PriceObservation,
)
from portfolio_api.historical_bootstrap_review import latest_historical_bootstrap_review

NOW = datetime(2026, 11, 9, tzinfo=UTC)


@pytest.mark.integration
def test_no_run_is_explicitly_unavailable(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        result = latest_historical_bootstrap_review(session, checked_at=NOW)
        assert result.run_id is None
        assert result.listings == []


@pytest.mark.integration
def test_large_scope_is_bounded_and_reports_omitted_listings(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        _, _, listing = _seed_canonical_scope(session)
        run = MarketDataBootstrapRun(
            id=uuid4(),
            input_digest="b" * 64,
            provider_id="synthetic",
            provider_schema_version="v1",
            crosswalk_sha256="c" * 64,
            target_environment="development",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            scope={},
            status="PREPARED",
            prepared_at=datetime(2026, 11, 8, 19, tzinfo=UTC),
            report={},
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                MarketDataBootstrapCheckpoint(
                    id=uuid4(),
                    run_id=run.id,
                    subject_kind="LISTING",
                    subject_key=f"SYNTH:{i:02}",
                    listing_id=listing.id,
                    start_date=run.start_date,
                    end_date=run.end_date,
                    status="PENDING",
                    attempt_count=0,
                    report={},
                )
                for i in range(31)
            ]
        )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        result = latest_historical_bootstrap_review(session, checked_at=NOW)
        assert result.listing_count == 31
        assert len(result.listings) == 30
        assert result.omitted_listing_count == 1
        assert all(row.reason == "CHECKPOINT_NOT_COMPLETE" for row in result.listings)
        assert result.run_id is not None
        page = latest_historical_bootstrap_review(
            session, checked_at=NOW, run_id=result.run_id, offset=30
        )
        assert page.offset == 30 and page.omitted_listing_count == 0
        assert [row.subject_key for row in page.listings] == ["SYNTH:30"]
        assert {row.subject_key for row in result.listings}.isdisjoint(
            {row.subject_key for row in page.listings}
        )
        with pytest.raises(ValueError):
            latest_historical_bootstrap_review(session, checked_at=NOW, offset=30)
        with pytest.raises(ValueError):
            latest_historical_bootstrap_review(
                session, checked_at=NOW, run_id=result.run_id, offset=31
            )
        with pytest.raises(LookupError):
            latest_historical_bootstrap_review(session, checked_at=NOW, run_id=uuid4())
        pinned_id = result.run_id
    newer_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            MarketDataBootstrapRun(
                id=newer_id,
                input_digest="e" * 64,
                provider_id="synthetic",
                provider_schema_version="v1",
                crosswalk_sha256="c" * 64,
                target_environment="development",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                scope={},
                status="PREPARED",
                prepared_at=datetime(2026, 11, 8, 22, tzinfo=UTC),
                report={},
            )
        )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        assert latest_historical_bootstrap_review(session, checked_at=NOW).run_id == newer_id
        page = latest_historical_bootstrap_review(
            session, checked_at=NOW, run_id=pinned_id, offset=30
        )
        assert page.run_id == pinned_id and page.listings[0].subject_key == "SYNTH:30"


@pytest.mark.integration
@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "changed_identity",
        "wrong_batch",
        "missing_schedule",
        "pending",
        "currency_missing",
        "wrong_currency",
        "wrong_provider",
    ],
)
def test_review_uses_only_verified_listing_and_batch_dates(
    postgres_engine: Engine, mode: str
) -> None:
    with Session(postgres_engine) as session, session.begin():
        _, security, listing = _seed_canonical_scope(session)
        listing.venue = "UNREVIEWED" if mode == "missing_schedule" else "NYSE"
        if mode == "currency_missing":
            listing.currency = None
        digest = "a" * 64
        run = MarketDataBootstrapRun(
            id=uuid4(),
            input_digest="b" * 64,
            provider_id="synthetic",
            provider_schema_version="v1",
            crosswalk_sha256="c" * 64,
            target_environment="development",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            scope={},
            status="COMPLETE",
            prepared_at=datetime(2026, 11, 8, 19, tzinfo=UTC),
            report={},
        )
        batch = MarketDataBatch(
            id=uuid4(),
            source_digest=digest,
            source_kind="PROVIDER_RESPONSE",
            provider_id="synthetic",
            normalizer_version="synthetic-v1",
            provider_summary={},
            reconciliation={},
            recorded_at=datetime(2026, 11, 8, 20, tzinfo=UTC),
        )
        session.add_all([run, batch])
        session.flush()
        checkpoint = MarketDataBootstrapCheckpoint(
            id=uuid4(),
            run_id=run.id,
            subject_kind="LISTING",
            subject_key="NYSE:SYNTH",
            listing_id=listing.id,
            start_date=run.start_date,
            end_date=run.end_date,
            status="PENDING" if mode == "pending" else "COMPLETE",
            attempt_count=1,
            batch_id=batch.id,
            source_digest="d" * 64 if mode == "wrong_batch" else digest,
            finished_at=datetime(2026, 11, 8, 21, tzinfo=UTC),
            report={
                "identity": {
                    "listing_id": str(listing.id),
                    "security_id": str(security.id),
                    "venue": "OLD" if mode == "changed_identity" else listing.venue,
                    "ticker": listing.ticker,
                    "currency": listing.currency,
                }
            },
        )
        session.add(checkpoint)
        for day in (2, 7):
            session.add(
                PriceObservation(
                    listing_id=listing.id,
                    batch_id=batch.id,
                    price_kind="DAILY_CLOSE",
                    market_date=datetime(2026, 7, day, tzinfo=UTC),
                    recorded_at=datetime(2026, 11, 8, 20, tzinfo=UTC),
                    split_adjusted_close=Decimal("100"),
                    currency="EUR" if mode == "wrong_currency" else "USD",
                    provider="other" if mode == "wrong_provider" else "synthetic",
                    provider_symbol="SYNTH",
                    adjustment_basis="Synthetic split-adjusted close",
                    data_quality="PASS",
                    source_ref=f"bootstrap-review-{day}-{uuid4()}",
                )
            )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        result = latest_historical_bootstrap_review(session, checked_at=NOW)
        assert result.listing_count == 1 and result.omitted_listing_count == 0
        row = result.listings[0]
        expected = {
            "valid": "AVAILABLE",
            "changed_identity": "IDENTITY_CHANGED",
            "wrong_batch": "BATCH_UNVERIFIED",
            "missing_schedule": "NO_SCHEDULE",
            "pending": "CHECKPOINT_NOT_COMPLETE",
            "currency_missing": "LISTING_CURRENCY_UNAVAILABLE",
            "wrong_currency": "NO_DAILY_CLOSES",
            "wrong_provider": "NO_DAILY_CLOSES",
        }[mode]
        assert row.reason == expected
        if mode == "valid":
            assert row.scheduled_session_review is not None
            assert row.scheduled_session_review.absent_scheduled_dates == [date(2026, 7, 6)]
        else:
            assert row.scheduled_session_review is None
        assert session.scalar(select(MarketDataBootstrapCheckpoint.status)) == (
            "PENDING" if mode == "pending" else "COMPLETE"
        )
