"""Incomplete Sheets publication is unavailable before any external effect."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_agent_work_sheet_sync import _contract

from portfolio_api import agent_work_sheet_sync, thesis_watch_sheet_sync
from portfolio_api.domain import routes, schemas
from portfolio_api.domain.models import OperationalJobRequest
from portfolio_api.main import create_app
from portfolio_api.manual_operations import create_job_request
from portfolio_api.portfolio_sheet_sync import (
    GoogleSheetsPortfolioPublisher,
    PortfolioSheetPublishError,
    publish_portfolio_state,
)
from portfolio_api.recurring_operations import _publish_agent_feeds, process_manual_job_requests
from portfolio_api.settings import Settings


def test_all_service_entries_fail_before_read_or_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    session = cast(Session, object())
    settings = Settings(
        _env_file=None, google_sheets_spreadsheet_id="synthetic-workbook-id-123456789"
    )
    monkeypatch.setattr(
        "portfolio_api.portfolio_sheet_sync.q.overview", lambda *_a: pytest.fail("read started")
    )
    calls: list[Callable[[], object]] = [
        lambda: publish_portfolio_state(session, uuid4(), settings),
        lambda: thesis_watch_sheet_sync.publish_thesis_watch_feed(session, settings),
        lambda: agent_work_sheet_sync.publish_agent_work_feed(session, _contract(), settings),
        lambda: GoogleSheetsPortfolioPublisher(settings),
    ]
    for call in calls:
        with pytest.raises(PortfolioSheetPublishError) as error:
            call()
        assert error.value.code == "PUBLICATION_UNAVAILABLE" and error.value.status == 503
    result = _publish_agent_feeds(cast(Engine, object()), settings, datetime.now(UTC))
    assert result["status"] == "BLOCKED" and result["failure_code"] == "PUBLICATION_UNAVAILABLE"


@pytest.mark.parametrize("route", ["portfolio", "thesis", "agent"])
def test_direct_routes_reject_before_data_or_delivery(
    route: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = cast(Session, object())
    for name in ("publish_portfolio_state", "publish_thesis_watch_feed", "deliver_agent_work"):
        monkeypatch.setattr(routes, name, lambda *_a, **_k: pytest.fail("publication started"))
    with pytest.raises(HTTPException) as error:
        if route == "portfolio":
            routes.post_google_sheets_portfolio_state_publish(
                schemas.GoogleSheetsPortfolioStatePublishRequest.model_construct(
                    portfolio_id=uuid4()
                ),
                session,
            )
        elif route == "thesis":
            routes.post_google_sheets_thesis_watch_publish(
                schemas.GoogleSheetsThesisWatchPublishRequest.model_construct(), session
            )
        else:
            routes.post_google_sheets_agent_work_publish(
                "PORTFOLIO_THESIS_SENTINEL",
                schemas.GoogleSheetsAgentWorkPublishRequest.model_construct(),
                session,
            )
    assert error.value.status_code == 503 and "PUBLICATION_UNAVAILABLE" in str(error.value.detail)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/google-sheets-sync/portfolio-state/publish", {"portfolio_id": str(uuid4())}),
        ("/v1/google-sheets-sync/thesis-watch/publish", {}),
        ("/v1/google-sheets-agent-operations/PORTFOLIO_THESIS_SENTINEL/work/publish", {}),
    ],
)
def test_authenticated_http_rejects_publication(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, object]
) -> None:
    token = "synthetic-proxy-token-01234567890123456789"
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url=SecretStr(
            "postgresql+psycopg://synthetic.invalid/fixture?sslmode=verify-full"
        ),
        api_access_token=SecretStr(token),
    )
    monkeypatch.setattr(
        "portfolio_api.main.create_database_engine", lambda *_a, **_k: postgres_engine
    )
    with TestClient(create_app(settings)) as client:
        assert client.post(path, json=body).status_code == 401
        response = client.post(path, json=body, headers={"x-api-access-token": token})
        assert response.status_code == 503 and "PUBLICATION_UNAVAILABLE" in response.text


@pytest.mark.integration
def test_manual_feed_dispatch_is_blocked_without_publisher(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        request, _ = create_job_request(
            session, schemas.OperationalJobRequestCreate(job_name="AGENT_WORK_FEED")
        )
        request_id = request.id
    monkeypatch.setattr(
        "portfolio_api.recurring_operations.deliver_agent_work",
        lambda *_a, **_k: pytest.fail("delivery started"),
    )
    result = process_manual_job_requests(postgres_engine, Settings(_env_file=None))
    assert result["status"] == "BLOCKED"
    with Session(postgres_engine) as session:
        stored = session.get(OperationalJobRequest, request_id)
        assert stored is not None and stored.status == "BLOCKED"
