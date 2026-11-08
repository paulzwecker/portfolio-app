"""Synthetic read-only review of bounded bootstrap batch evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr
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
def test_history_review_http_routes_require_authentication_and_read_only_transactions(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    modes: list[tuple[object, object]] = []
    original = latest_historical_bootstrap_review

    def checked_review(session: Session, *, run_id: object = None, offset: int = 0) -> object:
        modes.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        assert run_id is None
        return original(session, offset=offset)

    monkeypatch.setattr(
        "portfolio_api.domain.routes.latest_historical_bootstrap_review", checked_review
    )
    settings = fixture_settings().model_copy(
        update={"app_env": "preview", "api_access_token": SecretStr("synthetic-history-token")}
    )
    with Session(postgres_engine) as session:
        schema = str(session.scalar(text("SELECT current_schema()")))
    reader = fixture_read_engine(postgres_engine.url, schema, fixture_settings())
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            path = "/v1/market-data/historical-bootstrap"
            assert client.get(path).status_code == 401
            headers = {"x-api-access-token": "synthetic-history-token"}
            response = client.get(path, headers=headers)
            assert response.status_code == 200 and response.json()["run_id"] is None
            assert client.post(path, headers=headers).status_code == 405
            invalid = client.get(
                f"{path}/{uuid4()}/checkpoints/{uuid4()}/reconciliation", headers=headers
            )
            assert invalid.status_code == 404
        assert modes == [("on", "repeatable read")]
    finally:
        reader.dispose()


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
        "no_prices",
        "malformed_receipt",
        "unavailable",
        "failed",
        "blocked",
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
            status={
                "pending": "PENDING",
                "unavailable": "UNAVAILABLE",
                "failed": "FAILED",
                "blocked": "BLOCKED",
            }.get(mode, "COMPLETE"),
            attempt_count=1,
            batch_id=batch.id,
            source_digest="d" * 64 if mode == "wrong_batch" else digest,
            failure_code={
                "unavailable": "NO_PROVIDER_DATA",
                "failed": "PRIVATE_ERROR_MESSAGE",
                "blocked": "CANONICAL_IDENTITY_CHANGED",
            }.get(mode),
            finished_at=datetime(2026, 11, 8, 21, tzinfo=UTC),
            report={
                "identity": {
                    "listing_id": str(listing.id),
                    "security_id": str(security.id),
                    "venue": "OLD" if mode == "changed_identity" else listing.venue,
                    "ticker": listing.ticker,
                    "currency": listing.currency,
                },
                "coverage": {
                    "raw_response_count": True if mode == "malformed_receipt" else 1,
                    "daily_price_rows": -1 if mode == "malformed_receipt" else 0,
                    "normalization_warnings_captured": False,
                    "normalization_warnings": [],
                },
                "provider_failure_count": False if mode == "malformed_receipt" else 0,
                "normalization_rejections": [],
            },
        )
        session.add(checkpoint)
        for day in () if mode in {"no_prices", "malformed_receipt"} else (2, 7):
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
            "no_prices": "NO_DAILY_CLOSES",
            "malformed_receipt": "NO_DAILY_CLOSES",
            "unavailable": "CHECKPOINT_UNAVAILABLE",
            "failed": "CHECKPOINT_FAILED",
            "blocked": "CHECKPOINT_BLOCKED",
        }[mode]
        assert row.reason == expected
        if mode == "valid":
            assert row.scheduled_session_review is not None
            assert row.scheduled_session_review.absent_scheduled_dates == [date(2026, 7, 6)]
            assert row.requested_window_review is not None
            assert row.requested_window_review.start_date == date(2026, 1, 1)
            assert row.requested_window_review.end_date == date(2026, 11, 8)
            assert date(2026, 7, 1) in row.requested_window_review.absent_scheduled_dates
            assert date(2026, 7, 8) in row.requested_window_review.absent_scheduled_dates
        else:
            assert row.scheduled_session_review is None
            assert row.requested_window_review is None
        if mode in {"no_prices", "unavailable", "failed", "blocked"}:
            assert row.checkpoint_diagnostics is not None
            assert row.checkpoint_diagnostics.raw_response_count == 1
            assert row.checkpoint_diagnostics.normalization_warning_count is None
            assert row.checkpoint_diagnostics.failure_kind == (
                "NO_PROVIDER_DATA"
                if mode == "unavailable"
                else "OTHER"
                if mode in {"failed", "blocked"}
                else "NONE"
            )
            assert "PRIVATE_ERROR_MESSAGE" not in row.model_dump_json()
        if mode == "malformed_receipt":
            assert row.checkpoint_diagnostics is not None
            assert row.checkpoint_diagnostics.raw_response_count is None
            assert row.checkpoint_diagnostics.normalized_daily_rows is None
            assert row.checkpoint_diagnostics.provider_failure_count is None
        assert session.scalar(select(MarketDataBootstrapCheckpoint.status)) == {
            "pending": "PENDING",
            "unavailable": "UNAVAILABLE",
            "failed": "FAILED",
            "blocked": "BLOCKED",
        }.get(mode, "COMPLETE")
