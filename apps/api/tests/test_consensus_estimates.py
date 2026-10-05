import asyncio
import json
import urllib.request
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.consensus_estimates import (
    FMP_PROVIDER_ID,
    LEGACY_PROVIDER_ID,
    NORMALIZER_VERSION,
    CanonicalConsensusEstimate,
    FmpConsensusNormalizer,
    FmpConsensusProvider,
    estimate_values_changed,
    legacy_estimate_import_plan,
)
from portfolio_api.domain.consensus_policy import select_consensus_source
from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateBatch,
    ConsensusEstimateDataQuality,
    ConsensusEstimateObservation,
    ConsensusEstimatePeriodType,
    ConsensusEstimateProviderMapping,
    ConsensusEstimateRevisionContext,
    ConsensusEstimateSourceRole,
    protect_history,
)
from portfolio_api.domain.queries import company_consensus_estimates
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)


def mapping(
    *,
    provider: str = FMP_PROVIDER_ID,
    role: ConsensusEstimateSourceRole = ConsensusEstimateSourceRole.PRIMARY,
    priority: int = 10,
    effective: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    currency: str | None = "USD",
) -> ConsensusEstimateProviderMapping:
    return ConsensusEstimateProviderMapping(
        id=uuid4(),
        company_id=uuid4(),
        listing_id=None,
        provider_id=provider,
        provider_symbol="EXACT",
        role=role.value,
        priority=priority,
        currency=currency,
        evidence_source="https://example.test/identity",
        currency_evidence_source="https://example.test/currency" if currency else None,
        effective_from=effective,
        recorded_at=effective,
        actor="LOCAL_USER",
    )


def provider_record(payload: bytes, *, source: str = "EXACT:annual") -> RawProviderRecord:
    return RawProviderRecord(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        provider_id=FMP_PROVIDER_ID,
        provider_schema_version="stable",
        source_record_id=source,
        source_url="https://financialmodelingprep.com/stable/analyst-estimates",
        media_type="application/json",
        retrieved_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
        payload=payload,
        payload_sha256=__import__("hashlib").sha256(payload).hexdigest(),
    )


def test_fmp_normalizer_keeps_forward_periods_and_exact_values() -> None:
    row = json.dumps(
        [
            {
                "date": "2027-12-31",
                "revenueAvg": 123.456789,
                "revenueLow": 100,
                "revenueHigh": 150,
                "numAnalystsRevenue": 22,
                "epsAvg": 4.25,
                "epsLow": 3,
                "epsHigh": 5,
                "numAnalystsEps": 17,
            },
            {"date": "2025-12-31", "revenueAvg": 99, "epsAvg": 3},
        ]
    ).encode()
    result = FmpConsensusNormalizer(mapping(), date(2026, 10, 5)).normalize(provider_record(row))

    assert result.disposition == "ACCEPTED"
    assert result.observation is not None
    revenue, eps = result.observation
    assert isinstance(revenue, CanonicalConsensusEstimate)
    assert revenue.metric == "REVENUE"
    assert revenue.value == Decimal("123.456789")
    assert revenue.period_end == date(2027, 12, 31)
    assert revenue.currency == "USD"
    assert revenue.analyst_count == 22
    assert eps.metric == "EPS"
    assert eps.unit == "CURRENCY_PER_SHARE"
    assert eps.analyst_count == 17
    assert len(result.issues) == 1
    assert result.issues[0].code == "NON_FORWARD_PERIOD"


def test_missing_currency_or_coverage_is_data_check_and_missing_estimate_is_omitted() -> None:
    mapped_without_currency = mapping(currency=None)
    payload = json.dumps(
        [{"date": "2027-12-31", "revenueAvg": 100, "numAnalystsRevenue": None, "epsAvg": None}]
    ).encode()
    result = FmpConsensusNormalizer(mapped_without_currency, date(2026, 10, 5)).normalize(
        provider_record(payload)
    )

    assert result.observation is not None
    assert len(result.observation) == 1
    revenue = result.observation[0]
    assert revenue.value == Decimal("100")
    assert revenue.currency is None
    assert revenue.analyst_count is None
    assert revenue.data_quality == "DATA_CHECK"
    assert "currency" in (revenue.quality_reason or "")
    assert "analyst count" in (revenue.quality_reason or "")
    assert all(item.metric != "EPS" for item in result.observation)


def test_primary_continuity_never_fills_gaps_from_fallback() -> None:
    primary = mapping(provider="primary", role=ConsensusEstimateSourceRole.PRIMARY)
    fallback = mapping(provider="backup", role=ConsensusEstimateSourceRole.FALLBACK, priority=1)

    selected, status = select_consensus_source([primary, fallback])

    assert selected is primary
    assert status == "PRIMARY_SELECTED"


