"""Synthetic coverage for the bounded, frozen cloud market correction path."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _crosswalk, _mapping, _seed_canonical_scope

from portfolio_api.database import Base
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.market_data_startup import run_cloud_incremental_refresh
from portfolio_api.settings import Settings


@pytest.fixture
def market_scope(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, _digest = _crosswalk(_mapping(company.id, security.id, listing.id))
    path = tmp_path / "synthetic-crosswalk.json"
    path.write_text(crosswalk.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("portfolio_api.market_data_startup.CROSSWALK_PATH", path)
    return path


def table_counts(engine: Engine) -> dict[str, int | None]:
    with Session(engine) as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


@pytest.mark.integration
def test_cloud_correction_pins_ninety_day_scope_and_required_fx_without_writes(
    postgres_engine: Engine,
    market_scope: Path,
) -> None:
    settings = Settings(
        _env_file=None, database_url=None, database_target_environment="development"
    )
    before = table_counts(postgres_engine)
    scheduled = Mock(return_value={"status": "COMPLETE"})
    with (
        patch("portfolio_api.market_data_startup.run_scheduled", scheduled),
        Session(postgres_engine) as session,
    ):
        result = run_cloud_incremental_refresh(session, settings, datetime.now(UTC))
    assert result["status"] == "COMPLETE"
    assert result["subject_count"] == 2
    assert result["provider_http_attempt_upper_bound"] == 24
    arguments = scheduled.call_args.kwargs
    assert (arguments["end_date"] - arguments["start_date"]).days + 1 == 90
    assert arguments["listing_key_filter"] == {("NASDAQ", "SYNTH")}
    assert arguments["fx_pair_filter"] == {("USD", "EUR")}
    frozen, digest = arguments["frozen_yahoo_crosswalk"]
    assert frozen.mappings[0].ticker == "SYNTH"
    assert len(digest) == 64
    assert before == table_counts(postgres_engine)


@pytest.mark.integration
@pytest.mark.parametrize("problem", ["identity", "budget", "mapping", "target"])
def test_cloud_scope_fails_before_claims_or_provider_calls(
    postgres_engine: Engine,
    market_scope: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    import json

    payload = json.loads(market_scope.read_text(encoding="utf-8"))
    if problem == "identity":
        payload["mappings"][0]["canonical_company_id"] = str(uuid4())
    elif problem == "mapping":
        payload["mappings"] = []
    elif problem == "budget":
        monkeypatch.setattr("portfolio_api.market_data_startup.CLOUD_MAX_SUBJECTS", 1)
    market_scope.write_text(json.dumps(payload), encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url=None,
        database_target_environment=None if problem == "target" else "development",
    )
    before = table_counts(postgres_engine)
    with (
        patch("portfolio_api.market_data_startup.run_scheduled") as scheduled,
        Session(postgres_engine) as session,
    ):
        result = run_cloud_incremental_refresh(session, settings, datetime.now(UTC))
    assert result["status"] == "BLOCKED"
    scheduled.assert_not_called()
    assert before == table_counts(postgres_engine)


def test_pinned_replay_refuses_changed_mapping_bytes_before_claims(tmp_path: Path) -> None:
    path = tmp_path / "changed-mapping.json"
    path.write_text("{}", encoding="utf-8")
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="crosswalk changed"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            replay_scope={"crosswalk_sha256": "a" * 64},
            yahoo_crosswalk_path=path,
        )
    claim.assert_not_called()


@pytest.mark.parametrize("replacement", [{"listing_key_filter": set()}, {"fx_pair_filter": set()}])
def test_frozen_replay_filters_cannot_be_replaced(replacement: dict[str, Any]) -> None:
    with (
        patch("portfolio_api.external_ingestion._claim_run") as claim,
        pytest.raises(ValueError, match="cannot replace"),
    ):
        run_scheduled(
            cast(Session, None),
            Settings(_env_file=None, database_url=None),
            replay_scope={"crosswalk_sha256": "a" * 64},
            **replacement,
        )
    claim.assert_not_called()
