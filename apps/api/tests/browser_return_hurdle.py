"""Fictional accepted models for a strictly read-only investor browser journey."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import (
    dcf_fixture,
    owner_cash_flow_fixture,
    residual_income_fixture,
)

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops


def prepare_return_hurdle(engine: Engine, metadata: dict[str, object], scenario: str) -> None:
    company_id = UUID(str(metadata["company_id"]))
    listing_id = UUID(str(metadata["stock_listing_id"]))
    common = {
        "base_revision_id": None,
        "actor": "IMPORT",
        "source": "Fictional return-hurdle browser fixture",
        "rationale": "Representative test assumptions, never live investment data.",
        "effective_at": datetime.now(UTC) - timedelta(days=1),
    }
    with Session(engine) as session, session.begin():
        dcf = ops.create_financial_model(
            session,
            company_id,
            s.FinancialModelCreate(
                model_name="Fictional operating DCF",
                valuation_listing_id=listing_id,
                model_currency="USD",
                initial_revision=s.FinancialModelRevisionCreate.model_validate(
                    {**dcf_fixture()["input"], **common}
                ),
            ),
        )
        owner = ops.create_owner_cash_flow_model(
            session,
            company_id,
            s.OwnerCashFlowModelCreate(
                model_name="Fictional owner cash flow",
                valuation_listing_id=listing_id,
                model_currency="USD",
                initial_revision=s.OwnerCashFlowRevisionCreate.model_validate(
                    {**owner_cash_flow_fixture()["input"], **common}
                ),
            ),
        )
        residual = ops.create_residual_income_model(
            session,
            company_id,
            s.ResidualIncomeModelCreate(
                model_name="Fictional residual income",
                valuation_listing_id=listing_id,
                model_currency="USD",
                initial_revision=s.ResidualIncomeRevisionCreate.model_validate(
                    {**residual_income_fixture()["input"], **common}
                ),
            ),
        )
        metadata.update(
            scenario=scenario,
            dcf_model_id=str(dcf.id),
            dcf_revision_id=str(dcf.current_revision_id),
            owner_model_id=str(owner.id),
            owner_revision_id=str(owner.current_revision_id),
            residual_model_id=str(residual.id),
            residual_revision_id=str(residual.current_revision_id),
            model_fixture="fictional-accepted-models-v1",
        )
