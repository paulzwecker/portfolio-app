"""The writable browser rehearsal is limited to isolated immutable ledger receipts."""

from uuid import UUID

import pytest
from browser_server import (
    fixture_application,
    fixture_ledger_writer,
    fixture_read_engine,
    fixture_settings,
)
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable
from test_portfolio_ledger_reviews import accept, prepare, submit
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.database_write_target import DatabaseReadOnlyError
from portfolio_api.domain.models import Portfolio

pytestmark = pytest.mark.integration


def test_isolated_browser_review_writes_only_ledger_receipts(storage_engine: Engine) -> None:
    portfolio_id, packet = prepare(storage_engine)
    request = submit(storage_engine, portfolio_id, packet)
    settings = fixture_settings()
    with storage_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    reader = fixture_read_engine(storage_engine.url, schema, settings)
    writer = fixture_ledger_writer(storage_engine.url, schema)
    metadata = {"portfolio_id": str(portfolio_id), "schema": schema, "ledger_receipts_only": True}
    try:
        with TestClient(
            fixture_application(reader, settings, metadata, ledger_writer=writer)
        ) as client:
            before = client.get("/__test/fixture").json()
            path = f"/v1/portfolios/{portfolio_id}/ledger/candidates"
            result = client.post(path, json=request.model_dump(mode="json"))
            assert result.status_code == 200
            candidate = c.LedgerCandidateRead.model_validate(result.json())
            reviewed = client.post(
                f"{path}/{candidate.id}/review", json=accept(candidate).model_dump(mode="json")
            )
            assert reviewed.status_code == 200 and reviewed.json()["status"] == "ACCEPTED"
            assert client.get(path).json()["current_revision_number"] == 1
            assert (
                client.get("/__test/fixture").json()["protected_state_sha256"]
                == before["protected_state_sha256"]
            )
            assert (
                client.post(f"/v1/portfolios/{portfolio_id}/holding-snapshots", json={}).status_code
                == 405
            )
            assert (
                client.post(
                    "/v1/portfolios/11111111-1111-4111-8111-111111111111/ledger/candidates", json={}
                ).status_code
                == 405
            )
        statements: list[Executable] = [
            text("UPDATE portfolios SET name='forbidden'"),
            insert(Portfolio).values(id=UUID(int=1), name="forbidden", base_currency="EUR"),
            text("CREATE TABLE forbidden (id integer)"),
            text("SELECT nextval('forbidden')"),
            insert(Table("portfolio_ledger_candidates", MetaData(), schema="public")),
            text("SET search_path=public"),
        ]
        for statement in statements:
            with writer.begin() as connection, pytest.raises(DatabaseReadOnlyError):
                connection.execute(statement)
        with Session(reader) as session:
            assert (
                session.scalar(select(Portfolio.name).where(Portfolio.id == portfolio_id))
                == "Synthetic Ledger Portfolio"
            )
    finally:
        reader.dispose()
        writer.dispose()
