"""Least-privilege Data & Universe Steward company-context read boundary."""

from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import Company, Portfolio
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

READ_TOKEN = "data-universe-read-fixture-token-000000000000000000"
PROXY_TOKEN = "broad-api-test-fixture-token-000000000000000000"
MODEL_TOKEN = "model-proposal-test-fixture-token-000000000000000000"


def _settings(
    company_ids: str,
    *,
    enabled: bool = True,
    read_token: str = READ_TOKEN,
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="preview",
        database_url=SecretStr(
            "postgresql+psycopg://test:test@192.0.2.1:5432/preview?sslmode=verify-full"
        ),
        api_access_token=SecretStr(PROXY_TOKEN),
        data_universe_read_enabled=enabled,
        data_universe_read_token=SecretStr(read_token),
        data_universe_read_company_ids=company_ids,
    )


def _read_headers(token: str = READ_TOKEN) -> dict[str, str]:
    return {"X-Data-Universe-Read-Token": token}


def test_read_scope_requires_dedicated_token_and_explicit_companies() -> None:
    company_id = str(uuid4())
    assert _settings(company_id).data_universe_read_enabled
    cases: list[dict[str, Any]] = [
        {"data_universe_read_enabled": True},
        {"data_universe_read_enabled": True, "data_universe_read_token": SecretStr(READ_TOKEN)},
        {"data_universe_read_enabled": True, "data_universe_read_company_ids": company_id},
        {
            "data_universe_read_enabled": True,
            "data_universe_read_token": SecretStr(READ_TOKEN),
            "data_universe_read_company_ids": company_id + "," + company_id,
        },
        {
            "data_universe_read_enabled": True,
            "data_universe_read_token": SecretStr(READ_TOKEN),
            "data_universe_read_company_ids": "bad-identity",
        },
    ]
    for kwargs in cases:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)
    with pytest.raises(ValidationError, match="dedicated credential"):
        _settings(company_id, read_token=PROXY_TOKEN)
    with pytest.raises(ValidationError, match="at least 32"):
        _settings(company_id, read_token="short")


def test_scoped_token_cannot_escape_exact_get_or_sibling_routes() -> None:
    allowed = uuid4()
    other = uuid4()
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(_settings(str(allowed)))) as client,
    ):
        path = f"/v1/companies/{allowed}/agent-context"
        # Authorized read reaches the read-only DB dependency, which is absent here.
        authorized = client.get(path, headers=_read_headers())
        assert authorized.status_code == 503
        assert authorized.headers["cache-control"] == "no-store"
        assert client.get(path, headers=_read_headers("wrong")).status_code == 401
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-ACCESS-TOKEN": MODEL_TOKEN}).status_code == 401
        # Existing trusted application proxy read remains intact.
        assert client.get(path, headers={"X-API-ACCESS-TOKEN": PROXY_TOKEN}).status_code == 503
        assert (
            client.get(f"/v1/companies/{other}/agent-context", headers=_read_headers()).status_code
            == 404
        )
        assert client.get(f"/v1/companies/{allowed}", headers=_read_headers()).status_code == 403
        assert (
            client.get(f"/v1/companies/{allowed}/market-data", headers=_read_headers()).status_code
            == 403
        )
        assert (
            client.get(
                f"/v1/companies/{allowed}/agent-context/extra", headers=_read_headers()
            ).status_code
            == 403
        )
        assert client.post(path, headers=_read_headers(), json={}).status_code == 403
        assert (
            client.post(
                "/v1/company-observation-proposals",
                headers=_read_headers(),
                json={},
            ).status_code
            == 403
        )
        assert client.get("/health/live", headers=_read_headers()).status_code == 403


def test_read_token_is_disabled_by_default_even_if_configured() -> None:
    company_id = uuid4()
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(_settings(str(company_id), enabled=False))) as client,
    ):
        assert (
            client.get(
                f"/v1/companies/{company_id}/agent-context",
                headers=_read_headers(),
            ).status_code
            == 401
        )


@pytest.mark.integration
def test_scoped_context_omits_portfolio_and_research_state(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        company = Company(name="Synthetic Agent Read", reporting_currency="USD")
        portfolio = Portfolio(name="Synthetic personal portfolio", base_currency="EUR")
        session.add_all([company, portfolio])
        session.flush()
        company_id, portfolio_id = company.id, portfolio.id

    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(_settings(str(company_id)))) as client,
    ):
        path = f"/v1/companies/{company_id}/agent-context"
        response = client.get(path, headers=_read_headers())
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["contract_type"] == "CompanyAgentContextV1"
        assert payload["company"]["id"] == str(company_id)
        assert payload["portfolio_id"] is None
        assert payload["portfolio"] is None
        assert payload["portfolio_target_revision_id"] is None
        assert payload["portfolio_holdings_authority"] is None
        assert payload["portfolio_status"]["status"] == "UNSUPPORTED"
        assert payload["native_models_status"]["status"] == "UNSUPPORTED"
        assert payload["research_status"]["status"] == "UNSUPPORTED"
        assert payload["thesis_status"]["status"] == "UNSUPPORTED"
        assert payload["imported_outputs_status"]["status"] == "UNSUPPORTED"
        assert payload["native_models"] == []
        assert payload["current_research"] == []
        assert payload["current_theses"] == []
        assert payload["resource_links"] == {}

        assert (
            client.get(
                path,
                headers=_read_headers(),
                params={"portfolio_id": str(portfolio_id)},
            ).status_code
            == 403
        )
        regular = client.get(path, headers={"X-API-ACCESS-TOKEN": PROXY_TOKEN})
        assert regular.status_code == 200, regular.text
        assert regular.json()["portfolio_id"] == str(portfolio_id)
        assert regular.json()["portfolio_status"]["status"] != "UNSUPPORTED"
        assert regular.json()["resource_links"]["financial_statements"].startswith("/v1/")


def test_credential_scope_is_not_substituted_for_general_api_token() -> None:
    company_id = str(UUID("11d5e2d1-9b6f-4403-9491-cbdb1ba0a569"))
    with (
        patch("portfolio_api.main.create_database_engine", return_value=None),
        TestClient(create_app(_settings(company_id))) as client,
    ):
        # Even providing both a valid broad proxy credential and an invalid scoped
        # credential fails closed rather than silently upgrading the request.
        response = client.get(
            f"/v1/companies/{company_id}/agent-context",
            headers={
                "X-Data-Universe-Read-Token": "invalid",
                "X-API-ACCESS-TOKEN": PROXY_TOKEN,
            },
        )
        assert response.status_code == 401
