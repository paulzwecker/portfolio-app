"""A fictional browser publication can insert only its scoped canonical snapshot/receipt."""

from uuid import UUID

import pytest
from browser_ledger_ownership import prepare_ledger_ownership
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
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.database_write_target import DatabaseReadOnlyError
from portfolio_api.domain import queries
from portfolio_api.domain.models import Portfolio, PortfolioLedgerCandidate

pytestmark = pytest.mark.integration


def test_browser_publication_writes_only_scoped_snapshot_and_receipt(
    storage_engine: Engine,
) -> None:
    # This fixture uses its actual seed's opening balances, not operator data.
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from browser_portfolio_data import prepare_portfolio_data

    settings = fixture_settings()
    with TemporaryDirectory() as directory:
        metadata = prepare_portfolio_data(storage_engine, Path(directory), "unpriced", settings)
    prepare_ledger_ownership(storage_engine, metadata, publish=False)
    portfolio_id = UUID(str(metadata["portfolio_id"]))
    candidate_id = str(metadata["candidate_id"])
    with storage_engine.connect() as connection:
        schema = str(connection.scalar(text("SELECT current_schema()")))
    metadata.update(schema=schema, ledger_publication_only=True)
    reader = fixture_read_engine(storage_engine.url, schema, settings)
    writer = fixture_ledger_writer(storage_engine.url, schema, publication=True)
    path = f"/v1/portfolios/{portfolio_id}/ledger/candidates/{candidate_id}"
    try:
        invalid_scopes: tuple[dict[str, object], ...] = (
            {},
            {"ledger_receipts_only": True, "ledger_publication_only": True},
        )
        for invalid_scope in invalid_scopes:
            with pytest.raises(ValueError, match="one explicit test-only scope"):
                fixture_application(reader, settings, invalid_scope, ledger_writer=writer)
        with TestClient(
            fixture_application(reader, settings, metadata, ledger_writer=writer)
        ) as client:
            before = client.get("/__test/fixture").json()
            plan = c.LedgerPublicationPreviewRead.model_validate(
                client.get(f"{path}/publication-preview").json()
            )
            body = c.LedgerPublicationCreate(
                expected_plan_sha256=plan.plan_sha256,
                expected_previous_publication_id=None,
                confirmation=plan.confirmation_phrase,
                reason="Fictional reviewed browser publication",
                ownership_transfer_reviewed=True,
                whole_portfolio_scope_reviewed=True,
                current_state_recovery_verified=True,
                holdings_confirmation=True,
            ).model_dump(mode="json")
            bad = {**body, "confirmation": "incorrect"}
            assert client.post(f"{path}/publish", json=bad).status_code == 409
            assert (
                client.get("/__test/fixture").json()["protected_state_sha256"]
                == before["protected_state_sha256"]
            )
            response = client.post(f"{path}/publish", json=body)
            assert response.status_code == 200
            receipt = c.LedgerPublicationRead.model_validate(response.json())
            assert not receipt.replayed
            assert client.post(f"{path}/publish", json=body).json()["replayed"]
            assert client.get(f"{path}/publication-preview").json()["status"] == "ALREADY_PUBLISHED"
            assert (
                client.get("/__test/fixture").json()["protected_state_sha256"]
                == before["protected_state_sha256"]
            )
            assert (
                client.post(f"/v1/portfolios/{portfolio_id}/holding-snapshots", json={}).status_code
                == 405
            )
            assert client.post(f"{path}/review", json={}).status_code == 405
            assert (
                client.post(f"/v1/portfolios/{portfolio_id}/ledger/candidates", json={}).status_code
                == 405
            )
            assert (
                client.post(
                    path.replace(candidate_id, str(UUID(int=1))) + "/publish", json=body
                ).status_code
                == 405
            )
        statements: list[Executable] = [
            text("UPDATE holding_snapshots SET reason='forbidden'"),
            insert(Portfolio).values(id=UUID(int=1), name="forbidden", base_currency="EUR"),
            insert(PortfolioLedgerCandidate).values(id=UUID(int=1)),
            text("CREATE TABLE forbidden (id integer)"),
            text("SELECT nextval('forbidden')"),
            insert(Table("holding_snapshots", MetaData(), schema="public")),
            text("SET search_path=public"),
        ]
        for statement in statements:
            with writer.begin() as connection, pytest.raises(DatabaseReadOnlyError):
                connection.execute(statement)
        with Session(reader) as session:
            overview = queries.overview(session, portfolio_id)
            assert overview.snapshot is not None and overview.snapshot.id == receipt.snapshot.id
            assert (
                session.scalar(select(Portfolio.id).where(Portfolio.id == portfolio_id))
                == portfolio_id
            )
    finally:
        reader.dispose()
        writer.dispose()
