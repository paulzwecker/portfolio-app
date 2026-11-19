"""Synthetic isolated company observation proposal review and safety tests."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import Engine

from portfolio_api.company_observation_proposals import (
    BATCH_ADAPTER,
    KPIObservationBatchV1,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

AGENT_TOKEN = "synthetic-observation-agent-000000000000000000"
REVIEWER_TOKEN = "synthetic-observation-reviewer-000000000000000"
pytestmark = pytest.mark.integration


def _settings(*, acceptance: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        observation_proposals_enabled=True,
        observation_acceptance_enabled=acceptance,
        observation_proposal_agent_token=SecretStr(AGENT_TOKEN),
        observation_proposal_agent_id="synthetic-observation-agent",
        observation_proposal_reviewer_token=SecretStr(REVIEWER_TOKEN),
        observation_proposal_reviewer_id="synthetic-human-reviewer",
    )


def _auth(token: str) -> dict[str, str]:
    return {"X-Observation-Proposal-Token": token}


def _base(company_id: str, contract: str, key: str) -> dict[str, Any]:
    return {
        "contract_type": contract,
        "contract_version": "1.0.0",
        "company_id": company_id,
        "external_batch_id": key,
        "authored_at": datetime.now(UTC).isoformat(),
        "rationale": "Synthetic source data reviewed through the company observation inbox.",
    }


def _definition(company_id: str) -> dict[str, Any]:
    return {
        **_base(company_id, "MetricDefinitionBatchV1", "definition-v1"),
        "items": [
            {
                "metric_key": "synthetic.trips",
                "display_name": "Trips",
                "category": "OPERATING",
                "value_kind": "COUNT",
                "canonical_unit": "trips",
                "canonical_scale": "1000000000",
                "currency_policy": "NONE",
                "aggregation_semantics": "PERIOD_FLOW",
                "default_period_type": "QUARTER",
                "default_basis": "REPORTED",
                "scope_dimensions": [],
                "actuals_allowed": True,
                "guidance_allowed": True,
                "description": "Synthetic mobility trips in billions, excludes unrelated data.",
                "source_reference": "https://example.com/trips-definition",
            }
        ],
    }


def _kpi(company_id: str, key: str, external_id: str) -> dict[str, Any]:
    return {
        **_base(company_id, "KPIObservationBatchV1", key),
        "items": [
            {
                "external_observation_id": external_id,
                "metric_key": "synthetic.trips",
                "period_type": "QUARTER",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "fiscal_year": 2026,
                "fiscal_quarter": 3,
                "value": "4.1",
                "value_qualifier": "GT",
                "unit": "trips",
                "scale": "1000000000",
                "currency": None,
                "basis": "REPORTED",
                "scope_json": {},
                "reported_at": datetime.now(UTC).isoformat(),
                "source_type": "EARNINGS_RELEASE",
                "source_reference": "https://example.com/earnings",
                "quality_status": "VERIFIED",
            }
        ],
    }


def _guidance(company_id: str) -> dict[str, Any]:
    return {
        **_base(company_id, "GuidanceObservationBatchV1", "guidance-v1"),
        "items": [
            {
                "external_guidance_id": "synthetic-next-q-guidance",
                "metric_key": "synthetic.trips",
                "period_type": "QUARTER",
                "period_start": "2027-01-01",
                "period_end": "2027-03-31",
                "fiscal_year": 2027,
                "fiscal_quarter": 1,
                "lower_value": "4.5",
                "midpoint_value": None,
                "upper_value": "5.0",
                "value_qualifier": "RANGE",
                "unit": "trips",
                "scale": "1000000000",
                "currency": None,
                "basis": "COMPANY_GUIDANCE",
                "scope_json": {},
                "issued_at": datetime.now(UTC).isoformat(),
                "source_type": "EARNINGS_RELEASE",
                "source_reference": "https://example.com/guidance",
                "status": "ACTIVE",
            }
        ],
    }


def _submit_preview_accept(client: TestClient, payload: dict[str, Any]) -> str:
    submit = client.post(
        "/v1/company-observation-proposals", json=payload, headers=_auth(AGENT_TOKEN)
    )
    assert submit.status_code == 201, submit.text
    proposal_id = submit.json()["proposal"]["id"]
    preview = client.post(
        f"/v1/company-observation-proposals/{proposal_id}/preview",
        headers=_auth(REVIEWER_TOKEN),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "READY", preview.text
    decision = client.post(
        f"/v1/company-observation-proposals/{proposal_id}/accept",
        headers=_auth(REVIEWER_TOKEN),
        json={
            "preview_fingerprint": preview.json()["preview_fingerprint"],
            "decision_note": "Reviewed synthetic source, qualifier, units and scope.",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "ACCEPTED"
    assert decision.json()["proposal"]["accepted_record_ids"]
    return str(decision.json()["proposal"]["accepted_record_ids"][0])


def test_contract_rejects_agent_supplied_authority_and_floats() -> None:
    payload = _kpi(str(uuid4()), "kpi-test", "source-trips")
    with pytest.raises(ValidationError):
        KPIObservationBatchV1.model_validate({**payload, "reviewer_id": "spoofed"})
    float_payload = _kpi(str(uuid4()), "kpi-test", "source-trips")
    float_payload["items"][0]["value"] = 4.1
    with pytest.raises(ValidationError):
        BATCH_ADAPTER.validate_python(float_payload)


def test_role_permissions_and_default_off_without_database() -> None:
    with TestClient(create_app(_settings())) as client:
        assert (
            client.post(
                "/v1/company-observation-proposals",
                json={},
                headers=_auth(REVIEWER_TOKEN),
            ).status_code
            == 401
        )
        assert client.get("/v1/company-observation-proposals").status_code == 401
        assert (
            client.post(
                f"/v1/company-observation-proposals/{uuid4()}/preview",
                headers=_auth(AGENT_TOKEN),
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/v1/company-observation-proposals/{uuid4()}/accept",
                headers=_auth(AGENT_TOKEN),
                json={"preview_fingerprint": "a" * 64, "decision_note": "Not permitted"},
            ).status_code
            == 401
        )
    with TestClient(create_app(_settings(acceptance=False))) as client:
        assert (
            client.post(
                f"/v1/company-observation-proposals/{uuid4()}/accept",
                headers=_auth(REVIEWER_TOKEN),
                json={"preview_fingerprint": "a" * 64, "decision_note": "No acceptance"},
            ).status_code
            == 403
        )
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert (
            client.get(
                "/v1/company-observation-proposals",
                headers=_auth(REVIEWER_TOKEN),
            ).status_code
            == 503
        )


def test_definition_kpi_guidance_and_correction_flow(postgres_engine: Engine) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(_settings())) as client,
    ):
        company = client.post(
            "/v1/companies", json={"name": "Synthetic proposals", "reporting_currency": "USD"}
        )
        assert company.status_code == 201
        company_id = company.json()["id"]
        definition_id = _submit_preview_accept(client, _definition(company_id))
        definitions = client.get(
            "/v1/company-metric-definitions", params={"company_id": company_id}
        )
        assert definitions.status_code == 200
        assert definitions.json()[0]["id"] == definition_id

        kpi = _kpi(company_id, "kpi-v1", "synthetic-trips-q3")
        accepted_kpi_id = _submit_preview_accept(client, kpi)
        replay = client.post(
            "/v1/company-observation-proposals", json=kpi, headers=_auth(AGENT_TOKEN)
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        mutated = _kpi(company_id, "kpi-v1", "changed-id")
        assert (
            client.post(
                "/v1/company-observation-proposals", json=mutated, headers=_auth(AGENT_TOKEN)
            ).status_code
            == 409
        )

        guidance_id = _submit_preview_accept(client, _guidance(company_id))
        context = client.get(f"/v1/companies/{company_id}/agent-context")
        assert context.status_code == 200, context.text
        assert context.json()["metric_observations"][0]["id"] == accepted_kpi_id
        assert context.json()["guidance_observations"][0]["id"] == guidance_id
        assert context.json()["guidance_observations"][0]["period_end"] == "2027-03-31"

        correction = _kpi(company_id, "kpi-v2", "synthetic-trips-q3-restated")
        correction["items"][0]["supersedes_observation_id"] = accepted_kpi_id
        correction["items"][0]["basis"] = "RESTATED"
        corrected_id = _submit_preview_accept(client, correction)
        history = client.get(
            f"/v1/companies/{company_id}/metric-observations",
            params={"metric_id": "synthetic.trips"},
        )
        assert history.status_code == 200
        by_id = {item["id"]: item for item in history.json()}
        assert by_id[corrected_id]["is_current"] is True
        assert by_id[accepted_kpi_id]["is_current"] is False
        assert by_id[corrected_id]["value_qualifier"] == "GT"
        assert by_id[corrected_id]["scale"] == "1000000000.000000000000"

        duplicate = _kpi(company_id, "duplicate-kpi", "synthetic-different-source")
        submitted = client.post(
            "/v1/company-observation-proposals", json=duplicate, headers=_auth(AGENT_TOKEN)
        )
        assert submitted.status_code == 201
        duplicate_id = submitted.json()["proposal"]["id"]
        preview = client.post(
            f"/v1/company-observation-proposals/{duplicate_id}/preview",
            headers=_auth(REVIEWER_TOKEN),
        )
        assert preview.status_code == 200
        assert preview.json()["status"] == "CONFLICT"
        assert preview.json()["preview_fingerprint"] is None
        rejected = client.post(
            f"/v1/company-observation-proposals/{duplicate_id}/reject",
            headers=_auth(REVIEWER_TOKEN),
            json={"decision_note": "Existing current observation; no supersession."},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"


def test_stale_preview_cannot_accept_competing_kpi(postgres_engine: Engine) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(_settings())) as client,
    ):
        company = client.post(
            "/v1/companies",
            json={"name": "Conflicting source company", "reporting_currency": "USD"},
        ).json()
        company_id = company["id"]
        _submit_preview_accept(client, _definition(company_id))

        first = client.post(
            "/v1/company-observation-proposals",
            json=_kpi(company_id, "first", "competing-source-1"),
            headers=_auth(AGENT_TOKEN),
        ).json()["proposal"]["id"]
        second = client.post(
            "/v1/company-observation-proposals",
            json=_kpi(company_id, "second", "competing-source-2"),
            headers=_auth(AGENT_TOKEN),
        ).json()["proposal"]["id"]
        a = client.post(
            f"/v1/company-observation-proposals/{first}/preview",
            headers=_auth(REVIEWER_TOKEN),
        ).json()
        b = client.post(
            f"/v1/company-observation-proposals/{second}/preview",
            headers=_auth(REVIEWER_TOKEN),
        ).json()
        assert a["status"] == b["status"] == "READY"

        wrong = client.post(
            f"/v1/company-observation-proposals/{first}/accept",
            headers=_auth(REVIEWER_TOKEN),
            json={"preview_fingerprint": "b" * 64, "decision_note": "Wrong reviewer fingerprint"},
        )
        assert wrong.status_code == 409

        accepted = client.post(
            f"/v1/company-observation-proposals/{first}/accept",
            headers=_auth(REVIEWER_TOKEN),
            json={
                "preview_fingerprint": a["preview_fingerprint"],
                "decision_note": "Reviewed first sourced observation.",
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "ACCEPTED"

        stale = client.post(
            f"/v1/company-observation-proposals/{second}/accept",
            headers=_auth(REVIEWER_TOKEN),
            json={
                "preview_fingerprint": b["preview_fingerprint"],
                "decision_note": "Attempt stale reviewer acceptance.",
            },
        )
        assert stale.status_code == 200, stale.text
        assert stale.json()["status"] == "PREVIEW_CHANGED"
        assert stale.json()["proposal"]["status"] == "CONFLICT"

        history = client.get(f"/v1/companies/{company_id}/metric-observations")
        assert history.status_code == 200
        assert len(history.json()) == 1


def test_primary_source_uber_q3_2026_shadow_fixture(postgres_engine: Engine) -> None:
    """Real disclosed numbers, isolated test identity; no production acceptance or scraping."""
    source = (
        "https://investor.uber.com/news-events/news/"
        "press-release-details/2026/"
        "Uber-Announces-Results-for-Third-Quarter-2026/default.aspx"
    )
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(_settings())) as client,
    ):
        company = client.post(
            "/v1/companies",
            json={"name": "Uber public-source TEST fixture", "reporting_currency": "USD"},
        ).json()
        company_id = company["id"]

        definitions = _definition(company_id)
        definitions["external_batch_id"] = "uber-source-metric-registry"
        trip_def = definitions["items"][0]
        trip_def.update(
            metric_key="uber.trips",
            canonical_scale="1000000",
            source_reference=source,
            description="Completed Mobility rides and Delivery orders in the reporting period.",
        )
        booking_def = {
            **trip_def,
            "metric_key": "uber.gross_bookings",
            "display_name": "Gross Bookings",
            "value_kind": "CURRENCY",
            "canonical_unit": "currency",
            "currency_policy": "REQUIRED",
            "description": "Total platform Gross Bookings, not recognized GAAP revenue.",
        }
        definitions["items"] = [trip_def, booking_def]
        _submit_preview_accept(client, definitions)

        actuals = _kpi(company_id, "uber-q3-2026-source-actuals", "uber-trips-2026q3")
        trip = actuals["items"][0]
        trip.update(
            metric_key="uber.trips",
            value="4061",
            scale="1000000",
            value_qualifier="EQ",
            source_reference=source,
            reported_at=None,  # IR release supplies date, not a precise timestamp.
        )
        bookings = {
            **trip,
            "external_observation_id": "uber-gross-bookings-2026q3",
            "metric_key": "uber.gross_bookings",
            "value": "59819",
            "unit": "currency",
            "currency": "USD",
        }
        actuals["items"] = [trip, bookings]
        _submit_preview_accept(client, actuals)

        guidance = _guidance(company_id)
        guidance["external_batch_id"] = "uber-q4-2026-source-guidance"
        g = guidance["items"][0]
        g.update(
            external_guidance_id="uber-q4-2026-gross-bookings-guidance",
            metric_key="uber.gross_bookings",
            period_start="2026-10-01",
            period_end="2026-12-31",
            fiscal_year=2026,
            fiscal_quarter=4,
            lower_value="63250",
            upper_value="65250",
            scale="1000000",
            unit="currency",
            currency="USD",
            issued_at=None,  # Source publication time is not inferred.
            source_reference=source,
        )
        _submit_preview_accept(client, guidance)

        result = client.get(f"/v1/companies/{company_id}/agent-context")
        assert result.status_code == 200, result.text
        observed = {
            row["metric_id"]: row for row in result.json()["metric_observations"]
        }
        assert set(observed) == {"uber.trips", "uber.gross_bookings"}
        assert Decimal(observed["uber.trips"]["value"]) == Decimal("4061")
        assert Decimal(observed["uber.gross_bookings"]["value"]) == Decimal("59819")
        assert observed["uber.gross_bookings"]["currency"] == "USD"
        assert observed["uber.gross_bookings"]["reported_at"] is None
        issued = result.json()["guidance_observations"]
        assert len(issued) == 1
        assert issued[0]["metric_id"] == "uber.gross_bookings"
        assert Decimal(issued[0]["lower_value"]) == Decimal("63250")
        assert Decimal(issued[0]["upper_value"]) == Decimal("65250")
        assert issued[0]["period_end"] == "2026-12-31"
        assert issued[0]["issued_at"] is None
        assert issued[0]["source_reference"] == source