def test_fallback_requires_unambiguous_priority_and_is_not_blended() -> None:
    first = mapping(provider="fallback_a", role=ConsensusEstimateSourceRole.FALLBACK, priority=10)
    second = mapping(provider="fallback_b", role=ConsensusEstimateSourceRole.FALLBACK, priority=10)
    selected, status = select_consensus_source([first, second])
    assert selected is None
    assert status == "AMBIGUOUS_FALLBACK"

    preferred, status = select_consensus_source(
        [first, mapping(provider="later", role=ConsensusEstimateSourceRole.FALLBACK, priority=20)]
    )
    assert preferred is first
    assert status == "FALLBACK_SELECTED"


def test_fmp_transport_uses_exact_mapping_and_never_persists_api_key_in_source_url(
    monkeypatch: MonkeyPatch,
) -> None:
    requests: list[str] = []

    class Response:
        headers = {"X-Api-Version": "stable-test"}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self) -> bytes:
            return b"[]"

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> Response:
        requests.append(request.full_url)
        assert timeout == 30
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    company_id = uuid4()
    provider = FmpConsensusProvider("secret-test-key", {company_id: "EXACT"})
    query = ProviderQuery(
        domain=ExternalDataDomain.CONSENSUS_ESTIMATES,
        subjects=(CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=company_id),),
        requested_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )

    records = asyncio.run(provider.fetch(query))

    assert len(records) == 2
    assert {"annual", "quarter"} == {url.split("period=")[1].split("&")[0] for url in requests}
    assert all("symbol=EXACT" in url and "apikey=secret-test-key" in url for url in requests)
    assert all("secret-test-key" not in str(record.source_url) for record in records)
    assert all(record.payload_sha256 for record in records)


def test_correction_comparison_detects_value_and_coverage_changes() -> None:
    previous = ConsensusEstimateObservation(
        value=Decimal("10"),
        low_value=Decimal("8"),
        high_value=Decimal("12"),
        analyst_count=5,
        currency="USD",
    )
    unchanged = {
        "value": Decimal("10"),
        "low_value": Decimal("8"),
        "high_value": Decimal("12"),
        "analyst_count": 5,
        "currency": "USD",
    }
    revised = {**unchanged, "value": Decimal("11"), "analyst_count": 6}
    assert not estimate_values_changed(previous, unchanged)
    assert estimate_values_changed(previous, revised)


def test_consensus_batches_and_observations_are_append_only() -> None:
    class DirtySession:
        def __init__(self, item: object) -> None:
            self.dirty = {item}
            self.deleted: set[object] = set()

    for item in (ConsensusEstimateBatch(), ConsensusEstimateObservation()):
        try:
            protect_history(DirtySession(item), None, None)
        except ValueError as error:
            assert "append-only" in str(error)
        else:
            raise AssertionError("Consensus history mutation was not rejected")


def test_legacy_history_reconciliation_only_imports_supported_snapshot_fields() -> None:
    report, observations = legacy_estimate_import_plan()
    facts = [item for item in observations if "value" in item]

    assert report["source_sha256"]
    assert report["company_rows"] == 79
    assert report["resolved_company_count"] == 79
    assert report["snapshot_date"] == "2026-09-12"
    assert len(facts) == 67
    assert {item["status"] for item in facts} == {"DATA_CHECK"}
    assert {item["metric"] for item in facts} == {"REVENUE", "EPS"}
    assert {item["horizon"] for item in facts} == {"FY+1", "FY+2"}
    assert all(item["snapshot_date"] == "2026-09-12" for item in facts)
    assert report["limitations"]
    assert NORMALIZER_VERSION == "consensus-estimates-v1"
    assert LEGACY_PROVIDER_ID != FMP_PROVIDER_ID


