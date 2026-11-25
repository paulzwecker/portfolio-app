"""Prepare an earnings research packet from an agent assessment and an accepted model export."""

import argparse
import hashlib
import json
from pathlib import Path

from portfolio_api.domain import schemas as s


def prepare(
    model: s.FinancialModelRead, payload: dict[str, object]
) -> s.ResearchRevisionPublishContract:
    packet = s.ResearchRevisionPublishContract.model_validate(payload)
    review = packet.earnings_review
    if review is None or (
        model.company_id,
        model.valuation_listing.id,
        model.current_revision_id,
    ) != (packet.company_id, review.listing_id, review.base_revision_id):
        raise ValueError("The publication must reference this listing and its accepted revision.")
    (year,) = (
        year
        for scenario in model.current_revision.scenarios
        if scenario.scenario == "BASE"
        for year in scenario.years
        if year.forecast_year == 1
    )
    if getattr(year, review.driver) != review.accepted_base_year_one:
        raise ValueError("Reviewed assumption differs from the exported model.")
    return packet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_export", type=Path)
    parser.add_argument("assessment", type=Path)
    args = parser.parse_args()
    model = s.FinancialModelRead.model_validate_json(args.model_export.read_bytes())
    data = json.loads(args.assessment.read_bytes())
    listing = model.valuation_listing
    if data.pop("listing").upper() != f"{listing.venue}:{listing.ticker}".upper() or (
        data.pop("revision_number") != model.current_revision.revision_number
    ):
        raise ValueError("Assessment targets another listing or model revision.")
    data.update(company_id=str(model.company_id), security_id=str(listing.security_id))
    review = data["earnings_review"]
    review.update(listing_id=str(listing.id), base_revision_id=str(model.current_revision_id))
    source = hashlib.sha256(data["source_reference"].encode()).hexdigest()[:24]
    data["stream_key"] = f"earnings/{review['listing_id']}/{source}/{review['driver']}"
    data.setdefault("external_revision_id", str(review["base_revision_id"]))
    print(prepare(model, data).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
