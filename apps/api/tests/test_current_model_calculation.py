"""Current quote calculations never mutate accepted model state."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import pytest
from synthetic_financial_fixtures import dcf_fixture

from portfolio_api.current_model_calculation import (
    NativeCurrentCalculation,
    calculate_native_revision_at_quote,
)
from portfolio_api.domain.schemas import (
    DcfCalculationInput,
    ExpectedReturnMarketPriceRead,
    FinancialModelRevisionCreate,
    ReturnMethodologyRead,
)
from portfolio_api.financial_models import MarketPriceInput
from portfolio_api.return_semantics import DEFINITIONS, UFCF_ENTERPRISE_IRR


def accepted_inputs() -> tuple[dict[str, object], DcfCalculationInput]:
    fixture = dcf_fixture()
    revision = FinancialModelRevisionCreate.model_validate(fixture["input"])
    return fixture, DcfCalculationInput(base=revision.base, scenarios=revision.scenarios)


def methodology() -> ReturnMethodologyRead:
    definition = next(item for item in DEFINITIONS if item.code == UFCF_ENTERPRISE_IRR)
    return ReturnMethodologyRead(
        id=uuid4(),
        **definition.__dict__,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def quote_read(
    listing_id: UUID,
    observation_id: UUID,
    price: Decimal,
    *,
    status: Literal["AVAILABLE", "STALE"] = "AVAILABLE",
) -> ExpectedReturnMarketPriceRead:
    effective = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
    return ExpectedReturnMarketPriceRead(
        status=status,
        listing_id=listing_id,
        ticker="SYNTH",
        venue="NASDAQ",
        listing_currency="USD",
        quote=price,
        quote_currency="USD",
        model_reference_price=price,
        model_currency="USD",
        effective_at=effective,
        observed_at=effective,
        recorded_at=effective,
        provider="YAHOO_FINANCE",
        adjustment_basis="split-adjusted-close",
        observation_id=observation_id,
        source_ref="fixture:current-price",
        reason=None,
    )


def recalculate(
    *,
    inputs: DcfCalculationInput,
    listing_id: UUID,
    price: Decimal,
    freshness: Literal["FRESH", "STALE", "QUALITY_CHECK", "NO_DATA"] = "FRESH",
    currency: str = "USD",
    quote_listing_id: UUID | None = None,
) -> NativeCurrentCalculation:
    observation_id = uuid4()
    return calculate_native_revision_at_quote(
        model_type="UFCF_DCF_10Y_FADE",
        model_currency="USD",
        valuation_listing_id=listing_id,
        quote_listing_id=quote_listing_id or listing_id,
        revision_inputs=inputs,
        return_methodology=methodology(),
        forward_fundamental_cagr=Decimal("0.08"),
        accepted_output_id=uuid4(),
        accepted_reference_price=Decimal("343.5"),
        accepted_reference_price_observation_id=uuid4(),
        accepted_reference_price_effective_at=datetime(2026, 10, 8, tzinfo=UTC),
        market_price=MarketPriceInput(
            observation_id,
            price,
            currency,
            datetime(2026, 10, 9, 20, 0, tzinfo=UTC),
            freshness,
        ),
        market_price_read=quote_read(listing_id, observation_id, price),
        model_id=uuid4(),
        model_name="Synthetic issuer UFCF DCF",
        revision_id=uuid4(),
        revision_number=1,
        methodology_version="ufcf-dcf-v1",
        effective_at=datetime(2026, 10, 8, tzinfo=UTC),
        recorded_at=datetime(2026, 10, 8, tzinfo=UTC),
        calculated_as_of=datetime(2026, 10, 9, 23, 59, tzinfo=UTC),
        known_at=datetime(2026, 10, 9, 23, 59, tzinfo=UTC),
    )


def test_quote_changes_recalculate_returns_without_changing_accepted_reference_or_inputs() -> None:
    _, inputs = accepted_inputs()
    accepted_dump = inputs.model_dump(mode="json")
    listing_id = uuid4()
    at_acceptance = recalculate(inputs=inputs, listing_id=listing_id, price=Decimal("343.5"))
    at_current_quote = recalculate(inputs=inputs, listing_id=listing_id, price=Decimal("400"))

    assert at_acceptance.outputs.expected_cash_flow_irr is not None
    assert at_current_quote.outputs.expected_cash_flow_irr is not None
    assert (
        at_acceptance.outputs.expected_cash_flow_irr
        != at_current_quote.outputs.expected_cash_flow_irr
    )
    assert at_current_quote.outputs.current_price == Decimal("400")
    assert at_current_quote.read.accepted_reference_price == Decimal("343.5")
    assert at_current_quote.read.accepted_reference_price_effective_at == datetime(
        2026, 10, 8, tzinfo=UTC
    )
    assert at_current_quote.read.accepted_output_id != at_current_quote.read.revision_id
    assert inputs.model_dump(mode="json") == accepted_dump


def test_stale_or_currency_incompatible_exact_listing_quote_keeps_return_unavailable() -> None:
    _, inputs = accepted_inputs()
    listing_id = uuid4()
    stale = recalculate(
        inputs=inputs,
        listing_id=listing_id,
        price=Decimal("400"),
        freshness="STALE",
    )
    mismatched = recalculate(
        inputs=inputs,
        listing_id=listing_id,
        price=Decimal("400"),
        currency="EUR",
    )

    assert stale.outputs.weighted_fv > 0
    assert stale.outputs.price_status == "STALE"
    assert stale.outputs.expected_cash_flow_irr is None
    assert stale.outputs.expected_excess is None
    assert mismatched.outputs.price_status == "CURRENCY_MISMATCH"
    assert mismatched.outputs.expected_cash_flow_irr is None


def test_a_different_listing_cannot_supply_a_current_model_quote() -> None:
    _, inputs = accepted_inputs()
    with pytest.raises(ValueError, match="exact valuation listing"):
        recalculate(
            inputs=inputs,
            listing_id=uuid4(),
            quote_listing_id=uuid4(),
            price=Decimal("400"),
        )
