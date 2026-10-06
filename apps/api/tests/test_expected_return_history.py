from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateBatch,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    Listing,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
    PriceObservation,
    Security,
)
from portfolio_api.domain.queries import company_expected_return_history
from portfolio_api.expected_return_attribution import company_expected_return_attribution


def stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_history_composes_as_of_sources_without_merging_or_lookahead(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id, model_id = (uuid4() for _ in range(4))
    rev1_id, rev2_id, rev3_id = uuid4(), uuid4(), uuid4()
    quote_ids = [uuid4() for _ in range(4)]
    import_batch_id = uuid4()
    estimate_mapping_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add_all(
            [
                Company(
                    id=company_id,
                    name="Expected return history test",
                    reporting_currency="USD",
                ),
                Security(
                    id=security_id,
                    company_id=company_id,
                    name="History common stock",
                    security_type="COMMON_STOCK",
                    share_class=None,
                    underlying_security_id=None,
                ),
            ]
        )
        session.flush()
        session.add(
            Listing(
                id=listing_id,
                security_id=security_id,
                ticker="HIST",
                venue="NASDAQ",
                currency="USD",
            )
        )
        session.flush()

        quotes = [
            (quote_ids[0], "2026-10-01T00:00:00Z", "2026-10-01T15:00:00Z", "100"),
            (quote_ids[1], "2026-10-03T00:00:00Z", "2026-10-03T15:00:00Z", "110"),
            (quote_ids[2], "2026-10-05T00:00:00Z", "2026-10-05T15:00:00Z", "120"),
            (quote_ids[3], "2026-10-05T00:00:00Z", "2026-10-07T15:00:00Z", "130"),
        ]
        for quote_id, market_date, recorded_at, value in quotes:
            session.add(
                PriceObservation(
                    id=quote_id,
                    listing_id=listing_id,
                    batch_id=None,
                    price_kind="DAILY_CLOSE",
                    market_date=stamp(market_date),
                    observed_at=(None if quote_id == quote_ids[0] else stamp(recorded_at)),
                    recorded_at=stamp(recorded_at),
                    provider_close=Decimal(value),
                    split_adjusted_close=Decimal(value),
                    total_return_close=Decimal(value),
                    volume=None,
                    currency="USD",
                    provider_currency="USD",
                    source_price_multiplier=Decimal(1),
                    provider="YAHOO_FINANCE",
                    provider_symbol="NASDAQ:HIST",
                    adjustment_basis="provider-unadjusted-close",
                    data_quality="PASS",
                    source_ref=f"fixture:price:{value}",
                    supersedes_observation_id=None,
                )
            )
        session.flush()

        model = FinancialModel(
            id=model_id,
            company_id=company_id,
            valuation_listing_id=listing_id,
            model_type="UFCF_DCF_10Y_FADE",
            model_name="History DCF",
            model_currency="USD",
            source_model_key="P-HIST",
        )
        session.add(model)
        session.flush()
        revisions = [
            (rev1_id, 1, "2026-10-01T16:00:00Z", "2026-10-01T16:00:00Z"),
            (rev2_id, 2, "2026-10-05T16:00:00Z", "2026-10-05T16:00:00Z"),
            (rev3_id, 3, "2026-10-06T16:00:00Z", "2026-10-06T16:00:00Z"),
        ]
        for revision_id, number, effective, recorded in revisions:
            session.add(
                FinancialModelRevision(
                    id=revision_id,
                    model_id=model_id,
                    model_type="UFCF_DCF_10Y_FADE",
                    revision_number=number,
                    base_revision_id=None if number == 1 else rev1_id,
                    methodology_version=("fixture-dcf-v2" if number == 3 else "fixture-dcf-v1"),
                    source_revision_id=None,
                    contract_digest=None,
                    actor="LOCAL_USER",
                    source="synthetic test",
                    rationale=f"History revision {number}",
                    effective_at=stamp(effective),
                    recorded_at=stamp(recorded),
                )
            )
        session.flush()
        model.current_revision_id = rev3_id
        for index, (revision_id, price_id, value, irr) in enumerate(
            [
                (rev1_id, quote_ids[0], "100", "0.12"),
                (rev2_id, quote_ids[2], "120", "0.14"),
                (rev3_id, quote_ids[3], "130", "0.16"),
            ]
        ):
            session.add(
                FinancialModelOutput(
                    id=uuid4(),
                    revision_id=revision_id,
                    status="COMPLETE",
                    model_currency="USD",
                    price_observation_id=price_id,
                    current_price=Decimal(value),
                    price_effective_at=(stamp(quotes[index][1]) if price_id is not None else None),
                    price_status="FRESH" if price_id is not None else "NO_DATA",
                    price_unavailable_reason=None,
                    irr_unavailable_reason=None,
                    bear_fv=Decimal("70"),
                    base_fv=Decimal("100"),
                    bull_fv=Decimal("140"),
                    bear_probability=Decimal("0.2"),
                    base_probability=Decimal("0.6"),
                    bull_probability=Decimal("0.2"),
                    weighted_fv=Decimal("100"),
                    weighted_upside=Decimal("0.1"),
                    expected_cash_flow_irr=Decimal(irr),
                    hurdle=Decimal("0.09"),
                    expected_excess=Decimal(irr) - Decimal("0.09"),
                    forward_fundamental_cagr=Decimal("0.08"),
                )
            )

        session.add(
            ModelOutputImportBatch(
                id=import_batch_id,
                source_digest="a" * 64,
                workbook_sha256="b" * 64,
                observed_at=stamp("2026-10-04T10:00:00Z"),
                recorded_at=stamp("2026-10-04T10:00:00Z"),
                reconciliation={},
            )
        )
        session.add(
            ModelOutputSnapshot(
                id=uuid4(),
                company_id=company_id,
                batch_id=import_batch_id,
                model_key="P-HIST",
                snapshot_key="legacy-revision-2026-10-03",
                source_fingerprint="c" * 64,
                snapshot_kind="LEGACY_REVISION",
                contract_version="1",
                contract_status="PASS",
                output_quality="COMPLETE",
                model_currency="USD",
                currency_status="DOCUMENTED",
                currency_source_ref="fixture",
                model_status="COMPLETE",
                effective_at=stamp("2026-10-03T16:00:00Z"),
                recorded_at=stamp("2026-10-04T10:00:00Z"),
                actor="IMPORT",
                source="Portfolio_Watchlist.xlsx:P-HIST",
                source_revision_id="legacy-2026-10-03",
                revision_source="Workbook",
                revision_type="Periodic review",
                source_actor="Research team",
                rationale="Legacy source snapshot",
                evidence="Workbook fixture",
                notes=None,
                field_issues=[],
                bear_fv=Decimal("65"),
                base_fv=Decimal("95"),
                bull_fv=Decimal("130"),
                bear_probability=Decimal("0.2"),
                base_probability=Decimal("0.6"),
                bull_probability=Decimal("0.2"),
                weighted_fv=Decimal("95"),
                weighted_upside=Decimal("0.05"),
                expected_cash_flow_irr=Decimal("0.11"),
                hurdle=Decimal("0.09"),
                expected_excess=Decimal("0.02"),
                forward_fundamental_cagr=Decimal("0.07"),
            )
        )

        session.add(
            ConsensusEstimateProviderMapping(
                id=estimate_mapping_id,
                company_id=company_id,
                listing_id=listing_id,
                provider_id="fmp_estimates",
                provider_symbol="HIST",
                role="PRIMARY",
                priority=10,
                currency="USD",
                evidence_source="fixture provider identity",
                currency_evidence_source="fixture estimate currency",
                effective_from=stamp("2026-10-01T09:00:00Z"),
                recorded_at=stamp("2026-10-01T09:00:00Z"),
                actor="IMPORT",
            )
        )
        for index, (snapshot_date, observed_at, recorded_at, value) in enumerate(
            [
                ("2026-10-01", "2026-10-01T12:00:00Z", "2026-10-01T12:01:00Z", "100"),
                ("2026-10-05", "2026-10-05T15:00:00Z", "2026-10-05T15:01:00Z", "110"),
                ("2026-10-05", "2026-10-05T17:00:00Z", "2026-10-05T17:01:00Z", "999"),
            ]
        ):
            batch_id = uuid4()
            observed = stamp(observed_at)
            session.add(
                ConsensusEstimateBatch(
                    id=batch_id,
                    provider_id="fmp_estimates",
                    provider_schema_version="fixture-v1",
                    normalizer_version="fixture-v1",
                    domain="CONSENSUS_ESTIMATES",
                    source_kind="PROVIDER_RESPONSE",
                    source_digest=f"{index + 1:064x}",
                    source_reference="https://example.test/estimate-history",
                    query_scope={"fixture": True},
                    snapshot_date=date.fromisoformat(snapshot_date),
                    observed_at=observed,
                    recorded_at=stamp(recorded_at),
                    provider_summary={},
                    reconciliation={},
                )
            )
            session.flush()
            session.add(
                ConsensusEstimateObservation(
                    id=uuid4(),
                    company_id=company_id,
                    listing_id=listing_id,
                    provider_mapping_id=estimate_mapping_id,
                    batch_id=batch_id,
                    provider_id="fmp_estimates",
                    metric="REVENUE",
                    period_type="ANNUAL",
                    forecast_period="FY2027",
                    period_end=date(2027, 12, 31),
                    value=Decimal(value),
                    low_value=None,
                    high_value=None,
                    analyst_count=8 + index,
                    currency="USD",
                    unit="CURRENCY",
                    snapshot_date=date.fromisoformat(snapshot_date),
                    observed_at=observed,
                    recorded_at=stamp(recorded_at),
                    source_record_id=f"estimate:{index}",
                    source_ref=f"https://example.test/estimate-history#{index}",
                    revision_context="REVISED" if index else "SNAPSHOT",
                    data_quality="PASS",
                    quality_reason=None,
                    supersedes_observation_id=None,
                )
            )
        session.flush()
        same_day_estimate_time = stamp("2026-10-05T15:30:00Z")
        same_day_batch_id = uuid4()
        session.add(
            ConsensusEstimateBatch(
                id=same_day_batch_id,
                provider_id="fmp_estimates",
                provider_schema_version="fixture-v1",
                normalizer_version="fixture-v1",
                domain="CONSENSUS_ESTIMATES",
                source_kind="PROVIDER_RESPONSE",
                source_digest="4" * 64,
                source_reference="https://example.test/estimate-history#same-day",
                query_scope={"fixture": True},
                snapshot_date=date(2026, 10, 5),
                observed_at=same_day_estimate_time,
                recorded_at=same_day_estimate_time,
                provider_summary={},
                reconciliation={},
            )
        )
        session.flush()
        session.add(
            ConsensusEstimateObservation(
                id=uuid4(),
                company_id=company_id,
                listing_id=listing_id,
                provider_mapping_id=estimate_mapping_id,
                batch_id=same_day_batch_id,
                provider_id="fmp_estimates",
                metric="EPS",
                period_type="ANNUAL",
                forecast_period="FY2028",
                period_end=date(2028, 12, 31),
                value=Decimal("50"),
                low_value=None,
                high_value=None,
                analyst_count=8,
                currency="USD",
                unit="CURRENCY",
                snapshot_date=date(2026, 10, 5),
                observed_at=None,
                recorded_at=same_day_estimate_time,
                source_record_id="estimate:same-day-unknown-time",
                source_ref="https://example.test/estimate-history#same-day",
                revision_context="SNAPSHOT",
                data_quality="PASS",
                quality_reason=None,
                supersedes_observation_id=None,
            )
        )
        session.flush()

        history = company_expected_return_history(
            session,
            company_id,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T23:59:59Z"),
        )

        assert history.status == "AVAILABLE"
        assert [point.source_kind for point in history.history] == [
            "NATIVE_MODEL_REVISION",
            "IMPORTED_LEGACY_REVISION",
            "NATIVE_MODEL_REVISION",
        ]
        native_current = next(point for point in history.history if point.is_current_at_cutoff)
        assert native_current.revision_id == rev2_id
        assert native_current.expected_cash_flow_irr == Decimal("0.140000000000000000")
        assert native_current.hurdle == Decimal("0.090000000000000000")
        assert native_current.expected_excess == Decimal("0.050000000000000000")
        assert native_current.market_price.model_reference_price == Decimal(
            "120.000000000000000000"
        )
        assert native_current.market_price.observed_at == stamp("2026-10-05T15:00:00Z")
        assert native_current.market_price.recorded_at == stamp("2026-10-05T15:00:00Z")
        assert native_current.market_price.adjustment_basis == "provider-unadjusted-close"
        assert native_current.estimate_context.provider_id == "fmp_estimates"
        assert native_current.estimate_context.periods[0].value == Decimal("110.000000000000")
        assert native_current.estimate_context.periods[0].observation_id is not None
        assert native_current.estimate_context.periods[0].source_ref.endswith("#1")
        assert all(estimate.metric != "EPS" for estimate in native_current.estimate_context.periods)
        assert all(
            estimate.value != Decimal("999.000000000000")
            for estimate in native_current.estimate_context.periods
        )
        native_prior = next(
            point
            for point in history.history
            if point.source_kind == "NATIVE_MODEL_REVISION" and point.revision_id == rev1_id
        )
        assert native_prior.market_price.status == "DATA_CHECK"
        assert "observation timestamp" in (native_prior.market_price.reason or "")

        legacy = next(
            point for point in history.history if point.source_kind == "IMPORTED_LEGACY_REVISION"
        )
        assert legacy.return_semantics == "LEGACY_NORMALIZED_FIELD"
        assert legacy.valuation_ticker == "HIST"
        assert legacy.actor == "IMPORT"
        assert legacy.source_actor == "Research team"
        assert legacy.revision_type == "Periodic review"
        assert legacy.market_price.quote == Decimal("110.0000000000")
        assert legacy.weighted_fv == Decimal("95.0000000000000000000000")

        earlier = company_expected_return_history(
            session,
            company_id,
            as_of=date(2026, 10, 4),
            known_at=stamp("2026-10-04T23:59:59Z"),
        )
        assert len(earlier.history) == 2
        assert sum(point.is_current_at_cutoff for point in earlier.history) == 1
        assert all(point.revision_id != rev2_id for point in earlier.history)

        later = company_expected_return_history(
            session,
            company_id,
            as_of=date(2026, 10, 6),
            known_at=stamp("2026-10-07T23:59:59Z"),
        )
        revision_three = next(point for point in later.history if point.revision_id == rev3_id)
        assert revision_three.market_price.status == "PRICE_NOT_CAPTURED"
        assert revision_three.market_price.model_reference_price == Decimal("130")
        assert revision_three.market_price.quote is None

        legacy_to_native = company_expected_return_attribution(
            session,
            company_id,
            legacy.point_id,
            native_current.point_id,
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T23:59:59Z"),
        )
        assert legacy_to_native.status == "RETURN_SEMANTICS_CHANGE"
        assert legacy_to_native.expected_irr_change is None
        assert legacy_to_native.prior.expected_cash_flow_irr == Decimal("0.11")
        assert legacy_to_native.current.expected_cash_flow_irr == Decimal("0.14")

        native_unavailable_inputs = company_expected_return_attribution(
            session,
            company_id,
            f"native:{rev1_id}",
            f"native:{rev2_id}",
            as_of=date(2026, 10, 5),
            known_at=stamp("2026-10-05T23:59:59Z"),
        )
        assert native_unavailable_inputs.status == "INPUTS_UNAVAILABLE"
        assert native_unavailable_inputs.expected_irr_change == Decimal("0.02")
        assert native_unavailable_inputs.residual == Decimal("0.02")
        assert native_unavailable_inputs.drivers == []

        methodology_change = company_expected_return_attribution(
            session,
            company_id,
            f"native:{rev2_id}",
            f"native:{rev3_id}",
            as_of=date(2026, 10, 6),
            known_at=stamp("2026-10-07T23:59:59Z"),
        )
        assert methodology_change.status == "METHODOLOGY_CHANGE"
        assert methodology_change.expected_irr_change == Decimal("0.02")
        assert methodology_change.residual == Decimal("0.02")
        assert methodology_change.drivers == []
