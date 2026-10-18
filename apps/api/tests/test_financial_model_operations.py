"""API/storage integration for canonical model creation and append-only revisions."""

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import dcf_fixture

from portfolio_api.domain.models import (
    DcfProjection,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    PriceObservation,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def fixture_payload() -> dict[str, object]:
    return cast(dict[str, object], dcf_fixture())


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


pytestmark = pytest.mark.integration


def test_canonical_dcf_api_persists_projection_output_and_immutable_revision_history(
    postgres_engine: Engine,
) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post(
            "/v1/companies",
            json={"name": "Synthetic issuer", "reporting_currency": "USD"},
        ).json()
        company_id = company["id"]
        security = client.post(
            f"/v1/companies/{company_id}/securities",
            json={"name": "Synthetic common stock", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "XNAS", "ticker": "SYNTH", "currency": "USD"},
        ).json()

        observed_at = datetime.now(UTC) - timedelta(days=1)
        with Session(postgres_engine) as db, db.begin():
            db.add(
                PriceObservation(
                    listing_id=UUID(listing["id"]),
                    market_date=observed_at,
                    provider_close=Decimal("20"),
                    split_adjusted_close=Decimal("20"),
                    total_return_close=None,
                    volume=None,
                    currency="USD",
                    provider="fixture-provider",
                    provider_symbol="XNAS:SYNTH",
                    adjustment_basis="Reference price fixture",
                    data_quality="PASS",
                    source_ref="test-financial-model:synthetic-price-v1",
                )
            )

        fixture = fixture_payload()
        initial_revision = copy.deepcopy(fixture["input"])
        assert isinstance(initial_revision, dict)
        initial_revision["effective_at"] = observed_at.isoformat()
        initial_preview = client.post(
            f"/v1/companies/{company_id}/financial-models/preview",
            json={
                "valuation_listing_id": listing["id"],
                "model_currency": "USD",
                "base": initial_revision["base"],
                "scenarios": initial_revision["scenarios"],
            },
        )
        assert initial_preview.status_code == 200, initial_preview.text
        assert len(initial_preview.json()["projections"]) == 30
        assert initial_preview.json()["model_id"] is None
        assert initial_preview.json()["outputs"]["status"] == "COMPLETE"
        assert initial_preview.json()["outputs"]["return_methodology"]["code"] == (
            "UFCF_ENTERPRISE_IRR"
        )
        assert initial_preview.json()["outputs"]["return_methodology"]["perspective"] == (
            "ENTERPRISE"
        )
        create = client.post(
            f"/v1/companies/{company_id}/financial-models",
            json={
                "model_type": "UFCF_DCF_10Y_FADE",
                "model_name": "Synthetic issuer operating UFCF DCF",
                "valuation_listing_id": listing["id"],
                "model_currency": "USD",
                "source_model_key": "SYNTHETIC_DCF",
                "initial_revision": initial_revision,
            },
        )
        assert create.status_code == 201, create.text
        first = create.json()
        model_id = first["id"]
        revision1 = first["current_revision"]
        outputs1 = revision1["outputs"]
        assert outputs1["return_methodology"]["code"] == "UFCF_ENTERPRISE_IRR"
        expected = fixture["expected"]
        assert isinstance(expected, dict)
        for field in (
            "bear_fv",
            "base_fv",
            "bull_fv",
            "weighted_fv",
            "weighted_upside",
            "expected_cash_flow_irr",
            "hurdle",
            "expected_excess",
        ):
            assert abs(Decimal(outputs1[field]) - Decimal(str(expected[field]))) < Decimal(
                "0.0000001"
            )
        assert outputs1["status"] == "COMPLETE"
        assert outputs1["price_observation_id"] is not None
        assert len(revision1["projections"]) == 30
        assert all(
            row["revenue"] is None for row in revision1["projections"] if row["forecast_year"] > 5
        )
        assert first["valuation_listing"]["id"] == listing["id"]
        assert len(first["history"]) == 1

        quote_observed_at = datetime.now(UTC)
        with Session(postgres_engine) as db, db.begin():
            db.add(
                PriceObservation(
                    listing_id=UUID(listing["id"]),
                    market_date=quote_observed_at,
                    provider_close=Decimal("25"),
                    split_adjusted_close=Decimal("25"),
                    total_return_close=None,
                    volume=None,
                    currency="USD",
                    provider="fixture-provider",
                    provider_symbol="XNAS:SYNTH",
                    adjustment_basis="Reference price fixture",
                    data_quality="PASS",
                    source_ref="test-financial-model:synthetic-price-current-v2",
                )
            )
        known_at = (quote_observed_at + timedelta(seconds=2)).isoformat()
        current_state = client.get(
            f"/v1/companies/{company_id}/expected-return-history",
            params={"as_of": quote_observed_at.date().isoformat(), "known_at": known_at},
        )
        assert current_state.status_code == 200, current_state.text
        assert current_state.json()["current_calculations"], current_state.json()
        current_calculations = current_state.json()["current_calculations"]
        current_calculation = next(
            (item for item in current_calculations if item["revision_id"] == revision1["id"]),
            None,
        )
        assert current_calculation is not None, current_calculations
        assert current_calculation["market_price"]["listing_id"] == listing["id"]
        assert (
            current_calculation["outputs"]["price_observation_id"]
            != outputs1["price_observation_id"]
        )
        assert Decimal(current_calculation["outputs"]["current_price"]) == Decimal("25")
        assert Decimal(current_calculation["accepted_reference_price"]) == Decimal("20")
        assert Decimal(current_calculation["outputs"]["expected_cash_flow_irr"]) != Decimal(
            outputs1["expected_cash_flow_irr"]
        )

        historical_state = client.get(
            f"/v1/companies/{company_id}/expected-return-history",
            params={"as_of": observed_at.date().isoformat(), "known_at": known_at},
        )
        assert historical_state.status_code == 200, historical_state.text
        historical_calculation = next(
            item
            for item in historical_state.json()["current_calculations"]
            if item["revision_id"] == revision1["id"]
        )
        assert (
            historical_calculation["outputs"]["price_observation_id"]
            == outputs1["price_observation_id"]
        )
        assert (
            historical_calculation["outputs"]["expected_cash_flow_irr"]
            == outputs1["expected_cash_flow_irr"]
        )
        unchanged_revision = client.get(
            f"/v1/financial-models/{model_id}/revisions/{revision1['id']}"
        )
        assert unchanged_revision.status_code == 200
        assert unchanged_revision.json()["outputs"] == outputs1
        assert len(client.get(f"/v1/financial-models/{model_id}/revisions").json()) == 1

        edit = copy.deepcopy(initial_revision)
        edit["base_revision_id"] = revision1["id"]
        edit["source_revision_id"] = None
        edit["actor"] = "LOCAL_USER"
        edit["source"] = "Company Explorer"
        edit["rationale"] = "Updated the Base Y1 growth assumption after review."
        edit["effective_at"] = now_iso()
        edit["scenarios"][1]["years"][0]["revenue_growth"] = "0.21"
        endpoint = edit["scenarios"][1]["year10_ufcf_growth"]
        edit["scenarios"][1]["tail_ufcf_growth"] = [
            {"forecast_year": year, "ufcf_growth": rate}
            for year, rate in zip(
                range(6, 11), ["0.12", "0.10", "0.08", "0.06", endpoint], strict=True
            )
        ]
        preview = client.post(
            f"/v1/financial-models/{model_id}/revisions/preview",
            json={
                "base_revision_id": revision1["id"],
                "base": edit["base"],
                "scenarios": edit["scenarios"],
            },
        )
        assert preview.status_code == 200, preview.text
        preview_data = preview.json()
        assert preview_data["current_revision_id"] == revision1["id"]
        assert preview_data["current_revision_number"] == 1
        assert len(preview_data["projections"]) == 30
        assert preview_data["outputs"]["base_fv"] != outputs1["base_fv"]
        assert (
            client.get(f"/v1/financial-models/{model_id}").json()["current_revision_id"]
            == revision1["id"]
        )
        accepted = client.post(f"/v1/financial-models/{model_id}/revisions", json=edit)
        assert accepted.status_code == 201, accepted.text
        revision2 = accepted.json()
        assert revision2["revision_number"] == 2
        assert revision2["base_revision_id"] == revision1["id"]
        assert revision2["outputs"]["base_fv"] != outputs1["base_fv"]
        assert revision2["outputs"]["base_fv"] == preview_data["outputs"]["base_fv"]
        assert revision2["methodology_version"] == "ufcf-dcf-explicit-tail-v1"
        assert [
            Decimal(row["ufcf_growth"]) for row in revision2["scenarios"][1]["tail_ufcf_growth"]
        ] == [
            Decimal("0.12"),
            Decimal("0.10"),
            Decimal("0.08"),
            Decimal("0.06"),
            Decimal(endpoint),
        ]
        stale_preview = client.post(
            f"/v1/financial-models/{model_id}/revisions/preview",
            json={
                "base_revision_id": revision1["id"],
                "base": edit["base"],
                "scenarios": edit["scenarios"],
            },
        )
        assert stale_preview.status_code == 409

        history = client.get(f"/v1/financial-models/{model_id}/revisions")
        assert history.status_code == 200
        assert [item["revision_number"] for item in history.json()] == [2, 1]
        old = client.get(f"/v1/financial-models/{model_id}/revisions/{revision1['id']}")
        assert old.status_code == 200
        assert old.json()["outputs"]["base_fv"] == outputs1["base_fv"]
        assert Decimal(old.json()["scenarios"][1]["years"][0]["revenue_growth"]) == Decimal("0.08")

        conflict = client.post(f"/v1/financial-models/{model_id}/revisions", json=edit)
        assert conflict.status_code == 409

        company_models = client.get(f"/v1/companies/{company_id}/financial-models")
        assert company_models.status_code == 200
        assert company_models.json()[0]["current_revision_id"] == revision2["id"]

        exported_response = client.get(f"/v1/financial-models/{model_id}/contract")
        assert exported_response.status_code == 200, exported_response.text
        contract = exported_response.json()
        assert contract["contract_version"] == "1.2.0"
        # This test exercises compatibility with pre-evidence portable contracts.
        contract["contract_version"] = "1.1.0"
        assert contract["candidate_revision"]["scenarios"][1]["tail_ufcf_growth"]
        invalid_version = copy.deepcopy(contract)
        invalid_version["contract_version"] = "2.0.0"
        assert (
            client.post(
                f"/v1/financial-models/{model_id}/contract/preview",
                json=invalid_version,
            ).status_code
            == 422
        )
        naive_export_time = copy.deepcopy(contract)
        naive_export_time["exported_at"] = "2026-10-05T00:00:00"
        assert (
            client.post(
                f"/v1/financial-models/{model_id}/contract/preview",
                json=naive_export_time,
            ).status_code
            == 422
        )
        no_change = client.post(f"/v1/financial-models/{model_id}/contract/preview", json=contract)
        assert no_change.status_code == 200, no_change.text
        assert no_change.json()["status"] == "NO_CHANGES"

        invalid_snapshot = copy.deepcopy(contract)
        invalid_snapshot["base_calculation"]["outputs"]["base_fv"] = "999"
        invalid = client.post(
            f"/v1/financial-models/{model_id}/contract/preview", json=invalid_snapshot
        )
        assert invalid.status_code == 200, invalid.text
        assert invalid.json()["status"] == "INVALID_BASE_SNAPSHOT"

        candidate = contract["candidate_revision"]
        candidate["scenarios"][1]["years"][0]["revenue_growth"] = "0.22"
        candidate["scenarios"][1]["tail_ufcf_growth"][0]["ufcf_growth"] = "0.13"
        missing_rationale = client.post(
            f"/v1/financial-models/{model_id}/contract/preview", json=contract
        )
        assert missing_rationale.status_code == 200, missing_rationale.text
        assert missing_rationale.json()["status"] == "RATIONALE_REQUIRED"
        candidate["rationale"] = "External review updated the Base case growth assumption."

        preview = client.post(f"/v1/financial-models/{model_id}/contract/preview", json=contract)
        assert preview.status_code == 200, preview.text
        preview_data = preview.json()
        assert preview_data["status"] == "READY"
        assert preview_data["proposed_revision_number"] == 3
        assert preview_data["source_revision_id"] == candidate["source_revision_id"]
        assert preview_data["actor"] == "IMPORT"
        assert preview_data["effective_at"] == candidate["effective_at"]
        assert any(
            item["path"] == "scenarios.BASE.years.1.revenue_growth"
            for item in preview_data["changes"]
        )
        assert any(
            item["path"] == "scenarios.BASE.tail_ufcf_growth.6" for item in preview_data["changes"]
        )
        assert preview_data["output_changes"]

        imported = client.post(f"/v1/financial-models/{model_id}/contract/import", json=contract)
        assert imported.status_code == 200, imported.text
        imported_data = imported.json()
        assert imported_data["status"] == "IMPORTED"
        revision3 = imported_data["revision"]
        assert revision3["revision_number"] == 3
        assert revision3["actor"] == "IMPORT"
        assert revision3["methodology_version"] == "ufcf-dcf-explicit-tail-v1"
        assert revision3["source_revision_id"] == candidate["source_revision_id"]
        assert revision3["base_revision_id"] == revision2["id"]
        for field in (
            "bear_fv",
            "base_fv",
            "bull_fv",
            "weighted_fv",
            "weighted_upside",
            "expected_cash_flow_irr",
            "hurdle",
            "expected_excess",
            "status",
            "price_status",
        ):
            assert revision3["outputs"][field] == preview_data["calculated_outputs"][field]
        assert revision3["outputs"]["base_fv"] != revision2["outputs"]["base_fv"]
        assert Decimal(revision3["scenarios"][1]["tail_ufcf_growth"][0]["ufcf_growth"]) == Decimal(
            "0.13"
        )

        repeated_import = client.post(
            f"/v1/financial-models/{model_id}/contract/import", json=contract
        )
        assert repeated_import.status_code == 200, repeated_import.text
        assert repeated_import.json()["status"] == "ALREADY_IMPORTED"
        assert repeated_import.json()["revision"]["id"] == revision3["id"]

        reused_identity = copy.deepcopy(contract)
        reused_identity["candidate_revision"]["rationale"] += " changed after acceptance"
        changed_retry = client.post(
            f"/v1/financial-models/{model_id}/contract/preview", json=reused_identity
        )
        assert changed_retry.status_code == 200
        assert changed_retry.json()["status"] == "CONFLICT"

        stale_contract = copy.deepcopy(contract)
        stale_contract["candidate_revision"]["source_revision_id"] += "-followup"
        stale_contract["candidate_revision"]["rationale"] = (
            "A second external edit based on the now older application revision."
        )
        stale_contract["candidate_revision"]["scenarios"][1]["years"][0]["revenue_growth"] = "0.225"

        local_after_import = copy.deepcopy(edit)
        local_after_import["base_revision_id"] = revision3["id"]
        local_after_import["source_revision_id"] = None
        local_after_import["actor"] = "LOCAL_USER"
        local_after_import["rationale"] = "A later in-app review updated the same driver."
        local_after_import["scenarios"][1]["years"][0]["revenue_growth"] = "0.23"
        revision4 = client.post(
            f"/v1/financial-models/{model_id}/revisions", json=local_after_import
        )
        assert revision4.status_code == 201, revision4.text
        assert revision4.json()["revision_number"] == 4

        retry_after_newer_revision = client.post(
            f"/v1/financial-models/{model_id}/contract/import", json=contract
        )
        assert retry_after_newer_revision.status_code == 200
        assert retry_after_newer_revision.json()["status"] == "ALREADY_IMPORTED"
        assert (
            retry_after_newer_revision.json()["model"]["current_revision_id"]
            == (revision4.json()["id"])
        )
        assert retry_after_newer_revision.json()["revision"]["id"] == revision3["id"]

        stale_preview = client.post(
            f"/v1/financial-models/{model_id}/contract/preview", json=stale_contract
        )
        assert stale_preview.status_code == 200, stale_preview.text
        assert stale_preview.json()["status"] == "CONFLICT"
        stale_import = client.post(
            f"/v1/financial-models/{model_id}/contract/import", json=stale_contract
        )
        assert stale_import.status_code == 409
        assert (
            client.get(f"/v1/financial-models/{model_id}").json()["current_revision_id"]
            == revision4.json()["id"]
        )

    with Session(postgres_engine) as db:
        model = db.get(FinancialModel, model_id)
        assert model is not None
        revisions = db.scalars(
            select(FinancialModelRevision)
            .where(FinancialModelRevision.model_id == model.id)
            .order_by(FinancialModelRevision.revision_number)
        ).all()
        assert len(revisions) == 4
        outputs = db.scalars(select(FinancialModelOutput)).all()
        assert len(outputs) == 4
        projections = db.scalars(select(DcfProjection)).all()
        assert len(projections) == 120
        assert revisions[2].contract_digest is not None
        assert len(revisions[2].contract_digest) == 64

        db.rollback()
        with pytest.raises(ValueError, match="append-only"), db.begin():
            original = db.get(FinancialModelRevision, revisions[0].id)
            assert original is not None
            original.rationale = "Attempted historical overwrite"
            db.flush()


def test_canonical_model_requires_company_listing_and_explicit_currency(
    postgres_engine: Engine,
) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post("/v1/companies", json={"name": "Model identity issuer"}).json()
        other = client.post("/v1/companies", json={"name": "Other issuer"}).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Ordinary", "security_type": "COMMON_STOCK"},
        ).json()
        other_security = client.post(
            f"/v1/companies/{other['id']}/securities",
            json={"name": "Other ordinary", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "X-ONE", "ticker": "ONE", "currency": None},
        ).json()
        other_listing = client.post(
            f"/v1/securities/{other_security['id']}/listings",
            json={"venue": "X-TWO", "ticker": "TWO", "currency": "USD"},
        ).json()
        fixture = fixture_payload()
        initial = copy.deepcopy(fixture["input"])
        assert isinstance(initial, dict)
        initial["effective_at"] = now_iso()
        payload = {
            "model_name": "Identity check DCF",
            "valuation_listing_id": other_listing["id"],
            "model_currency": "USD",
            "initial_revision": initial,
        }
        assert (
            client.post(f"/v1/companies/{company['id']}/financial-models", json=payload).status_code
            == 422
        )
        payload["valuation_listing_id"] = listing["id"]
        payload["model_currency"] = None
        assert (
            client.post(f"/v1/companies/{company['id']}/financial-models", json=payload).status_code
            == 422
        )
