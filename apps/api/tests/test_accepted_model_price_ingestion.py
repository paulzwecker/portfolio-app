"""Exact accepted native-model price ingestion stays source-scoped and fails closed."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine

from portfolio_api.database_write_target import (
    ACCEPTED_MODEL_PRICE_WRITE_OPERATION,
    DatabaseWriteTargetError,
    _write_permission_scope,
)
from portfolio_api.market_data_ingestion import (
    _assert_accepted_model_price_plan,
    _private_accepted_price_report,
    run_cli,
)


def clean_preview(listing_id: UUID) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sample = datetime.now(UTC) - timedelta(days=1)
    price = {
        "listing_id": listing_id,
        "currency": "USD",
        "provider": "YAHOO_FINANCE",
        "data_quality": "PASS",
        "price_kind": "DAILY_CLOSE",
        "market_date": sample,
        "split_adjusted_close": 145.0,
    }
    plans: list[dict[str, Any]] = [
        {"batch": {"source_digest": "synthetic"}, "prices": [price], "actions": [], "fx": []}
    ]
    report: dict[str, Any] = {
        "selected_listing_count": 1,
        "verified_listing_mapping_count": 1,
        "market_data_batches": [{"accepted_subjects": 1, "daily_price_rows": 1}],
        "fx_batches": [],
        "required_fx_pairs": [],
        "provider_fetch_failures": [],
        "unresolved_listings": [],
        "selection_issues": [],
    }
    return report, plans


def test_accepted_model_price_writer_has_fixed_minimum_permissions() -> None:
    access = _write_permission_scope(ACCEPTED_MODEL_PRICE_WRITE_OPERATION, "ingestion")
    assert access is not None
    assert access["price_observations"] == frozenset({"SELECT", "INSERT"})
    assert access["market_data_batches"] == frozenset({"SELECT", "INSERT", "UPDATE"})
    assert "financial_models" in access and access["financial_models"] == frozenset({"SELECT"})
    assert "corporate_actions" not in access
    assert "fx_observations" not in access
    assert all("DELETE" not in grants for grants in access.values())
    assert _write_permission_scope("market_data_provider_ingestion", "ingestion") is None
    assert _write_permission_scope("application_write", "application") is None
    with pytest.raises(DatabaseWriteTargetError, match="write_permission_scope_mismatch"):
        _write_permission_scope(ACCEPTED_MODEL_PRICE_WRITE_OPERATION, "import")


@pytest.mark.parametrize(
    "bad",
    [
        "wrong_listing",
        "wrong_currency",
        "stale",
        "fx",
        "corporate_actions",
        "provider_failure",
        "extra_batches",
        "empty_prices",
        "no_mapping",
        "bad_quality",
        "negative_close",
    ],
)
def test_accepted_model_price_plan_blocks_out_of_scope_or_invalid_source(bad: str) -> None:
    listing_id = uuid4()
    report, plans = clean_preview(listing_id)
    if bad == "wrong_listing":
        plans[0]["prices"][0]["listing_id"] = uuid4()
    elif bad == "wrong_currency":
        plans[0]["prices"][0]["currency"] = "EUR"
    elif bad == "stale":
        plans[0]["prices"][0]["market_date"] = datetime.now(UTC) - timedelta(days=12)
    elif bad == "fx":
        plans[0]["fx"] = [{"pair": "USD/EUR"}]
    elif bad == "corporate_actions":
        plans[0]["actions"] = [{"action_type": "SPLIT"}]
    elif bad == "provider_failure":
        report["provider_fetch_failures"] = [{"code": "TIMEOUT"}]
    elif bad == "extra_batches":
        plans.append(plans[0].copy())
    elif bad == "empty_prices":
        plans[0]["prices"] = []
    elif bad == "no_mapping":
        report["verified_listing_mapping_count"] = 0
    elif bad == "bad_quality":
        plans[0]["prices"][0]["data_quality"] = "WARN"
    elif bad == "negative_close":
        plans[0]["prices"][0]["split_adjusted_close"] = -1
    with pytest.raises(ValueError):
        _assert_accepted_model_price_plan(
            report, plans, listing_id, "USD", datetime.now(UTC).date()
        )


def test_accepted_model_price_report_is_private_and_nonoverwriting(tmp_path: Path) -> None:
    target = tmp_path / "bkng.json"
    _private_accepted_price_report(target, {"model_id": "synthetic"})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="new file outside"):
        _private_accepted_price_report(target, {"model_id": "changed"})
    assert json.loads(target.read_text()) == {"model_id": "synthetic"}


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--listing", "NASDAQ:BKNG"],
        ["--lookback-days", "100"],
        ["--start-date", "2026-01-01"],
        ["--end-date", "2020-01-01"],
    ],
)
def test_restricted_price_cli_rejects_unsafe_args_before_database(
    tmp_path: Path, extra: list[str]
) -> None:
    model = uuid4()
    args = ["--accepted-model-id", str(model)]
    if not extra or "--lookback-days" not in extra:
        args.extend(["--lookback-days", "30"])
    args.extend(extra)
    if extra:
        args.extend(["--report", str(tmp_path / "scope.json")])
    with patch("portfolio_api.market_data_ingestion.create_database_engine") as database:
        with pytest.raises(SystemExit) as denied:
            run_cli(args)
        assert denied.value.code == 2
        database.assert_not_called()


@pytest.mark.parametrize("apply", [False, True])
def test_cli_uses_one_accepted_model_quote_and_no_fx(tmp_path: Path, apply: bool) -> None:
    model_id, company_id, listing_id = uuid4(), uuid4(), uuid4()
    report, plans = clean_preview(listing_id)
    expected = {**report, "plans": plans}
    engine = create_engine("sqlite+pysqlite:///:memory:")
    output = tmp_path / "accepted-price.json"
    argv = ["--accepted-model-id", str(model_id), "--lookback-days", "30", "--report", str(output)]
    if apply:
        argv.append("--apply")
    with (
        patch(
            "portfolio_api.market_data_ingestion.create_database_engine", return_value=engine
        ) as factory,
        patch(
            "portfolio_api.market_data_ingestion._accepted_model_price_scope",
            return_value=(company_id, listing_id, uuid4(), "USD", {("nasdaq", "bkng")}),
        ) as scope,
        patch("portfolio_api.market_data_ingestion.load_yahoo_crosswalk"),
        patch("portfolio_api.market_data_ingestion.YahooFinanceProvider"),
        patch(
            "portfolio_api.market_data_ingestion.build_provider_import",
            new_callable=AsyncMock,
            return_value=expected,
        ) as ingest,
        patch(
            "portfolio_api.market_data_ingestion.apply_provider_import",
            return_value={**report, "status": "APPLIED", "persistence": {"price_observations": 1}},
        ) as persist,
    ):
        assert run_cli(argv) == 0
    assert factory.call_args.kwargs["read_only"] is (not apply)
    assert factory.call_args.kwargs["write_operation"] == (
        ACCEPTED_MODEL_PRICE_WRITE_OPERATION if apply else "market_data_provider_ingestion"
    )
    assert ingest.call_args.kwargs["fx_pairs"] == set()
    assert ingest.call_args.kwargs["scope"] == "listings"
    assert ingest.call_args.kwargs["listing_keys"] == {("nasdaq", "bkng")}
    assert ingest.call_args.kwargs["company_ids"] == {company_id}
    assert ingest.call_args.kwargs["include_listing_ids"] == {listing_id}
    assert scope.call_count == (2 if apply else 1)
    assert persist.call_count == (1 if apply else 0)
    assert output.is_file()
    assert output.stat().st_mode & 0o777 == 0o600
