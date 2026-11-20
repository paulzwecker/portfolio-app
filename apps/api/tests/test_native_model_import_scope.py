"""Scope and non-mutating preflight safeguards for native model imports."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_booking_dcf_mapping import _synthetic_booking_workbook

from portfolio_api.model_input_migration import (
    _existing_model,
    _map_portfolio_dcf,
    _model_mappers_for,
    main,
)


def test_exact_model_tab_selection_and_unknown_keys_fail_closed() -> None:
    assert [key for key, _ in _model_mappers_for("P-BKNG")] == ["P-BKNG"]
    all_keys = [key for key, _ in _model_mappers_for(None)]
    assert "P-BKNG" in all_keys and "P-GOOGL" in all_keys
    for invalid in ("BKNG", "P-BKNG ", "P-NOT-A-MODEL", ""):
        with pytest.raises(ValueError, match="Unknown native-model source key"):
            _model_mappers_for(invalid)


def test_apply_cli_requires_one_named_model_before_any_database_connection(
    tmp_path: Path,
) -> None:
    with (
        patch("portfolio_api.model_input_migration.load_source_workbook") as workbook,
        patch("portfolio_api.model_input_migration.create_database_engine") as engine,
        pytest.raises(SystemExit) as denied,
    ):
        main(["--apply", "--output", str(tmp_path / "blocked.json")])
    assert denied.value.code == 2
    workbook.assert_not_called()
    engine.assert_not_called()


@pytest.mark.parametrize("apply", [False, True])
def test_cli_scopes_database_activity_and_uses_read_only_engine_for_preview(
    tmp_path: Path,
    apply: bool,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    fake_report = {
        "mode": "APPLIED" if apply else "DRY_RUN",
        "selected_model_keys": ["P-BKNG"],
        "input_sets_imported": 1 if apply else 0,
        "input_sets_already_imported": 0,
    }
    arguments = ["--model-key", "P-BKNG", "--output", str(tmp_path / "result.json")]
    if apply:
        arguments.append("--apply")
    with (
        patch(
            "portfolio_api.model_input_migration.load_source_workbook",
            return_value=_synthetic_booking_workbook(),
        ),
        patch(
            "portfolio_api.model_input_migration.create_database_engine",
            return_value=engine,
        ) as create,
        patch(
            "portfolio_api.model_input_migration.import_native_model_inputs",
            return_value=fake_report,
        ) as importer,
    ):
        assert main(arguments) == 0
    assert create.call_args.kwargs["read_only"] is (not apply)
    assert importer.call_args.kwargs["model_key"] == "P-BKNG"
    assert importer.call_args.kwargs["apply"] is apply


@pytest.mark.integration
def test_existing_model_select_does_not_request_row_lock_during_read_only_preflight(
    postgres_engine: Engine,
) -> None:
    mapped = _map_portfolio_dcf(
        _synthetic_booking_workbook(), "P-BKNG", datetime(2026, 11, 20, tzinfo=UTC)
    )
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        assert (
            _existing_model(
                session,
                company_id=uuid4(),
                listing_id=uuid4(),
                mapped=mapped,
                for_update=False,
            )
            is None
        )
