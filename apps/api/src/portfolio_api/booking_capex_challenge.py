"""Prepare Booking's cited one-input proposal from a canonical financial-model export."""

import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from portfolio_api.domain import schemas as s
from portfolio_api.model_revision_proposals import _inputs_read

MODEL_ID = UUID("94c15805-ee3a-48a2-9305-4a2d9fc466ed")
REVISION_ID = UUID("a1ec141d-01d7-4900-950d-fc92e2dbf31c")
SOURCE = "https://www.bookingholdings.com/wp-content/uploads/2026/11/Q3-26-BKNG-Earnings-Release-Final.pdf"
PRIOR = "https://www.bookingholdings.com/wp-content/uploads/2026/02/Q4-25-BKNG-Earnings-Release.pdf"


def challenged_inputs(inputs: s.DcfCalculationInput) -> s.DcfCalculationInput:
    proposed = inputs.model_copy(deep=True)
    (year,) = (
        year
        for scenario in proposed.scenarios
        if scenario.scenario == "BASE"
        for year in scenario.years
        if year.forecast_year == 1
    )
    if year.capex_to_revenue != Decimal("0.015"):
        raise ValueError("The accepted base Year 1 capex ratio must be 1.50%.")
    year.capex_to_revenue = Decimal("0.012")
    return proposed


def prepare(
    model: s.FinancialModelRead, evidence_id: UUID, authored_at: datetime
) -> s.FinancialModelRevisionProposalV1:
    revision = model.current_revision
    if (model.id, model.current_revision_id, revision.id, revision.revision_number) != (
        MODEL_ID,
        REVISION_ID,
        REVISION_ID,
        1,
    ):
        raise ValueError("Expected Booking's accepted P-BKNG revision 1.")
    inputs = _inputs_read(model)
    assert isinstance(inputs, s.DcfCalculationInput)
    return s.FinancialModelRevisionProposalV1.model_validate(
        {
            "contract_type": "FinancialModelRevisionProposalV1",
            "contract_version": "1.0.0",
            "external_revision_id": "bkng-r1-q3-2026-base-y1-capex-v1",
            "model_id": model.id,
            "company_id": model.company_id,
            "valuation_listing_id": model.valuation_listing.id,
            "model_currency": model.model_currency,
            "base_revision_id": revision.id,
            "base_revision_number": revision.revision_number,
            "methodology_version": revision.methodology_version,
            "authored_at": authored_at,
            "effective_at": authored_at,
            "source_reference": SOURCE,
            "rationale": (
                "Reduce base Year 1 capex/revenue from 1.50% to 1.20%. FY2025 additions "
                "were $322m on $26.9bn revenue (1.20%). Nine months through September 2026 "
                "were $251m on $21.777bn (1.15%). Retain 1.50% if expected investment "
                "accelerates. Keep revenue growth under review: quarterly GAAP revenue "
                "included a $900m FTC adjustment. Annual model growth requires a comparable period."
            ),
            "supporting_evidence": [
                {
                    "evidence_type": "RESEARCH_REVISION",
                    "relationship": "SUPPORTS",
                    "reference_id": evidence_id,
                    "note": f"FY2025 comparator: {PRIOR}",
                }
            ],
            "method": {"methodology": model.model_type, "inputs": challenged_inputs(inputs)},
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_export", type=Path)
    parser.add_argument("--research-revision-id", required=True, type=UUID)
    parser.add_argument("--authored-at", required=True, type=datetime.fromisoformat)
    args = parser.parse_args()
    model = s.FinancialModelRead.model_validate_json(args.model_export.read_bytes())
    print(prepare(model, args.research_revision_id, args.authored_at).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