def test_company_query_is_point_in_time_and_does_not_fill_a_primary_gap(
    postgres_engine: Engine,
) -> None:
    company_id = uuid4()
    primary_id = uuid4()
    fallback_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Consensus test company",
                reporting_currency="USD",
                is_demo=False,
            )
        )
        primary = ConsensusEstimateProviderMapping(
            id=primary_id,
            company_id=company_id,
            listing_id=None,
            provider_id="primary_estimates",
            provider_symbol="PRIMARY",
            role=ConsensusEstimateSourceRole.PRIMARY.value,
            priority=10,
            currency="USD",
            evidence_source="https://example.test/primary-identity",
            currency_evidence_source="https://example.test/primary-currency",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
            actor="LOCAL_USER",
        )
        fallback = ConsensusEstimateProviderMapping(
            id=fallback_id,
            company_id=company_id,
            listing_id=None,
            provider_id="fallback_estimates",
            provider_symbol="FALLBACK",
            role=ConsensusEstimateSourceRole.FALLBACK.value,
            priority=20,
            currency="USD",
            evidence_source="https://example.test/fallback-identity",
            currency_evidence_source="https://example.test/fallback-currency",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
            actor="LOCAL_USER",
        )
        session.add_all([primary, fallback])
        session.flush()
        observed_old = datetime(2026, 10, 1, 12, tzinfo=UTC)
        observed_new = datetime(2026, 10, 5, 12, tzinfo=UTC)
        batch_old = _test_batch("1" * 64, observed_old)
        batch_new = _test_batch("2" * 64, observed_new)
        fallback_observed = datetime(2026, 10, 4, 12, tzinfo=UTC)
        batch_fallback = _test_batch("3" * 64, fallback_observed, "fallback_estimates")
        session.add_all([batch_old, batch_new, batch_fallback])
        session.flush()
        old_observation_id = uuid4()
        old = _test_observation(
            old_observation_id, company_id, primary_id, batch_old.id, "10", observed_old
        )
        revised = _test_observation(
            uuid4(),
            company_id,
            primary_id,
            batch_new.id,
            "12",
            observed_new,
            supersedes=old_observation_id,
        )
        fallback_eps = _test_observation(
            uuid4(),
            company_id,
            fallback_id,
            batch_fallback.id,
            "2",
            fallback_observed,
            metric="EPS",
            provider_id="fallback_estimates",
        )
        session.add_all([old, revised, fallback_eps])
        session.flush()

        current = company_consensus_estimates(session, company_id, as_of=date(2026, 10, 5))
        known_then = company_consensus_estimates(
            session,
            company_id,
            as_of=date(2026, 10, 5),
            known_at=datetime(2026, 10, 3, 0, tzinfo=UTC),
        )
        selected = next(item for item in current.providers if item.selected)
        alternate = next(item for item in current.providers if not item.selected)
        assert current.continuity_status == "PRIMARY_SELECTED"
        assert selected.provider_id == "primary_estimates"
        assert selected.missing_metrics == ["EPS"]
        assert not alternate.selected
        assert alternate.periods[0].metric == "EPS"
        assert selected.periods[0].current_observation is not None
        assert selected.periods[0].current_observation.value == Decimal("12")
        historic_primary = next(item for item in known_then.providers if item.selected)
        assert historic_primary.periods[0].current_observation is not None
        assert historic_primary.periods[0].current_observation.value == Decimal("10")


def _test_batch(
    digest: str,
    observed_at: datetime,
    provider_id: str = "primary_estimates",
) -> ConsensusEstimateBatch:
    return ConsensusEstimateBatch(
        id=uuid4(),
        provider_id=provider_id,
        provider_schema_version="fixture",
        normalizer_version=NORMALIZER_VERSION,
        domain="CONSENSUS_ESTIMATES",
        source_kind="PROVIDER_RESPONSE",
        source_digest=digest,
        source_reference="https://example.test/response",
        query_scope={"fixture": True},
        snapshot_date=observed_at.date(),
        observed_at=observed_at,
        recorded_at=observed_at,
        provider_summary={},
        reconciliation={},
    )


def _test_observation(
    observation_id: UUID,
    company_id: UUID,
    mapping_id: UUID,
    batch_id: UUID,
    value: str,
    observed_at: datetime,
    *,
    supersedes: UUID | None = None,
    metric: str = "REVENUE",
    provider_id: str = "primary_estimates",
) -> ConsensusEstimateObservation:
    return ConsensusEstimateObservation(
        id=observation_id,
        company_id=company_id,
        listing_id=None,
        provider_mapping_id=mapping_id,
        batch_id=batch_id,
        provider_id=provider_id,
        metric=metric,
        period_type=ConsensusEstimatePeriodType.ANNUAL.value,
        forecast_period="ANNUAL ending 2027-12-31",
        period_end=date(2027, 12, 31),
        value=Decimal(value),
        low_value=None,
        high_value=None,
        analyst_count=10,
        currency="USD",
        unit="CURRENCY" if metric == "REVENUE" else "CURRENCY_PER_SHARE",
        snapshot_date=observed_at.date(),
        observed_at=observed_at,
        recorded_at=observed_at,
        source_record_id=f"{provider_id}:{metric}:{observed_at.date()}",
        source_ref="https://example.test/response",
        revision_context=(
            ConsensusEstimateRevisionContext.REVISED.value
            if supersedes
            else ConsensusEstimateRevisionContext.SNAPSHOT.value
        ),
        data_quality=ConsensusEstimateDataQuality.PASS.value,
        quality_reason=None,
        supersedes_observation_id=supersedes,
    )
