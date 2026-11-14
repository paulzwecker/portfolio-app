"""Independent arithmetic and read-only integration for hypothetical entry pricing."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import (
    dcf_fixture,
    owner_cash_flow_fixture,
    residual_income_fixture,
)

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import FinancialModel, FinancialModelRevision, PriceObservation
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_models import DcfCalculation, MarketPriceInput, calculate_ufcf_dcf
from portfolio_api.main import create_app
from portfolio_api.return_hurdle import (
    NativeInputs,
    ReturnStream,
    _entry_price,
    calculate_return_hurdle,
    model_return_hurdle,
)
from portfolio_api.return_semantics import (
    OWNER_CASH_FLOW_EQUITY_IRR,
    RESIDUAL_INCOME_EQUITY_IRR,
    UFCF_ENTERPRISE_HMODEL_IRR,
    UFCF_ENTERPRISE_IRR,
)
from portfolio_api.settings import Settings

METHODS = [
    UFCF_ENTERPRISE_IRR,
    UFCF_ENTERPRISE_HMODEL_IRR,
    OWNER_CASH_FLOW_EQUITY_IRR,
    RESIDUAL_INCOME_EQUITY_IRR,
]


def inputs_for(method: str) -> NativeInputs:
    if method == OWNER_CASH_FLOW_EQUITY_IRR:
        return s.OwnerCashFlowInput.model_validate(owner_cash_flow_fixture()["input"])
    if method == RESIDUAL_INCOME_EQUITY_IRR:
        return s.ResidualIncomeInput.model_validate(residual_income_fixture()["input"])
    revision = s.FinancialModelRevisionCreate.model_validate(dcf_fixture()["input"])
    return s.DcfCalculationInput(base=revision.base, scenarios=revision.scenarios)


def native(
    inputs: NativeInputs, method: str, price: Decimal
) -> DcfCalculation | ArchetypeCalculation:
    quote = MarketPriceInput(None, price, "USD", None, "FRESH")
    if isinstance(inputs, s.DcfCalculationInput):
        return calculate_ufcf_dcf(
            inputs, model_currency="USD", market_price=quote, return_methodology_code=method
        )
    if isinstance(inputs, s.OwnerCashFlowInput):
        return calculate_owner_cash_flow(inputs, model_currency="USD", market_price=quote)
    return calculate_residual_income(inputs, model_currency="USD", market_price=quote)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("target", ["0", "0.1", "0.35", "0.999"])
def test_target_prices_round_trip_and_leave_all_accepted_inputs_frozen(
    method: str, target: str
) -> None:
    value = inputs_for(method)
    before = value.model_dump_json()
    result = calculate_return_hurdle(
        value,
        currency="USD",
        method=method,
        required_return=Decimal(target),
        entry_price=Decimal("20"),
    )
    assert value.model_dump_json() == before
    assert result.weighted_entry_price is not None
    assert result.reconciled_irr is not None
    assert abs(result.reconciled_irr - Decimal(target)) < Decimal("1e-12")
    assert result.hypothetical_expected_irr is not None
    expected_irr = native(value, method, Decimal("20")).expected_cash_flow_irr
    assert expected_irr is not None
    assert abs(result.hypothetical_expected_irr - expected_irr) < Decimal("1e-12")
    assert len(result.scenarios) == 3 and len(result.cash_flows) == 10
    assert all(case.required_entry_price is not None for case in result.scenarios)
    # Probability-weight the cash-flow stream, not scenario IRRs.
    weighted_price = sum(
        (
            case.probability * case.required_entry_price
            for case in result.scenarios
            if case.required_entry_price is not None
        ),
        Decimal(0),
    )
    assert abs(weighted_price - result.weighted_entry_price) < Decimal("1e-17")
    assert result.contributions is not None
    parts = result.contributions
    assert abs(
        parts.annual_cash_flow_pv_per_share
        + parts.terminal_pv_per_share
        + parts.opening_balance_sheet_per_share
        - result.weighted_entry_price
    ) < Decimal("1e-17")


def test_dcf_independent_annuity_price_and_target_do_not_change_terminal_assumptions() -> None:
    value = inputs_for(UFCF_ENTERPRISE_IRR).model_dump()
    value["base"].update(
        base_revenue=Decimal(100), diluted_shares=Decimal(10), net_cash_debt=Decimal(20)
    )
    for case in value["scenarios"]:
        case.update(terminal_growth=Decimal(0), year10_ufcf_growth=Decimal(0))
        for year in case["years"]:
            year.update(
                revenue_growth=Decimal(0),
                ebit_margin=Decimal("0.1"),
                tax_rate=Decimal(0),
                da_to_revenue=Decimal(0),
                capex_to_revenue=Decimal(0),
                nwc_to_revenue=Decimal(0),
                discount_rate=Decimal("0.1"),
            )
    value["base"]["base_nwc_to_revenue"] = Decimal(0)
    inputs = s.DcfCalculationInput.model_validate(value)
    first = calculate_return_hurdle(
        inputs, currency="USD", method=UFCF_ENTERPRISE_IRR, required_return=Decimal("0.1")
    )
    second = calculate_return_hurdle(
        inputs, currency="USD", method=UFCF_ENTERPRISE_IRR, required_return=Decimal("0.2")
    )
    assert (
        first.weighted_entry_price == 12
    )  # Ten unit cash flows + ten terminal, PV=10; cash bridge=2.
    with localcontext() as context:
        context.prec = 60
        expected = (1 - Decimal("1.2") ** -10) / Decimal("0.2") + 10 / Decimal("1.2") ** 10 + 2
        assert second.weighted_entry_price is not None
        assert abs(second.weighted_entry_price - expected) < Decimal("1e-18")
    assert first.cash_flows == second.cash_flows
    assert first.accepted_hurdle == second.accepted_hurdle == Decimal("0.1")


def test_distinct_native_terminal_and_balance_sheet_conventions() -> None:
    results = {
        method: calculate_return_hurdle(
            inputs_for(method), currency="USD", method=method, required_return=Decimal("0.1")
        )
        for method in METHODS
    }
    # Independent fixed references calculated from each documented per-method stream.
    expected = {
        UFCF_ENTERPRISE_IRR: "6.513083145797072869",
        UFCF_ENTERPRISE_HMODEL_IRR: "6.425740305820888036",
        OWNER_CASH_FLOW_EQUITY_IRR: "24.901310672525370321",
        RESIDUAL_INCOME_EQUITY_IRR: "30.071940952810943302",
    }
    for method, price in expected.items():
        assert results[method].weighted_entry_price == Decimal(price)
    assert (
        results[UFCF_ENTERPRISE_IRR].cash_flows[-1].terminal_cash_flow_per_share
        > results[UFCF_ENTERPRISE_HMODEL_IRR].cash_flows[-1].terminal_cash_flow_per_share
    )
    for method in [OWNER_CASH_FLOW_EQUITY_IRR, RESIDUAL_INCOME_EQUITY_IRR]:
        contributions = results[method].contributions
        assert contributions is not None
        assert contributions.opening_balance_sheet_per_share == 0
    owner = inputs_for(OWNER_CASH_FLOW_EQUITY_IRR)
    assert isinstance(owner, s.OwnerCashFlowInput)
    without_cash = owner.model_copy(
        update={"base": owner.base.model_copy(update={"net_cash": Decimal(0)})}
    )
    no_cash = calculate_return_hurdle(
        without_cash,
        currency="USD",
        method=OWNER_CASH_FLOW_EQUITY_IRR,
        required_return=Decimal("0.1"),
    )
    assert no_cash.weighted_entry_price is not None
    owner_price = results[OWNER_CASH_FLOW_EQUITY_IRR].weighted_entry_price
    assert owner_price is not None
    with localcontext() as context:
        context.prec = 60
        assert abs(
            owner_price
            - no_cash.weighted_entry_price
            - owner.base.net_cash / owner.base.diluted_shares / Decimal("1.1") ** 10
        ) < Decimal("1e-17")


def test_conventional_negative_early_cash_flows_and_unavailable_cases() -> None:
    with localcontext() as context:
        context.prec = 60
        conventional = ReturnStream((Decimal(-1), *([Decimal(2)] * 9)), Decimal(10), Decimal(0))
        assert _entry_price(conventional, Decimal("0.1"))[0] is not None
        mixed = ReturnStream(
            (Decimal(2), Decimal(-1), *([Decimal(2)] * 8)), Decimal(10), Decimal(0)
        )
        assert _entry_price(mixed, Decimal("0.1"))[0] is None
        debt = ReturnStream(tuple([Decimal(1)] * 10), Decimal(10), Decimal(-100))
        assert _entry_price(debt, Decimal("0.1"))[0] is None
        tiny = ReturnStream(tuple([Decimal("1e-25")] * 10), Decimal("1e-25"), Decimal(0))
        assert _entry_price(tiny, Decimal("0.1"))[0] is None


@pytest.mark.parametrize("target", ["-0.01", "1", "NaN", "Infinity", 0.1, True])
def test_target_requires_bounded_exact_decimals(target: object) -> None:
    with pytest.raises(ValidationError):
        s.ReturnHurdleRequest.model_validate(
            {"base_revision_id": str(uuid4()), "required_return": target}
        )


@pytest.mark.parametrize("price", ["0", "-1", "NaN", 20.5, True])
def test_hypothetical_entry_requires_positive_exact_decimal(price: object) -> None:
    with pytest.raises(ValidationError):
        s.ReturnHurdleRequest.model_validate(
            {"base_revision_id": str(uuid4()), "required_return": "0.1", "entry_price": price}
        )


def seed_model(
    db: Session, method: str, *, effective: datetime | None = None
) -> tuple[UUID, UUID, UUID]:
    company = ops.create_company(db, s.CompanyCreate(name="Fictional return-hurdle issuer"))
    security = ops.create_security(
        db, company.id, s.SecurityCreate(name="Ordinary", security_type="COMMON_STOCK")
    )
    listing = ops.create_listing(
        db, security.id, s.ListingCreate(venue="SYNTHETIC", ticker="HURDLE", currency="USD")
    )
    revision = {
        **inputs_for(method).model_dump(),
        "base_revision_id": None,
        "actor": "IMPORT",
        "source": "fictional return-hurdle fixture",
        "rationale": "Synthetic immutable test",
        "effective_at": effective or datetime(2026, 1, 1, tzinfo=UTC),
    }
    common = {
        "model_name": "Fictional model",
        "valuation_listing_id": listing.id,
        "model_currency": "USD",
        "initial_revision": revision,
    }
    if method in {UFCF_ENTERPRISE_IRR, UFCF_ENTERPRISE_HMODEL_IRR}:
        model = ops.create_financial_model(
            db,
            company.id,
            s.FinancialModelCreate.model_validate(common),
            return_methodology_code=method,
        )
    elif method == OWNER_CASH_FLOW_EQUITY_IRR:
        model = ops.create_owner_cash_flow_model(
            db, company.id, s.OwnerCashFlowModelCreate.model_validate(common)
        )
    else:
        model = ops.create_residual_income_model(
            db, company.id, s.ResidualIncomeModelCreate.model_validate(common)
        )
    assert model.current_revision_id is not None
    return model.id, model.current_revision_id, listing.id


@pytest.mark.integration
@pytest.mark.parametrize("method", METHODS)
def test_api_is_read_only_revision_bound_and_returns_usable_result_without_prices(
    postgres_engine: Engine, method: str
) -> None:
    with Session(postgres_engine) as db, db.begin():
        model_id, revision_id, listing_id = seed_model(db, method)
        read_model = q.financial_model if method in METHODS[:2] else q.extended_financial_model
        before = read_model(db, model_id).model_dump()
    app = create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
    read_only = postgres_engine.execution_options(postgresql_readonly=True)
    with read_only.connect() as connection:
        assert connection.scalar(text("SHOW transaction_read_only")) == "on"
    with (
        patch("portfolio_api.main.create_database_engine", return_value=read_only),
        TestClient(app) as client,
    ):
        path = f"/v1/financial-models/{model_id}/return-hurdle"
        params = {
            "base_revision_id": str(revision_id),
            "required_return": "0.1",
            "entry_price": "20",
        }
        response = client.get(path, params=params)
        assert response.status_code == 200, response.text
        result = s.ReturnHurdleRead.model_validate(response.json())
        assert result.status == "AVAILABLE"
        assert result.return_methodology.code == method
        assert result.valuation_listing_id == listing_id
        assert (
            result.current_price
            is result.current_expected_irr
            is result.current_price_gap_to_required
            is None
        )
        assert result.market_price.status == "NO_DATA"
        assert result.hypothetical_status == "AVAILABLE"
        assert client.get(path).status_code == 422
        assert client.get(path, params={**params, "required_return": "1"}).status_code == 422
        assert (
            client.get(path, params={**params, "base_revision_id": str(uuid4())}).status_code == 409
        )
        assert (
            client.get(path.replace(str(model_id), str(uuid4())), params=params).status_code == 404
        )
        with Session(postgres_engine) as db:
            assert read_model(db, model_id).model_dump() == before


@pytest.mark.parametrize("future_field", ["effective_at", "recorded_at"])
def test_future_revision_cannot_supply_current_analysis(future_field: str) -> None:
    now = datetime.now(UTC)
    model_id, revision_id = uuid4(), uuid4()
    model = FinancialModel(
        id=model_id,
        current_revision_id=revision_id,
        model_type="UFCF_DCF_10Y_FADE",
        created_at=now - timedelta(days=1),
    )
    revision = FinancialModelRevision(
        id=revision_id,
        model_id=model_id,
        model_type=model.model_type,
        effective_at=now - timedelta(days=1),
        recorded_at=now - timedelta(days=1),
    )
    setattr(revision, future_field, now + timedelta(days=1))
    session = Mock(spec=Session)
    session.get.side_effect = [model, revision]
    with pytest.raises(ops.DomainError, match="not yet effective and known"):
        model_return_hurdle(
            session,
            model_id,
            s.ReturnHurdleRequest(base_revision_id=revision_id, required_return=Decimal("0.1")),
        )
    session.scalar.assert_not_called()


@pytest.mark.integration
@pytest.mark.parametrize(
    "currency,days_old,future_close,expected",
    [
        ("USD", 0, False, "AVAILABLE"),
        ("USD", 20, False, "STALE"),
        ("EUR", 0, False, "DATA_CHECK"),
        ("USD", 0, True, "BLOCKED_TIME"),
        ("USD", -1, False, "NO_DATA"),
    ],
)
def test_only_valid_fresh_exact_quote_supplies_market_comparison(
    postgres_engine: Engine, currency: str, days_old: int, future_close: bool, expected: str
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as db, db.begin():
        model_id, revision_id, listing_id = seed_model(db, UFCF_ENTERPRISE_IRR)
        observed = now - timedelta(days=days_old)
        db.add(
            PriceObservation(
                listing_id=listing_id,
                batch_id=None,
                price_kind="DAILY_CLOSE",
                market_date=(
                    now + timedelta(minutes=1)
                    if future_close
                    else observed.replace(hour=0, minute=0, second=0, microsecond=0)
                ),
                observed_at=observed,
                recorded_at=observed,
                provider_close=Decimal(20),
                split_adjusted_close=Decimal(20),
                total_return_close=None,
                volume=None,
                currency=currency,
                provider_currency=currency,
                source_price_multiplier=Decimal(1),
                provider="YAHOO_FINANCE",
                provider_symbol="SYNTH",
                adjustment_basis="split-adjusted-close",
                data_quality="PASS",
                source_ref="fictional:quote",
                supersedes_observation_id=None,
            )
        )
    app = create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
    with (
        patch(
            "portfolio_api.main.create_database_engine",
            return_value=postgres_engine.execution_options(postgresql_readonly=True),
        ),
        TestClient(app) as client,
    ):
        response = client.get(
            f"/v1/financial-models/{model_id}/return-hurdle",
            params={"base_revision_id": str(revision_id), "required_return": "0.1"},
        )
        assert response.status_code == 200, response.text
        result = s.ReturnHurdleRead.model_validate(response.json())
        if future_close:
            assert result.market_price.status in {"DATA_CHECK", "NO_DATA"}
        else:
            assert result.market_price.status == expected
        assert result.weighted_entry_price is not None
        if expected == "AVAILABLE":
            assert result.current_price == 20
            assert result.current_expected_irr is not None
            assert result.current_price_gap_to_required is not None
        else:
            assert (
                result.current_price
                is result.current_expected_irr
                is result.current_price_gap_to_required
                is None
            )


def test_unknown_method_or_version_never_inherits_a_supported_return_definition() -> None:
    with pytest.raises(ValueError, match="Unsupported DCF return method"):
        calculate_return_hurdle(
            inputs_for(UFCF_ENTERPRISE_IRR),
            currency="USD",
            method=OWNER_CASH_FLOW_EQUITY_IRR,
            required_return=Decimal("0.1"),
        )
    now = datetime.now(UTC) - timedelta(days=1)
    model_id, revision_id = uuid4(), uuid4()
    model = FinancialModel(
        id=model_id, current_revision_id=revision_id, model_type="UFCF_DCF_10Y_FADE", created_at=now
    )
    revision = FinancialModelRevision(
        id=revision_id,
        model_id=model_id,
        model_type=model.model_type,
        effective_at=now,
        recorded_at=now,
    )
    session = Mock(spec=Session)
    session.get.side_effect = [model, revision]
    session.scalar.return_value = SimpleNamespace(return_methodology=SimpleNamespace(version=2))
    with pytest.raises(ops.DomainError, match="supported accepted return methodology"):
        model_return_hurdle(
            session,
            model_id,
            s.ReturnHurdleRequest(base_revision_id=revision_id, required_return=Decimal("0.1")),
        )
