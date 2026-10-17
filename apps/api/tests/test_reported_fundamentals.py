"""Reported-fact normalization and optional PostgreSQL append-only checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.domain.models import (
    Company,
    ExternalRawPayload,
    FundamentalDataQuality,
    FundamentalMetric,
    FundamentalPeriodType,
    FundamentalRevisionContext,
    FundamentalStatement,
    ReportedFundamentalBatch,
    ReportedFundamentalObservation,
    now,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    CanonicalSubjectRef,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.reported_fundamentals import (
    SEC_NORMALIZER_VERSION,
    SEC_PROVIDER_ID,
    SecCompanyFactsProvider,
    _companyfacts_response_matches_cik,
    _normalize_companyfacts_json,
    _normalized_sec_entity_name,
    ingest_sec_company_facts,
    normalize_sec_company_facts,
    record_cik_mapping,
    resolve_fundamental_period,
    sync_reported_fundamentals,
)
from portfolio_api.settings import Settings

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
CIK = "0000000001"
OBSERVED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)
REVENUE = FundamentalMetric.REVENUE.value


@pytest.mark.parametrize(
    ("provider_name", "verified_name"),
    [
        ("COPART, INC.", "COPART INC"),
        ("MercadoLibre, Inc.", "MERCADOLIBRE INC"),
        ("MICROSOFT CORPORATION", "MICROSOFT CORP"),
        ("Mastercard Incorporated", "Mastercard Inc"),
        ("DLocal Limited", "dLocal Ltd"),
        ("Intuitive Surgical, Inc.", "INTUITIVE SURGICAL INC"),
        ("MORNINGSTAR,\u00a0INC.", "Morningstar, Inc."),
        (
            "Taiwan Semiconductor Manufacturing Company Limited",
            "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD",
        ),
        ("Veeva Systems Inc.", "VEEVA SYSTEMS INC"),
        ("COMFORT SYSTEMS USA,\u00a0INC.", "COMFORT SYSTEMS USA INC"),
        ("AXON ENTERPRISE, INC.", "AXON ENTERPRISE INC"),
        ("NOVO NORDISK A/S", "NOVO NORDISK A S"),
    ],
)
def test_sec_entity_name_comparison_accepts_only_format_and_legal_suffix_variants(
    provider_name: str, verified_name: str
) -> None:
    assert _normalized_sec_entity_name(provider_name) == _normalized_sec_entity_name(verified_name)


def test_sec_entity_name_comparison_does_not_treat_renames_or_parent_entities_as_aliases() -> None:
    assert _normalized_sec_entity_name("Facebook, Inc.") != _normalized_sec_entity_name(
        "Meta Platforms, Inc."
    )
    assert _normalized_sec_entity_name("Example Holdings Inc") != _normalized_sec_entity_name(
        "Example Subsidiary Inc"
    )
    assert _companyfacts_response_matches_cik({"cik": 900075}, "0000900075")
    assert not _companyfacts_response_matches_cik({"cik": 900076}, "0000900075")
    assert not _companyfacts_response_matches_cik({"cik": True}, "0000000001")


def companyfacts_payload(
    annual_revenue: int = 9007199254740993,
    accession: str = "0000000001-24-000001",
    filed: str = "2024-02-10",
    entity_name: str = "Example Issuer Inc.",
    cik: int = 1,
) -> bytes:
    """Small synthetic SEC-shaped fixture; it is not company or investment data."""
    facts = {
        "cik": cik,
        "entityName": entity_name,
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": annual_revenue,
                                "accn": accession,
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": filed,
                                "frame": "CY2023",
                            },
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": 250,
                                "accn": "0000000001-24-000002",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-10",
                                "frame": "CY2024Q1",
                            },
                            {
                                "start": "2024-01-01",
                                "end": "2024-06-30",
                                "val": 500,
                                "accn": "0000000001-24-000003",
                                "fy": 2024,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2024-08-10",
                            },
                        ]
                    }
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "end": "2024-03-31",
                                "val": 75,
                                "accn": "0000000001-24-000002",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-10",
                            }
                        ]
                    }
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "val": -31,
                                "accn": "0000000001-24-000002",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-10",
                            }
                        ]
                    }
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 12,
                                "accn": "0000000001-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-10",
                            }
                        ]
                    }
                },
                "UnmappedStandardConcept": {"units": {"USD": []}},
            },
            "issuer-extension": {
                "Revenue": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 999,
                                "form": "10-K",
                            }
                        ]
                    }
                }
            },
        },
    }
    return json.dumps(facts, separators=(",", ":")).encode()


def record(
    payload: bytes | None = None, *, observed_at: datetime = OBSERVED_AT
) -> RawProviderRecord:
    content = payload if payload is not None else companyfacts_payload()
    return RawProviderRecord(
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
        provider_id=SEC_PROVIDER_ID,
        provider_schema_version="companyfacts-v1",
        source_record_id=f"CIK{CIK}",
        source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json",
        media_type="application/json",
        retrieved_at=observed_at,
        payload=content,
        payload_sha256=hashlib.sha256(content).hexdigest(),
    )


def test_sec_companyfacts_normalization_preserves_period_currency_units_and_exact_values() -> None:
    facts, counters, issues = _normalize_companyfacts_json(record(), COMPANY_ID, CIK)
    by_metric = {item.metric: item for item in facts if item.period_end.year == 2023}
    annual_revenue = by_metric[FundamentalMetric.REVENUE]

    assert annual_revenue.value == Decimal("9007199254740993")
    assert annual_revenue.period_type == FundamentalPeriodType.ANNUAL
    assert annual_revenue.period_start is not None
    assert annual_revenue.period_start.date().isoformat() == "2023-01-01"
    assert annual_revenue.period_end.date().isoformat() == "2023-12-31"
    assert annual_revenue.fiscal_year == 2023
    assert annual_revenue.fiscal_period == "FY"
    assert annual_revenue.filed_at is not None
    assert annual_revenue.filed_at.date().isoformat() == "2024-02-10"
    assert annual_revenue.currency == "USD"
    assert by_metric[FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES].currency is None
    assert by_metric[FundamentalMetric.DILUTED_WEIGHTED_AVERAGE_SHARES].unit == "shares"
    quarterly = [
        item
        for item in facts
        if item.metric == FundamentalMetric.REVENUE
        and item.period_end.date().isoformat() == "2024-03-31"
    ]
    assert len(quarterly) == 1
    assert quarterly[0].period_type == FundamentalPeriodType.QUARTERLY
    assert quarterly[0].period_start is not None
    assert quarterly[0].period_start.date().isoformat() == "2024-01-01"
    assert quarterly[0].period_end.date().isoformat() == "2024-03-31"
    assert quarterly[0].fiscal_year == 2024
    assert quarterly[0].fiscal_period == "Q1"
    assert quarterly[0].filed_at is not None
    assert quarterly[0].filed_at.date().isoformat() == "2024-05-10"
    assert all(
        item.period_end.date().isoformat() != "2024-06-30" for item in facts
    )  # the six-month year-to-date value is not presented as one quarter
    capex = next(item for item in facts if item.metric == FundamentalMetric.CAPITAL_EXPENDITURES)
    assert capex.value == Decimal("-31")  # preserve the source sign
    assert capex.source_concept == "PaymentsToAcquirePropertyPlantAndEquipment"
    assert counters["year_to_date_or_unclassified_durations"] == 1
    assert counters["unmapped_standard_concepts"] == 1
    assert issues


def test_companyfacts_normalizer_rejects_provider_specific_custom_concepts_as_domain_facts() -> (
    None
):
    result = normalize_sec_company_facts(record(), COMPANY_ID, CIK)
    assert result.observation is not None
    assert all(item.source_taxonomy in {"us-gaap", "ifrs-full"} for item in result.observation)
    assert all(item.source_concept != "Revenue" for item in result.observation)


def test_provider_requires_exact_cik_mapping_and_uses_the_shared_provider_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_download(url: str, user_agent: str) -> bytes:
        calls.append((url, user_agent))
        return companyfacts_payload()

    async def to_thread(function: Any, *args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr("portfolio_api.reported_fundamentals._download_sec_json", fake_download)
    monkeypatch.setattr("portfolio_api.reported_fundamentals.asyncio.to_thread", to_thread)
    query = ProviderQuery(
        domain=ExternalDataDomain.REPORTED_FUNDAMENTALS,
        subjects=[CanonicalSubjectRef(kind=CanonicalSubjectKind.COMPANY, id=COMPANY_ID)],
        requested_at=OBSERVED_AT,
    )
    provider = SecCompanyFactsProvider({COMPANY_ID: CIK}, "Test application contact@example.com")

    fetched = asyncio.run(provider.fetch(query))
    assert len(fetched) == 1
    assert fetched[0].source_record_id == f"CIK{CIK}"
    assert fetched[0].payload_sha256 == hashlib.sha256(companyfacts_payload()).hexdigest()
    assert calls == [
        (
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json",
            "Test application contact@example.com",
        )
    ]
    assert (
        asyncio.run(SecCompanyFactsProvider({}, "Test app contact@example.com").fetch(query)) == []
    )
    with pytest.raises(ValueError, match="contact email"):
        SecCompanyFactsProvider({COMPANY_ID: CIK}, "anonymous")


def test_sec_company_identity_failure_does_not_discard_other_company_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatched_company_id = UUID("22222222-2222-4222-8222-222222222222")
    mismatched_cik = "0000000002"
    mismatched_record = record().model_copy(update={"source_record_id": f"CIK{mismatched_cik}"})
    provider_records = [record(), mismatched_record]

    def fake_load_mappings(
        _session: Session,
        _company_id: UUID | None,
        _company_ids: Any,
    ) -> dict[UUID, str]:
        return {COMPANY_ID: CIK, mismatched_company_id: mismatched_cik}

    async def fake_fetch(
        _provider: SecCompanyFactsProvider, _query: ProviderQuery
    ) -> list[RawProviderRecord]:
        return provider_records

    def fake_ingest(
        _session: Session, company_id: UUID, _cik: str, _record: RawProviderRecord
    ) -> dict[str, object]:
        if company_id == mismatched_company_id:
            raise ValueError(
                "SEC entity name does not match the recorded provider identity mapping"
            )
        return {"status": "IMPORTED", "reconciliation": {"source_fact_count": 4}}

    monkeypatch.setattr(
        "portfolio_api.reported_fundamentals._load_cik_mappings", fake_load_mappings
    )
    monkeypatch.setattr(SecCompanyFactsProvider, "fetch", fake_fetch)
    monkeypatch.setattr("portfolio_api.reported_fundamentals.ingest_sec_company_facts", fake_ingest)

    results = asyncio.run(
        sync_reported_fundamentals(
            cast(Session, None),
            Settings(_env_file=None, sec_user_agent="Portfolio Research App contact@example.com"),
            company_ids=[COMPANY_ID, mismatched_company_id],
        )
    )

    assert results[0]["status"] == "IMPORTED"
    assert results[1]["status"] == "DATA_CHECK"
    assert results[1]["failure_code"] == "SEC_RECORD_VALIDATION"
    assert results[1]["source_record_id"] == f"CIK{mismatched_cik}"


def _reported_row(
    *,
    value: str,
    provider: str = "sec_edgar",
    source_priority: int = 10,
    concept: str = "RevenueFromContractWithCustomerExcludingAssessedTax",
    mapping_priority: int = 0,
    filed_at: datetime = datetime(2024, 2, 10, tzinfo=UTC),
    recorded_at: datetime = datetime(2024, 2, 11, tzinfo=UTC),
    quality: FundamentalDataQuality = FundamentalDataQuality.PASS,
) -> ReportedFundamentalObservation:
    return ReportedFundamentalObservation(
        id=uuid4(),
        company_id=COMPANY_ID,
        security_id=None,
        batch_id=uuid4(),
        provider_id=provider,
        provider_entity_id=CIK if provider == "sec_edgar" else "vendor-company-1",
        source_priority=source_priority,
        metric=REVENUE,
        statement=FundamentalStatement.INCOME_STATEMENT.value,
        period_type=FundamentalPeriodType.ANNUAL.value,
        period_start=datetime(2023, 1, 1, tzinfo=UTC),
        period_end=datetime(2023, 12, 31, tzinfo=UTC),
        fiscal_year=2023,
        fiscal_period="FY",
        filed_at=filed_at,
        observed_at=recorded_at,
        recorded_at=recorded_at,
        value=Decimal(value),
        currency="USD",
        unit="currency",
        source_taxonomy="us-gaap",
        source_concept=concept,
        source_unit="USD",
        accession_number="0000000001-24-000001",
        form="10-K",
        frame="CY2023",
        source_record_id=f"source:{provider}:{concept}:{filed_at.date()}",
        source_url="https://www.sec.gov/Archives/edgar/data/1/filing-index.html",
        source_ref=f"filing:{provider}:{concept}",
        observation_fingerprint=hashlib.sha256(
            f"{provider}:{concept}:{value}".encode()
        ).hexdigest(),
        mapping_priority=mapping_priority,
        revision_context="ORIGINAL",
        data_quality=quality.value,
        quality_reason=None,
        supersedes_observation_id=None,
    )


def test_fundamental_precedence_selects_primary_but_marks_provider_conflict() -> None:
    primary = _reported_row(value="100")
    secondary = _reported_row(value="101", provider="normalized-vendor", source_priority=50)

    result = resolve_fundamental_period([primary, secondary])

    assert result.selected is primary
    assert result.status == "CONFLICT"
    assert len(result.current_sources) == 2


def test_equally_preferred_primary_conflict_has_no_selected_value() -> None:
    first = _reported_row(value="100", concept="Revenues", mapping_priority=0)
    second = _reported_row(value="101", concept="SalesRevenueNet", mapping_priority=0)

    result = resolve_fundamental_period([first, second])

    assert result.selected is None
    assert result.status == "CONFLICT"


def test_resolver_uses_latest_filing_in_a_lineage_and_preserves_data_check() -> None:
    original = _reported_row(value="100")
    restated = _reported_row(
        value="95",
        filed_at=datetime(2025, 2, 10, tzinfo=UTC),
        recorded_at=datetime(2025, 2, 11, tzinfo=UTC),
        quality=FundamentalDataQuality.DATA_CHECK,
    )

    result = resolve_fundamental_period([original, restated])

    assert result.selected is restated
    assert result.selected.value == Decimal("95")
    assert result.status == "DATA_CHECK"
    assert {item.value for item in [original, restated]} == {Decimal("95"), Decimal("100")}


@pytest.mark.integration
def test_sec_import_allows_documented_name_format_variants_but_checks_exact_cik(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        session.add(Company(id=COMPANY_ID, name="Example canonical issuer"))
        session.flush()
        record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Example Issuer Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )

        equivalent = record(companyfacts_payload(entity_name="Example Issuer, Incorporated"))
        assert (
            ingest_sec_company_facts(session, COMPANY_ID, CIK, equivalent)["status"] == "IMPORTED"
        )

        wrong_cik = record(companyfacts_payload(cik=2))
        with pytest.raises(ValueError, match="payload CIK"):
            ingest_sec_company_facts(session, COMPANY_ID, CIK, wrong_cik)

        different_issuer = record(
            companyfacts_payload(
                entity_name="Example Subsidiary Inc.", accession="0000000001-25-000001"
            )
        )
        with pytest.raises(ValueError, match="issuer name"):
            ingest_sec_company_facts(session, COMPANY_ID, CIK, different_issuer)


@pytest.mark.integration
def test_sec_import_is_repeatable_and_later_filing_appends_a_possible_restatement(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session:
        issuer = Company(id=COMPANY_ID, name="Example canonical issuer", reporting_currency="USD")
        session.add(issuer)
        session.flush()
        record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Example Issuer Inc.",
            "https://www.sec.gov/Archives/edgar/data/1/issuer-index.html",
        )
        initial = record()
        first = ingest_sec_company_facts(session, COMPANY_ID, CIK, initial)
        session.commit()
        first_known_at = now()
        monkeypatch.setattr(
            "portfolio_api.reported_fundamentals.now",
            lambda: first_known_at + timedelta(seconds=1),
        )

        correction_payload = companyfacts_payload(
            annual_revenue=9007199254740994,
            accession="0000000001-25-000001",
            filed="2025-02-10",
        )
        correction_record = record(
            correction_payload,
            observed_at=datetime(2026, 10, 5, 13, tzinfo=UTC),
        )
        second = ingest_sec_company_facts(session, COMPANY_ID, CIK, correction_record)
        session.commit()
        replay = ingest_sec_company_facts(session, COMPANY_ID, CIK, correction_record)
        session.commit()

        assert first["status"] == "IMPORTED"
        assert second["status"] == "IMPORTED"
        assert replay["status"] == "ALREADY_IMPORTED"
        assert (
            session.scalar(
                select(func.count(ReportedFundamentalBatch.id)).where(
                    ReportedFundamentalBatch.normalizer_version == SEC_NORMALIZER_VERSION
                )
            )
            == 2
        )
        revenue_rows = list(
            session.scalars(
                select(ReportedFundamentalObservation).where(
                    ReportedFundamentalObservation.company_id == COMPANY_ID,
                    ReportedFundamentalObservation.metric == REVENUE,
                    ReportedFundamentalObservation.period_end == datetime(2023, 12, 31, tzinfo=UTC),
                )
            )
        )
        assert len(revenue_rows) == 2
        newer = max(revenue_rows, key=lambda item: item.recorded_at)
        older = min(revenue_rows, key=lambda item: item.recorded_at)
        assert newer.value == Decimal("9007199254740994")
        assert newer.supersedes_observation_id == older.id
        assert newer.revision_context == FundamentalRevisionContext.POTENTIAL_RESTATEMENT.value
        assert newer.data_quality == FundamentalDataQuality.DATA_CHECK.value
        assert (
            session.scalar(
                select(func.count(ExternalRawPayload.id)).where(
                    ExternalRawPayload.reported_fundamental_batch_id.is_not(None)
                )
            )
            == 2
        )

        from portfolio_api.domain.queries import company_reported_fundamentals

        point_in_time = company_reported_fundamentals(
            session, COMPANY_ID, period_type="ANNUAL", known_at=first_known_at
        )
        row = next(
            item for item in point_in_time.periods if item.metric == FundamentalMetric.REVENUE
        )
        assert row.value == Decimal("9007199254740993")
        assert len(row.observations) == 1

        original = session.get(ReportedFundamentalObservation, older.id)
        assert original is not None
        original.value = Decimal("1")
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()


@pytest.mark.integration
def test_reported_fundamental_cik_mapping_is_unique_and_source_attributed(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        issuer = Company(id=COMPANY_ID, name="Example canonical issuer", reporting_currency=None)
        session.add(issuer)
        session.flush()
        first = record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Example Issuer Inc.",
            "https://www.sec.gov/Archives/edgar/data/1/issuer-index.html",
        )
        repeated = record_cik_mapping(
            session,
            COMPANY_ID,
            CIK,
            "Example Issuer Inc.",
            "https://www.sec.gov/Archives/edgar/data/1/issuer-index.html",
        )
        assert first.id == repeated.id
        assert first.provider_id == SEC_PROVIDER_ID
        assert first.identifier_value == CIK
        assert first.evidence_source.startswith("https://www.sec.gov/")
        session.commit()
