"""Cross-feature native-price valuation and accepted-model authority boundaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_native_market_valuation import native_price
from test_return_hurdle import METHODS, seed_model

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain import services as ops
from portfolio_api.domain.models import FxObservation
from portfolio_api.main import create_app
from portfolio_api.settings import Settings


@pytest.mark.integration
@pytest.mark.parametrize("method", METHODS)
def test_native_portfolio_value_never_becomes_an_observed_model_return(
    postgres_engine: Engine, method: str
) -> None:
    """One exact native quote values holdings but leaves model quote eligibility unchanged."""
    observed = datetime.now(UTC) - timedelta(minutes=1)
    market_date = (observed - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(postgres_engine) as db, db.begin():
        model_id, revision_id, listing_id = seed_model(db, method)
        portfolio = ops.create_portfolio(
            db, s.PortfolioCreate(name="Fictional cross-feature portfolio", base_currency="EUR")
        )
        portfolio_id = portfolio.id
        snapshot = ops.record_holdings(
            db,
            portfolio_id,
            s.SnapshotCreate(
                effective_at=market_date,
                actor="IMPORT",
                reason="Synthetic integration only",
                source="fictional:integrated-financial-boundaries",
                completeness="COMPLETE",
                positions=[s.PositionInput(listing_id=listing_id, quantity=Decimal("2.5"))],
            ),
        )
        db.add(
            native_price(
                listing_id=listing_id,
                market_date=market_date,
                observed_at=observed,
                recorded_at=observed,
                provider_close=Decimal("50"),
                source_price_multiplier=Decimal(1),
                currency="USD",
                provider_currency="USD",
                # Deliberately present, but neither a native mark nor a model quote.
                total_return_close=Decimal("42"),
            )
        )
        db.add(
            FxObservation(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.9"),
                effective_at=market_date,
                observed_at=observed,
                recorded_at=observed,
                provider="SYNTHETIC_FX",
                source="fictional:integrated-financial-boundaries",
                actor="IMPORT",
                reason="Synthetic FX conversion only",
            )
        )
        db.flush()
        read_model = q.financial_model if method in METHODS[:2] else q.extended_financial_model
        accepted_before = read_model(db, model_id).model_dump()
        holdings_before = q.snapshot_read(db, snapshot).model_dump()
        snapshot_id = snapshot.id

    read_only = postgres_engine.execution_options(postgresql_readonly=True)
    with read_only.connect() as connection:
        assert connection.scalar(text("SHOW transaction_read_only")) == "on"
    app = create_app(Settings(_env_file=None, database_url=None, api_access_token=None))
    with (
        patch("portfolio_api.main.create_database_engine", return_value=read_only),
        TestClient(app) as client,
    ):
        response = client.get(f"/v1/portfolios/{portfolio_id}/overview")
        assert response.status_code == 200, response.text
        overview = s.PortfolioOverview.model_validate(response.json())
        position = overview.companies[0].positions[0]
        assert position.listing_id == listing_id
        assert position.valuation_price_basis == "UNADJUSTED_NATIVE_CLOSE"
        assert position.latest_price == Decimal("50")
        assert position.native_market_value == Decimal("125")
        assert position.base_market_value == overview.base_market_value == Decimal("112.5")

        response = client.get(
            f"/v1/financial-models/{model_id}/return-hurdle",
            params={
                "base_revision_id": str(revision_id),
                "required_return": "0.1",
                "entry_price": "50",
            },
        )
        assert response.status_code == 200, response.text
        result = s.ReturnHurdleRead.model_validate(response.json())
        assert result.status == "AVAILABLE" and result.weighted_entry_price is not None
        assert result.market_price.adjustment_basis == "UNADJUSTED_NATIVE_CLOSE"
        assert result.market_price.quote == Decimal("50")
        assert result.market_price.model_reference_price is None
        assert result.market_price.status == "DATA_CHECK"
        assert (
            result.current_price
            is result.current_expected_irr
            is result.current_price_gap_to_required
            is None
        )
        assert result.hypothetical_entry_price == Decimal("50")
        assert result.hypothetical_status == "AVAILABLE"
        assert result.hypothetical_expected_irr is not None

    with Session(postgres_engine) as db:
        assert read_model(db, model_id).model_dump() == accepted_before
        after = q.overview(db, portfolio_id)
        assert after.snapshot is not None and after.snapshot.id == snapshot_id
        assert after.snapshot.model_dump() == holdings_before
