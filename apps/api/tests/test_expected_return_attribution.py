import copy
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import PriceObservation
from portfolio_api.expected_return_attribution import (
    company_expected_return_attribution,
    symmetric_shapley_decomposition,
)
from portfolio_api.main import create_app
from portfolio_api.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "p_googl_ufcf_dcf_v1.json"


def _attribution_point(
    point_id: str, effective_at: datetime, expected_irr: Decimal | None
) -> s.ExpectedReturnHistoryPointRead:
    return s.ExpectedReturnHistoryPointRead(
        point_id=point_id,
        source_kind="NATIVE_MODEL_REVISION",
        event_status="DATED",
        effective_at=effective_at,
        recorded_at=effective_at,
        series_id="native:test-model",
        model_key="P-ATTR",
        model_id=uuid4(),
        revision_id=uuid4(),
        revision_number=1,
        model_type="UFCF_DCF_10Y_FADE",
        methodology_version="fixture-v1",
        model_label="Attribution fixture",
        model_currency="USD",
        currency_status="DOCUMENTED",
        valuation_listing_id=None,
        valuation_ticker=None,
        valuation_venue=None,
        valuation_listing_currency=None,
        is_current_at_cutoff=True,
        output_status="COMPLETE",
        output_quality="COMPLETE",
        contract_status=None,
        return_semantics="NATIVE_METHOD_OUTPUT",
        actor="LOCAL_USER",
        source_actor=None,
        revision_source=None,
        revision_type=None,
        bear_fv=Decimal("70"),
        base_fv=Decimal("100"),
        bull_fv=Decimal("140"),
        bear_probability=Decimal("0.2"),
        base_probability=Decimal("0.6"),
        bull_probability=Decimal("0.2"),
        weighted_fv=Decimal("100"),
        weighted_upside=None,
        expected_cash_flow_irr=expected_irr,
        hurdle=Decimal("0.09"),
        expected_excess=None,
        forward_fundamental_cagr=None,
        market_price=s.ExpectedReturnMarketPriceRead(
            status="NO_DATA",
            listing_id=None,
            ticker=None,
            venue=None,
            listing_currency=None,
            quote=None,
            quote_currency=None,
            model_reference_price=None,
            model_currency="USD",
            effective_at=None,
            observed_at=None,
            recorded_at=None,
            provider=None,
            adjustment_basis=None,
            observation_id=None,
            source_ref=None,
            reason="No price captured.",
        ),
        estimate_context=s.ExpectedReturnEstimateContextRead(
            status="NO_OBSERVATIONS", provider_id=None, periods=[]
        ),
        source="fixture",
        source_revision_id=None,
        rationale="Fixture history point.",
        evidence=None,
    )


def test_missing_endpoint_return_stays_null_without_database_or_zero_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    prior = _attribution_point(
        "native:prior", datetime(2026, 10, 1, 12, tzinfo=UTC), Decimal("0.12")
    )
    current = _attribution_point("native:current", datetime(2026, 10, 2, 12, tzinfo=UTC), None)
    current.model_id = prior.model_id
    current.revision_number = 2
    history = s.CompanyExpectedReturnHistoryRead(
        company_id=company_id,
        as_of=date(2026, 10, 2),
        known_at=datetime(2026, 10, 2, 23, tzinfo=UTC),
        status="PARTIAL",
        history=[prior, current],
    )
    monkeypatch.setattr(
        "portfolio_api.expected_return_attribution.q.company_expected_return_history",
        lambda *_args, **_kwargs: history,
    )

    result = company_expected_return_attribution(
        cast(Session, None), company_id, prior.point_id, current.point_id
    )

    assert result.status == "MISSING_RETURN"
    assert result.prior.expected_cash_flow_irr == Decimal("0.12")
    assert result.current.expected_cash_flow_irr is None
    assert result.expected_irr_change is None
    assert result.residual is None
    assert result.drivers == []


