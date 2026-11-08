"""Fictional sensitivity checks preserve exact inputs and accepted history."""

from decimal import ROUND_HALF_UP, Decimal, localcontext
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import dcf_fixture

from portfolio_api.dcf_sensitivity import calculate_dcf_sensitivity, model_dcf_sensitivity
from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.financial_models import MarketPriceInput, calculate_ufcf_dcf
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


def inputs() -> s.DcfCalculationInput:
    revision = s.FinancialModelRevisionCreate.model_validate(dcf_fixture()["input"])
    return s.DcfCalculationInput(base=revision.base, scenarios=revision.scenarios)


def test_sensitivity_baseline_and_each_cell_reuse_native_engine_without_mutating_inputs() -> None:
    value = inputs()
    original = value.model_dump(mode="json")
    with patch(
        "portfolio_api.dcf_sensitivity.calculate_ufcf_dcf", wraps=calculate_ufcf_dcf
    ) as engine:
        cells = calculate_dcf_sensitivity(value, model_currency="USD")
    assert len(cells) == engine.call_count == 9
    assert len({(cell.discount_rate_shift, cell.terminal_growth_shift) for cell in cells}) == 9
    assert value.model_dump(mode="json") == original
    for call, cell in zip(engine.call_args_list, cells, strict=True):
        shifted = call.args[0]
        assert shifted.base == value.base
        for initial, scenario in zip(value.scenarios, shifted.scenarios, strict=True):
            assert scenario.probability == initial.probability
            assert scenario.year10_ufcf_growth == initial.year10_ufcf_growth
            assert scenario.tail_ufcf_growth == initial.tail_ufcf_growth
            assert scenario.terminal_growth == initial.terminal_growth + cell.terminal_growth_shift
            for old, new in zip(initial.years, scenario.years, strict=True):
                assert new.discount_rate == old.discount_rate + cell.discount_rate_shift
                assert new.model_dump(exclude={"discount_rate"}) == old.model_dump(
                    exclude={"discount_rate"}
                )
        result = calculate_ufcf_dcf(
            shifted,
            model_currency="USD",
            market_price=MarketPriceInput(None, None, None, None, "NO_DATA"),
        )
        with localcontext() as context:
            context.prec = 60
            for name in ("bear_fv", "base_fv", "bull_fv", "weighted_fv"):
                assert getattr(cell, name) == getattr(result, name).quantize(
                    Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP
                )
    baseline = cells[4]
    assert baseline.discount_rate_shift == baseline.terminal_growth_shift == 0
    assert cells[1].weighted_fv is not None
    assert baseline.weighted_fv is not None
    assert cells[7].weighted_fv is not None
    assert cells[1].weighted_fv > baseline.weighted_fv > cells[7].weighted_fv


@pytest.mark.parametrize("rate,growth", [("0.01", "0.005"), ("0", "-0.01"), ("0.999", "0.02")])
def test_invalid_shifted_cells_are_unavailable_without_losing_the_valid_baseline(
    rate: str, growth: str
) -> None:
    raw = inputs().model_dump()
    for scenario in raw["scenarios"]:
        scenario["terminal_growth"] = Decimal(growth)
        for year in scenario["years"]:
            year["discount_rate"] = Decimal(rate)
    cells = calculate_dcf_sensitivity(
        s.DcfCalculationInput.model_validate(raw), model_currency="USD"
    )
    assert cells[4].status == "AVAILABLE"
    invalid = [cell for cell in cells if cell.status == "INVALID_ASSUMPTIONS"]
    assert invalid
    assert all(cell.weighted_fv is None and cell.unavailable_reason for cell in invalid)
    assert all(cell.bear_fv is cell.base_fv is cell.bull_fv is None for cell in invalid)


def test_explicit_tail_and_high_precision_rates_replay_deterministically() -> None:
    raw = inputs().model_dump()
    for scenario in raw["scenarios"]:
        scenario["tail_ufcf_growth"] = [
            {"forecast_year": year, "ufcf_growth": scenario["year10_ufcf_growth"]}
            for year in range(6, 11)
        ]
        scenario["years"][0]["discount_rate"] = Decimal("0.090123456789012345")
    value = s.DcfCalculationInput.model_validate(raw)
    frozen = value.model_dump_json()
    first = calculate_dcf_sensitivity(value, model_currency="USD")
    replay = calculate_dcf_sensitivity(
        s.DcfCalculationInput.model_validate_json(frozen), model_currency="USD"
    )
    assert first == replay
    assert value.model_dump_json() == frozen


@pytest.mark.integration
def test_api_sensitivity_is_read_only_revision_bound_and_rejects_other_models(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db, db.begin():
        company = ops.create_company(db, s.CompanyCreate(name="Fictional sensitivity issuer"))
        security = ops.create_security(
            db, company.id, s.SecurityCreate(name="Ordinary shares", security_type="COMMON_STOCK")
        )
        listing = ops.create_listing(
            db, security.id, s.ListingCreate(venue="SYNTHETIC", ticker="SENS", currency="USD")
        )
        model = ops.create_financial_model(
            db,
            company.id,
            s.FinancialModelCreate(
                model_name="Fictional DCF",
                valuation_listing_id=listing.id,
                model_currency="USD",
                initial_revision=s.FinancialModelRevisionCreate.model_validate(
                    dcf_fixture()["input"]
                ),
            ),
        )
        model_id, revision_id = model.id, model.current_revision_id
        assert revision_id is not None
        before = q.financial_model(db, model_id).model_dump()

    app = create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
    read_only_engine = postgres_engine.execution_options(postgresql_readonly=True)
    with read_only_engine.connect() as connection:
        assert connection.scalar(text("SHOW transaction_read_only")) == "on"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=read_only_engine),
        TestClient(app) as client,
    ):
        path = f"/v1/financial-models/{model_id}/sensitivity"
        response = client.get(path, params={"base_revision_id": str(revision_id)})
        assert response.status_code == 200
        body = s.DcfSensitivityRead.model_validate(response.json())
        assert body.model_id == model_id and body.revision_id == revision_id
        assert len(body.cells) == 9
        assert body.cells[4].weighted_fv == Decimal(
            before["current_revision"]["outputs"]["weighted_fv"]
        )
        assert client.get(path).status_code == 422
        assert client.get(path, params={"base_revision_id": str(uuid4())}).status_code == 409
        assert (
            client.get(
                f"/v1/financial-models/{uuid4()}/sensitivity",
                params={"base_revision_id": str(revision_id)},
            ).status_code
            == 404
        )
        with Session(postgres_engine) as db:
            assert q.financial_model(db, model_id).model_dump() == before
        with Session(postgres_engine) as db, db.begin():
            revised = s.FinancialModelRevisionCreate.model_validate(dcf_fixture()["input"])
            revised.base_revision_id = revision_id
            revised.source_revision_id = "synthetic:dcf:v2"
            ops.append_financial_model_revision(db, model_id, revised)
        assert client.get(path, params={"base_revision_id": str(revision_id)}).status_code == 409


def test_sensitivity_rejects_non_dcf_identity_before_reading_inputs() -> None:
    from unittest.mock import Mock

    from portfolio_api.domain.models import FinancialModel, FinancialModelType

    session = Mock(spec=Session)
    session.get.return_value = FinancialModel(model_type=FinancialModelType.OWNER_CASH_FLOW_10Y)
    with pytest.raises(ops.DomainError, match="UFCF DCF model not found"):
        model_dcf_sensitivity(session, uuid4(), uuid4())
    session.get.assert_called_once()
