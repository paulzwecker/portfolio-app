"""Bounded, transient fair-value sensitivity for an exact accepted DCF revision."""

from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from portfolio_api.current_model_calculation import dcf_inputs_for_revision
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import FinancialModel, FinancialModelRevision, FinancialModelType
from portfolio_api.domain.services import DomainError
from portfolio_api.financial_models import MarketPriceInput, calculate_ufcf_dcf

DISCOUNT_RATE_SHIFTS = (Decimal("-0.01"), Decimal(0), Decimal("0.01"))
TERMINAL_GROWTH_SHIFTS = (Decimal("-0.005"), Decimal(0), Decimal("0.005"))


def calculate_dcf_sensitivity(
    inputs: s.DcfCalculationInput, *, model_currency: str
) -> list[s.DcfSensitivityCellRead]:
    """Shift each scenario's annual discount rates and terminal growth in parallel.

    Probabilities, operating inputs and the explicit or faded UFCF tail stay fixed.
    Each of the nine cells reuses the native engine and its validated input contract.
    """
    cells = []
    with localcontext() as context:
        context.prec = 60
        for discount_shift in DISCOUNT_RATE_SHIFTS:
            for growth_shift in TERMINAL_GROWTH_SHIFTS:
                shifted = inputs.model_dump(mode="python")
                for scenario in shifted["scenarios"]:
                    scenario["terminal_growth"] += growth_shift
                    for year in scenario["years"]:
                        year["discount_rate"] += discount_shift
                try:
                    candidate = s.DcfCalculationInput.model_validate(shifted)
                except ValidationError:
                    cells.append(
                        s.DcfSensitivityCellRead(
                            discount_rate_shift=discount_shift,
                            terminal_growth_shift=growth_shift,
                            status="INVALID_ASSUMPTIONS",
                            unavailable_reason=(
                                "Shifted rates exceed the supported input bounds or terminal "
                                "growth reaches a scenario's year-five discount rate."
                            ),
                            bear_fv=None,
                            base_fv=None,
                            bull_fv=None,
                            weighted_fv=None,
                        )
                    )
                    continue
                calculation = calculate_ufcf_dcf(
                    candidate,
                    model_currency=model_currency,
                    market_price=MarketPriceInput(None, None, None, None, "NO_DATA"),
                )
                values = {
                    name: getattr(calculation, name).quantize(
                        Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP
                    )
                    for name in ("bear_fv", "base_fv", "bull_fv", "weighted_fv")
                }
                cells.append(
                    s.DcfSensitivityCellRead(
                        discount_rate_shift=discount_shift,
                        terminal_growth_shift=growth_shift,
                        status="AVAILABLE",
                        unavailable_reason=None,
                        **values,
                    )
                )
    return cells


def model_dcf_sensitivity(
    session: Session, model_id: UUID, base_revision_id: UUID
) -> s.DcfSensitivityRead:
    model = session.get(FinancialModel, model_id)
    if model is None or model.model_type != FinancialModelType.UFCF_DCF_10Y_FADE:
        raise DomainError("UFCF DCF model not found", 404)
    if model.current_revision_id != base_revision_id:
        raise DomainError("The model changed since it was read; reload before sensitivity", 409)
    revision = session.get(FinancialModelRevision, base_revision_id)
    if revision is None or revision.model_id != model.id:
        raise DomainError("Current model revision is inconsistent", 409)
    inputs = dcf_inputs_for_revision(session, revision)
    return s.DcfSensitivityRead(
        calculation_version="ufcf-dcf-sensitivity-v1",
        model_id=model.id,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        methodology_version=revision.methodology_version,
        model_currency=model.model_currency,
        discount_rate_shifts=list(DISCOUNT_RATE_SHIFTS),
        terminal_growth_shifts=list(TERMINAL_GROWTH_SHIFTS),
        scenarios=[
            s.DcfSensitivityScenarioRead(
                scenario=item.scenario,
                probability=item.probability,
                year5_discount_rate=next(
                    year.discount_rate for year in item.years if year.forecast_year == 5
                ),
                terminal_growth=item.terminal_growth,
            )
            for item in inputs.scenarios
        ],
        cells=calculate_dcf_sensitivity(inputs, model_currency=model.model_currency),
    )
