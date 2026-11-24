from decimal import Decimal

import pytest
from synthetic_financial_fixtures import dcf_fixture

from portfolio_api.booking_capex_challenge import challenged_inputs
from portfolio_api.domain.schemas import DcfCalculationInput
from portfolio_api.domain.services import _additional_input_changes


def test_changes_only_the_reviewed_input_and_refuses_another_baseline() -> None:
    data = dcf_fixture()["input"]
    data["scenarios"][1]["years"][0]["capex_to_revenue"] = "0.015"
    inputs = DcfCalculationInput(base=data["base"], scenarios=data["scenarios"])
    proposed = challenged_inputs(inputs)
    changes = _additional_input_changes(
        inputs.model_dump(mode="json"), proposed.model_dump(mode="json")
    )
    assert len(changes) == 1
    assert changes[0].path == "scenarios[1].years[0].capex_to_revenue"
    assert proposed.scenarios[1].years[0].capex_to_revenue == Decimal("0.012")
    with pytest.raises(ValueError, match="1.50%"):
        challenged_inputs(proposed)