@pytest.mark.integration
def test_native_dcf_attribution_recalculates_price_probability_rates_and_model_inputs(
    postgres_engine: Engine,
) -> None:
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post(
            "/v1/companies", json={"name": "Attribution test issuer", "reporting_currency": "USD"}
        ).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Attribution test common", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "NASDAQ", "ticker": "ATTR", "currency": "USD"},
        ).json()
        prior_effective = datetime.now(UTC) - timedelta(days=3)
        with Session(postgres_engine) as session, session.begin():
            session.add(
                PriceObservation(
                    listing_id=UUID(listing["id"]),
                    price_kind="DAILY_CLOSE",
                    market_date=prior_effective.replace(hour=0, minute=0, second=0, microsecond=0),
                    observed_at=prior_effective,
                    recorded_at=prior_effective,
                    provider_close=Decimal("343.5"),
                    split_adjusted_close=Decimal("343.5"),
                    total_return_close=Decimal("343.5"),
                    currency="USD",
                    provider_currency="USD",
                    provider="ATTRIBUTION_FIXTURE",
                    provider_symbol="NASDAQ:ATTR",
                    adjustment_basis="TEST_REFERENCE_PRICE",
                    data_quality="PASS",
                    source_ref="fixture:attribution-price:343.5",
                )
            )

        payload = cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))
        initial = copy.deepcopy(cast(dict[str, object], payload["input"]))
        initial["source_revision_id"] = None
        initial["effective_at"] = prior_effective.isoformat()
        created = client.post(
            f"/v1/companies/{company['id']}/financial-models",
            json={
                "model_type": "UFCF_DCF_10Y_FADE",
                "model_name": "Attribution test DCF",
                "valuation_listing_id": listing["id"],
                "model_currency": "USD",
                "source_model_key": "P-ATTR",
                "initial_revision": initial,
            },
        )
        assert created.status_code == 201, created.text
        model = created.json()
        prior_revision = model["current_revision"]

        current_effective = datetime.now(UTC) - timedelta(days=1)
        with Session(postgres_engine) as session, session.begin():
            session.add(
                PriceObservation(
                    listing_id=UUID(listing["id"]),
                    price_kind="DAILY_CLOSE",
                    market_date=current_effective.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ),
                    observed_at=current_effective,
                    recorded_at=current_effective,
                    provider_close=Decimal("360"),
                    split_adjusted_close=Decimal("360"),
                    total_return_close=Decimal("360"),
                    currency="USD",
                    provider_currency="USD",
                    provider="ATTRIBUTION_FIXTURE",
                    provider_symbol="NASDAQ:ATTR",
                    adjustment_basis="TEST_REFERENCE_PRICE",
                    data_quality="PASS",
                    source_ref="fixture:attribution-price:360",
                )
            )
        updated = copy.deepcopy(initial)
        updated["base_revision_id"] = prior_revision["id"]
        updated["actor"] = "LOCAL_USER"
        updated["source"] = "Attribution test"
        updated["rationale"] = "Changed price, probability, return rates and operating inputs."
        updated["effective_at"] = current_effective.isoformat()
        updated_base = cast(dict[str, object], updated["base"])
        updated_base["base_revenue"] = str(
            Decimal(str(updated_base["base_revenue"])) * Decimal("1.05")
        )
        updated_scenarios = cast(list[dict[str, object]], updated["scenarios"])
        probabilities = (Decimal("0.15"), Decimal("0.55"), Decimal("0.30"))
        for index, scenario in enumerate(updated_scenarios):
            scenario["probability"] = str(probabilities[index])
            scenario["year10_ufcf_growth"] = str(
                Decimal(str(scenario["year10_ufcf_growth"])) + Decimal("0.005")
            )
            years = cast(list[dict[str, object]], scenario["years"])
            for year in years:
                year["discount_rate"] = str(Decimal(str(year["discount_rate"])) + Decimal("0.005"))
        accepted = client.post(f"/v1/financial-models/{model['id']}/revisions", json=updated)
        assert accepted.status_code == 201, accepted.text
        current_revision = accepted.json()

        history = client.get(f"/v1/companies/{company['id']}/expected-return-history")
        assert history.status_code == 200, history.text
        native = [
            row
            for row in history.json()["history"]
            if row["source_kind"] == "NATIVE_MODEL_REVISION"
        ]
        by_revision = {row["revision_id"]: row for row in native}
        prior_point = by_revision[prior_revision["id"]]
        current_point = by_revision[current_revision["id"]]
        response = client.get(
            f"/v1/companies/{company['id']}/expected-return-attribution",
            params={
                "prior_point_id": prior_point["point_id"],
                "current_point_id": current_point["point_id"],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "ATTRIBUTED"
        assert result["method"] == "SYMMETRIC_COUNTERFACTUAL_SHAPLEY"
        assert result["prior"]["revision_id"] == prior_revision["id"]
        assert result["current"]["revision_id"] == current_revision["id"]
        assert (
            result["prior"]["market_price"]["observation_id"]
            != result["current"]["market_price"]["observation_id"]
        )
        assert {driver["code"] for driver in result["drivers"]} == {
            "MARKET_PRICE",
            "SCENARIO_PROBABILITIES",
            "REQUIRED_RETURN_ASSUMPTIONS",
            "MODEL_ASSUMPTIONS",
        }
        total = Decimal(result["expected_irr_change"])
        effects = sum((Decimal(driver["effect"]) for driver in result["drivers"]), Decimal(0))
        residual = Decimal(result["residual"])
        assert abs(total - effects - residual) <= Decimal("0.000000000001")
        assert "not improved company economics" in next(
            driver["explanation"]
            for driver in result["drivers"]
            if driver["code"] == "REQUIRED_RETURN_ASSUMPTIONS"
        )


def test_shapley_bridge_attributes_multiple_interacting_drivers_additively() -> None:
    # Each bit switches one historical input group to the newer endpoint. The
    # interaction terms force the attribution to account for ordering effects.
    def expected_irr(mask: int) -> Decimal:
        price = Decimal(bool(mask & 1))
        probabilities = Decimal(bool(mask & 2))
        required_return = Decimal(bool(mask & 4))
        assumptions = Decimal(bool(mask & 8))
        return (
            Decimal("0.10")
            + price * Decimal("0.02")
            - probabilities * Decimal("0.01")
            + required_return * Decimal("0.03")
            - assumptions * Decimal("0.04")
            + price * probabilities * Decimal("0.01")
            + required_return * assumptions * Decimal("0.02")
        )

    factors = ("PRICE", "PROBABILITY", "RATE", "MODEL")
    effects = symmetric_shapley_decomposition(expected_irr, factors)
    total_change = expected_irr(15) - expected_irr(0)

    assert set(effects) == set(factors)
    assert all(effect != 0 for effect in effects.values())
    assert abs(sum(effects.values(), Decimal(0)) - total_change) < Decimal("1e-24")
    assert effects["RATE"] != Decimal("0.03")  # includes half the rate/model interaction
    assert effects == symmetric_shapley_decomposition(expected_irr, factors)


def test_shapley_supports_no_effect_and_single_factor_cases() -> None:
    assert symmetric_shapley_decomposition(lambda _mask: Decimal("0"), ("PRICE",)) == {
        "PRICE": Decimal(0)
    }
    assert symmetric_shapley_decomposition(
        lambda mask: Decimal("0.12") if mask & 1 else Decimal("0.08"), ("PRICE",)
    ) == {"PRICE": Decimal("0.04")}


@pytest.mark.parametrize("bad_count", [0, 1, 3])
def test_shapley_decomposition_is_deterministic_for_small_factor_sets(bad_count: int) -> None:
    factors = tuple(f"driver-{index}" for index in range(bad_count))
    effects = symmetric_shapley_decomposition(
        lambda mask: Decimal(mask.bit_count()) / Decimal(100), factors
    )
    assert sum(effects.values(), Decimal(0)) == Decimal(bad_count) / Decimal(100)
