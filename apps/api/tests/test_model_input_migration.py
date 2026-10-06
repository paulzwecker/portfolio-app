"""Reconciliation and idempotent import tests for the first real model batch."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelMigrationAssessment,
    FinancialModelOutput,
    FinancialModelRevision,
    Listing,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
    Security,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.main import create_app
from portfolio_api.model_input_migration import (
    DEFAULT_WORKBOOK,
    EXPECTED_MODEL_KEYS,
    REVIEWED_IMPORT_KEYS,
    _legacy_inventory_rows,
    _reconcile_model,
    _screen_active_dcf_cohort,
    _source_price,
    import_native_model_inputs,
    map_supported_models,
)
from portfolio_api.settings import Settings

pytestmark = pytest.mark.integration


def source_workbook() -> Workbook:
    return Workbook.read(DEFAULT_WORKBOOK, lambda name: name in EXPECTED_MODEL_KEYS)


def add_company_listing(
    session: Session,
    *,
    name: str,
    reporting_currency: str,
    security_name: str,
    ticker: str,
    venue: str,
    currency: str,
) -> Company:
    company = Company(name=name, reporting_currency=reporting_currency, is_demo=False)
    session.add(company)
    session.flush()
    security = Security(
        company_id=company.id,
        name=security_name,
        security_type="COMMON_STOCK",
        is_demo=False,
    )
    session.add(security)
    session.flush()
    session.add(
        Listing(
            security_id=security.id,
            ticker=ticker,
            venue=venue,
            currency=currency,
            is_demo=False,
        )
    )
    session.flush()
    return company


def test_authoritative_source_mappings_and_cached_calculations_reconcile() -> None:
    workbook = source_workbook()
    mapped = map_supported_models(workbook, datetime.now(UTC))
    assert [model.model_key for model in mapped] == list(REVIEWED_IMPORT_KEYS)
    googl, tost, asml, isrg, mastercard = mapped
    assert googl.model_currency == "USD"
    assert googl.input_cell_map["base.base_revenue"] == "B17"
    assert googl.input_cell_map["scenarios.BASE.years"] == "J16:N22"
    assert googl.source_price_cell == "B4"
    assert tost.model_currency == "USD"
    assert tost.input_cell_map["base.base_revenue"] == "B5"
    assert tost.input_cell_map["scenarios.BASE.owner_cash_flow_margin"] == "C40:L40"
    assert tost.source_references["base.base_revenue"].startswith("https://www.sec.gov/")
    for model, ticker, currency in (
        (asml, "ASML", "EUR"),
        (isrg, "ISRG", "USD"),
        (mastercard, "MA", "USD"),
    ):
        assert model.ticker == ticker
        assert model.model_currency == currency
        assert model.mapping_version == "legacy-ufcf-dcf-cohort-v1"
        assert model.input_cell_map["base.base_revenue"] == "B17"
        assert model.input_cell_map["scenarios.BASE.years"] == "J16:N22"
        assert model.venue is None

    parity = {model.model_key: _reconcile_model(workbook, model) for model in mapped}
    googl_result = parity["P-GOOGL"]
    tost_result = parity["W-TOST"]
    assert googl_result["status"] == "PARITY_PASS"
    assert googl_result["projection_reconciliation"]["compared"] == 30
    assert googl_result["projection_reconciliation"]["passed"] == 30
    assert googl_result["output_reconciliation"]["compared"] == 22
    assert googl_result["output_reconciliation"]["passed"] == 22
    assert tost_result["status"] == "PARITY_PASS"
    assert tost_result["projection_reconciliation"]["compared"] == 123
    assert tost_result["projection_reconciliation"]["passed"] == 123
    assert tost_result["output_reconciliation"]["compared"] == 22
    assert tost_result["output_reconciliation"]["passed"] == 22
    for model_key in ("P-ASML", "P-ISRG", "P-MA"):
        assert parity[model_key]["status"] == "PARITY_PASS"
        assert parity[model_key]["projection_reconciliation"]["passed"] == 30
        assert parity[model_key]["output_reconciliation"]["passed"] == 22


def test_source_quote_is_used_only_for_parity_and_keeps_effective_date_unknown() -> None:
    mapped = map_supported_models(source_workbook(), datetime.now(UTC))
    assert all(model.values.effective_at.tzinfo is not None for model in mapped)
    assert all(_source_price(model).effective_at is None for model in mapped)
    by_key = {model.model_key: model for model in mapped}
    assert by_key["P-GOOGL"].source_price == Decimal("343.5")
    assert by_key["W-TOST"].source_price == Decimal("29.79")
    assert by_key["P-ASML"].source_price_cell == "B4"
    assert "P-ASML legacy Expected Cash-Flow IRR" in by_key["P-ASML"].legacy_return_semantics
    googl, tost = by_key["P-GOOGL"], by_key["W-TOST"]
    assert googl.legacy_return_semantics.startswith("P-GOOGL legacy Expected Cash-Flow IRR")
    assert (
        "not document owner cash flow as a guaranteed distribution" in tost.legacy_return_semantics
    )


def test_import_creates_reviewed_native_revisions_once_and_records_parity_assessments(
    postgres_engine: Engine,
) -> None:
    accepted_at = datetime.now(UTC) - timedelta(minutes=1)
    workbook = source_workbook()
    with Session(postgres_engine) as session, session.begin():
        add_company_listing(
            session,
            name="Alphabet",
            reporting_currency="USD",
            security_name="Alphabet Class A",
            ticker="GOOGL",
            venue="NASDAQ",
            currency="USD",
        )
        add_company_listing(
            session,
            name="Toast",
            reporting_currency="USD",
            security_name="Toast common stock",
            ticker="TOST",
            venue="NYSE",
            currency="USD",
        )
        for name, ticker, venue, currency in (
            ("ASML Holding", "ASML", "AMS", "EUR"),
            ("Intuitive Surgical", "ISRG", "NASDAQ", "USD"),
            ("Mastercard", "MA", "NYSE", "USD"),
        ):
            add_company_listing(
                session,
                name=name,
                reporting_currency=currency,
                security_name=f"{name} ordinary shares",
                ticker=ticker,
                venue=venue,
                currency=currency,
            )
        first = import_native_model_inputs(session, workbook, accepted_at=accepted_at, apply=True)
        assert first["input_sets_imported"] == 5
        assert first["status_counts"]["PARITY_PASS"] == 5
        assert all(row["apply_status"] == "IMPORTED" for row in first["models"])
        screening = {row["model_key"]: row["status"] for row in first["candidate_screening"]}
        assert screening["P-NVO"] == "BLOCKED"
        assert screening["P-MSCI"] == "DATA_CHECK"
        assert screening["W-GEV"] == "PARTIAL_MAPPING"

    with Session(postgres_engine) as session, session.begin():
        replay = import_native_model_inputs(
            session, workbook, accepted_at=accepted_at + timedelta(seconds=30), apply=True
        )
        assert replay["input_sets_imported"] == 0
        assert replay["input_sets_already_imported"] == 5, [
            (
                row.get("model_key"),
                row.get("status"),
                row.get("apply_status"),
                row.get("identity_blocker"),
            )
            for row in replay["models"]
        ]
        assert [row["apply_status"] for row in replay["models"]] == [
            "ALREADY_IMPORTED",
            "ALREADY_IMPORTED",
            "ALREADY_IMPORTED",
            "ALREADY_IMPORTED",
            "ALREADY_IMPORTED",
        ]
        assert session.scalar(select(func.count()).select_from(FinancialModel)) == 5
        assert session.scalar(select(func.count()).select_from(FinancialModelRevision)) == 5
        assert (
            session.scalar(select(func.count()).select_from(FinancialModelMigrationAssessment)) == 5
        )
        assert session.scalar(select(func.count()).select_from(FinancialModelOutput)) == 5
        revisions = session.scalars(select(FinancialModelRevision)).all()
        assert {row.actor for row in revisions} == {"IMPORT"}
        assert all(row.effective_at == accepted_at for row in revisions)
        assert all("sha256=" in (row.source or "") for row in revisions)
        assert {
            revision_id.rsplit(":", 1)[-1]
            for revision_id in {revision.source_revision_id for revision in revisions}
            if revision_id is not None
            and any(f":{key}:" in revision_id for key in {"P-ASML", "P-ISRG", "P-MA"})
        } == {"legacy-ufcf-dcf-cohort-v1"}
        current_outputs = session.scalars(select(FinancialModelOutput)).all()
        assert all(row.status == "PARTIAL" for row in current_outputs)
        assert all(row.weighted_upside is None for row in current_outputs)
        assert all(row.expected_cash_flow_irr is None for row in current_outputs)
        assessments = session.scalars(select(FinancialModelMigrationAssessment)).all()
        assert {row.status for row in assessments} == {"PARITY_PASS"}
        assert all(
            cast(dict[str, Any], row.report)["source"]["effective_date"] is None
            for row in assessments
        )


def test_company_migration_status_distinguishes_native_output_only_and_unsupported(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        googl = add_company_listing(
            session,
            name="Alphabet",
            reporting_currency="USD",
            security_name="Alphabet Class A",
            ticker="GOOGL",
            venue="NASDAQ",
            currency="USD",
        )
        tost = add_company_listing(
            session,
            name="Toast",
            reporting_currency="USD",
            security_name="Toast common stock",
            ticker="TOST",
            venue="NYSE",
            currency="USD",
        )
        spgi = add_company_listing(
            session,
            name="S&P Global",
            reporting_currency="USD",
            security_name="S&P Global common stock",
            ticker="SPGI",
            venue="NYSE",
            currency="USD",
        )
        adyen = add_company_listing(
            session,
            name="Adyen",
            reporting_currency="EUR",
            security_name="Adyen common stock",
            ticker="ADYEN",
            venue="AMS",
            currency="EUR",
        )
        batch = ModelOutputImportBatch(
            id=uuid4(),
            source_digest="1" * 64,
            workbook_sha256="2" * 64,
            observed_at=datetime.now(UTC),
            reconciliation={},
        )
        session.add(batch)
        session.flush()
        imported = import_native_model_inputs(
            session,
            source_workbook(),
            accepted_at=datetime.now(UTC),
            apply=True,
        )
        assert imported["input_sets_imported"] == 2
        session.add(
            ModelOutputSnapshot(
                company_id=adyen.id,
                batch_id=batch.id,
                model_key="P-ADYEN",
                snapshot_key="current-test",
                source_fingerprint="3" * 64,
                snapshot_kind="CURRENT_CONTRACT",
                contract_version="v1",
                contract_status="PASS",
                output_quality="COMPLETE",
                model_currency="EUR",
                currency_status="DOCUMENTED",
                currency_source_ref="test",
                effective_at=None,
                actor="IMPORT",
                source="fixture",
            )
        )
        session.flush()
        companies = {
            "GOOGL": googl.id,
            "TOST": tost.id,
            "SPGI": spgi.id,
            "ADYEN": adyen.id,
        }

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        for ticker, expected_status in {
            "GOOGL": "NATIVE_EDITABLE",
            "TOST": "NATIVE_EDITABLE",
            "SPGI": "UNSUPPORTED_LEGACY",
            "ADYEN": "IMPORTED_OUTPUT_ONLY",
        }.items():
            response = client.get(f"/v1/companies/{companies[ticker]}/model-migration-status")
            assert response.status_code == 200, response.text
            item = next(
                row for row in response.json()["models"] if row["canonical_ticker"] == ticker
            )
            assert item["representation_status"] == expected_status
            if ticker in {"GOOGL", "TOST"}:
                assert item["native_revision_number"] == 1
                assert item["parity_status"] == "PARITY_PASS"
        assert (
            client.get(f"/v1/companies/{companies['GOOGL']}/model-migration-status").status_code
            == 200
        )


def test_migration_mapping_is_limited_to_parity_proven_active_tabs() -> None:
    inventory = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "docs/reconciliation/model-migration-inventory-2026-10-05.json"
        ).read_text(encoding="utf-8")
    )
    assert inventory["recommended_batches"][0]["model_tabs"] == sorted(REVIEWED_IMPORT_KEYS)
    assert {
        model.model_key for model in map_supported_models(source_workbook(), datetime.now(UTC))
    } == set(REVIEWED_IMPORT_KEYS)


def test_active_dcf_screening_keeps_incomplete_and_nonparity_inputs_out_of_native_models() -> None:
    screening = _screen_active_dcf_cohort(
        source_workbook(),
        datetime.now(UTC),
        _legacy_inventory_rows(),
    )
    statuses = {row["model_key"]: row["status"] for row in screening}
    assert statuses["P-NVO"] == "BLOCKED"
    assert statuses["P-MSCI"] == "DATA_CHECK"
    assert statuses["W-GEV"] == "PARTIAL_MAPPING"
    assert statuses["P-ADYEN"] == "DATA_CHECK"
    assert statuses["P-AMZN"] == "DATA_CHECK"
