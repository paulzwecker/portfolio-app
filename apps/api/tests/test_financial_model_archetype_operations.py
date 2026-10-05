"""Persistence and revision-history integration for additional model methods."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    FinancialModelRevision,
    OwnerCashFlowProjection,
    ResidualIncomeProjection,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.integration


def fixture_data(filename: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / filename).read_text(encoding="utf-8")))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@pytest.mark.parametrize(
    ("fixture_name", "method", "currency", "projection_model"),
    [
        (
            "w_tost_owner_cash_flow_v1.json",
            "owner-cash-flow",
            "USD",
            OwnerCashFlowProjection,
        ),
        (
            "w_hdfc_residual_income_v1.json",
            "residual-income",
            "INR",
            ResidualIncomeProjection,
        ),
    ],
)
def test_additional_archetype_models_create_append_and_read_immutable_history(
    postgres_engine: Engine,
    fixture_name: str,
    method: str,
    currency: str,
    projection_model: type[OwnerCashFlowProjection] | type[ResidualIncomeProjection],
) -> None:
    with (
        patch_engine(postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        fixture = fixture_data(fixture_name)
        company = client.post(
            "/v1/companies",
            json={"name": f"{fixture['model_key']} model fixture", "reporting_currency": currency},
        ).json()
        company_id = company["id"]
        security = client.post(
            f"/v1/companies/{company_id}/securities",
            json={"name": f"{fixture['model_key']} ordinary", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "PARITY", "ticker": fixture["model_key"], "currency": currency},
        ).json()
        initial_revision = {
            **copy.deepcopy(fixture["input"]),
            "base_revision_id": None,
            "source_revision_id": None,
            "actor": "LOCAL_USER",
            "source": "Workbook parity fixture",
            "rationale": "Initial representative workbook methodology fixture.",
            "effective_at": now_iso(),
        }
        response = client.post(
            f"/v1/companies/{company_id}/canonical-financial-models/{method}",
            json={
                "model_name": f"{fixture['model_key']} {method}",
                "valuation_listing_id": listing["id"],
                "model_currency": currency,
                "source_model_key": fixture["model_key"],
                "initial_revision": initial_revision,
            },
        )
        assert response.status_code == 201, response.text
        model = response.json()
        revision1 = model["current_revision"]
        assert len(revision1["projections"]) == 30
        assert revision1["outputs"]["status"] == "PARTIAL"
        assert revision1["outputs"]["weighted_fv"] is not None
        assert revision1["outputs"]["weighted_upside"] is None
        assert revision1["outputs"]["expected_cash_flow_irr"] is None

        edited = copy.deepcopy(fixture["input"])
        if method == "owner-cash-flow":
            edited["scenarios"][1]["years"][0]["owner_cash_flow_margin"] = "0.051"
        else:
            edited["scenarios"][1]["starting_roe"] = "0.156"
        accepted = client.post(
            f"/v1/canonical-financial-models/{model['id']}/{method}/revisions",
            json={
                **edited,
                "base_revision_id": revision1["id"],
                "source_revision_id": None,
                "actor": "LOCAL_USER",
                "source": "Company Explorer",
                "rationale": "Updated an explicitly editable methodology assumption.",
                "effective_at": now_iso(),
            },
        )
        assert accepted.status_code == 201, accepted.text
        revision2 = accepted.json()
        assert revision2["revision_number"] == 2
        assert revision2["base_revision_id"] == revision1["id"]
        assert len(client.get(f"/v1/companies/{company_id}/canonical-financial-models").json()) == 1
        historical = client.get(
            f"/v1/canonical-financial-models/{model['id']}/revisions/{revision1['id']}"
        )
        assert historical.status_code == 200
        assert historical.json()["outputs"] == revision1["outputs"]
        with Session(postgres_engine) as db:
            assert (
                len(
                    db.query(projection_model)
                    .join(
                        FinancialModelRevision,
                        projection_model.revision_id == FinancialModelRevision.id,
                    )
                    .filter(FinancialModelRevision.model_id == model["id"])
                    .all()
                )
                == 60
            )


def patch_engine(engine: Engine) -> Any:
    """Keep the integration app on the isolated schema created by the fixture."""
    from unittest.mock import patch

    return patch("portfolio_api.main.create_database_engine", return_value=engine)


def test_owner_cash_flow_portable_contract_round_trip_and_stale_base_conflict(
    postgres_engine: Engine,
) -> None:
    with (
        patch_engine(postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        fixture = fixture_data("w_tost_owner_cash_flow_v1.json")
        company = client.post(
            "/v1/companies", json={"name": "TOST contract fixture", "reporting_currency": "USD"}
        ).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Toast common", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "NYSE", "ticker": "TOST", "currency": "USD"},
        ).json()
        payload = {
            "model_name": "Toast owner cash flow",
            "valuation_listing_id": listing["id"],
            "model_currency": "USD",
            "source_model_key": "W-TOST",
            "initial_revision": {
                **fixture["input"],
                "base_revision_id": None,
                "source_revision_id": None,
                "actor": "LOCAL_USER",
                "source": "W-TOST parity fixture",
                "rationale": "Initial owner cash-flow model.",
                "effective_at": now_iso(),
            },
        }
        created = client.post(
            f"/v1/companies/{company['id']}/canonical-financial-models/owner-cash-flow",
            json=payload,
        )
        assert created.status_code == 201, created.text
        model_id = created.json()["id"]
        contract = client.get(f"/v1/canonical-financial-models/{model_id}/contract").json()
        candidate = contract["candidate_revision"]
        candidate["source_revision_id"] = "sheet-pass-1"
        candidate["rationale"] = "Expanded Year 1 owner cash-flow margin after review."
        candidate["owner_cash_flow"]["scenarios"][1]["years"][0]["owner_cash_flow_margin"] = "0.051"
        preview = client.post(
            f"/v1/canonical-financial-models/{model_id}/contract/preview", json=contract
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "READY"
        assert preview.json()["output_changes"]
        imported = client.post(
            f"/v1/canonical-financial-models/{model_id}/contract/import", json=contract
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["revision"]["actor"] == "IMPORT"
        replay = client.post(
            f"/v1/canonical-financial-models/{model_id}/contract/import", json=contract
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["status"] == "ALREADY_IMPORTED"

        stale = client.get(f"/v1/canonical-financial-models/{model_id}/contract").json()
        stale["candidate_revision"]["source_revision_id"] = "sheet-pass-stale"
        stale["candidate_revision"]["rationale"] = "A later external change based on old state."
        stale["candidate_revision"]["owner_cash_flow"]["scenarios"][0]["years"][0][
            "owner_cash_flow_margin"
        ] = "0.031"
        web_update = copy.deepcopy(stale["candidate_revision"]["owner_cash_flow"])
        current = imported.json()["model"]["current_revision"]
        web_update["scenarios"][0]["years"][1]["owner_cash_flow_margin"] = "0.041"
        accepted = client.post(
            f"/v1/canonical-financial-models/{model_id}/owner-cash-flow/revisions",
            json={
                **web_update,
                "base_revision_id": current["id"],
                "actor": "LOCAL_USER",
                "source": "Company Explorer",
                "rationale": "Accepted a newer web edit.",
                "effective_at": now_iso(),
            },
        )
        assert accepted.status_code == 201, accepted.text
        conflict = client.post(
            f"/v1/canonical-financial-models/{model_id}/contract/preview", json=stale
        )
        assert conflict.status_code == 200, conflict.text
        assert conflict.json()["status"] == "CONFLICT"
