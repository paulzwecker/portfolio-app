"""Workbook refreshes share the canonical portfolio/ledger review lock."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_portfolio_ledger_storage import AT
from test_portfolio_ledger_storage import storage_engine as storage_engine

from portfolio_api import legacy_import
from portfolio_api.domain.models import CashPosition, HoldingSnapshot, Portfolio

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("entrypoint", ["identity", "holdings"])
def test_workbook_writer_waits_behind_portfolio_lock_and_recovers(
    storage_engine: Engine, entrypoint: str
) -> None:
    portfolio_id = legacy_import._stable_id("portfolio", "legacy-default")
    with Session(storage_engine) as session, session.begin():
        session.add(
            Portfolio(
                id=portfolio_id,
                name="Synthetic workbook refresh portfolio",
                base_currency="EUR",
                created_at=AT,
            )
        )
    workbook = legacy_import.Workbook(Path("synthetic-unopened-workbook.xlsx"), "a" * 64, {})
    plan = legacy_import.ImportPlan(
        portfolio_workbook=workbook,
        market_workbook=workbook,
        observed_at=AT + timedelta(days=1),
        source_digest="b" * 64,
        cash=[legacy_import.CashRow("EUR", Decimal("7.125"), "synthetic-cash-record")],
    )

    def invoke(session: Session) -> None:
        if entrypoint == "identity":
            assert legacy_import._import_identity(session, plan, incremental_sync=True) == {}
        else:
            portfolio = session.get(Portfolio, portfolio_id)
            assert portfolio is not None
            assert legacy_import._import_holdings(session, plan, {}, portfolio) == (1, 1)

    with Session(storage_engine) as blocker, blocker.begin():
        blocker.execute(select(Portfolio.id).where(Portfolio.id == portfolio_id).with_for_update())
        with Session(storage_engine) as writer:
            writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(OperationalError) as rejected:
                invoke(writer)
            assert getattr(rejected.value.orig, "sqlstate", None) == "55P03"
            writer.rollback()
            assert writer.scalar(select(func.count()).select_from(HoldingSnapshot)) == 0
            assert writer.scalar(select(func.count()).select_from(CashPosition)) == 0
    with Session(storage_engine) as writer, writer.begin():
        invoke(writer)
    with Session(storage_engine) as session:
        expected = 1 if entrypoint == "holdings" else 0
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == expected
        assert session.scalar(select(func.count()).select_from(CashPosition)) == expected
        if expected:
            assert session.scalar(select(CashPosition.balance)) == Decimal("7.125")
