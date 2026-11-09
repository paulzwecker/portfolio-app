"""Issuer metadata is a conservative boundary, not source authentication."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from portfolio_api.domain.models import CompanyProviderIdentifier, ReportedFundamentalBatch
from portfolio_api.sec_identity import fact_cik_matches, mapping_known_at, reviewed_cik


def test_mapping_requires_canonical_cik_and_public_evidence() -> None:
    mapping = CompanyProviderIdentifier(
        provider_id="sec_edgar",
        identifier_type="SEC_CIK",
        identifier_value="0000000001",
        provider_company_name="Issuer",
        evidence_source="https://www.sec.gov/edgar/?CIK=1",
        effective_at=datetime(2020, 1, 1, tzinfo=UTC),
        recorded_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    assert reviewed_cik(mapping) == "0000000001"
    assert mapping_known_at(mapping, datetime(2020, 1, 1, tzinfo=UTC), None)
    assert not mapping_known_at(mapping, datetime(2019, 12, 31, tzinfo=UTC), None)
    assert not mapping_known_at(mapping, None, datetime(2020, 1, 1, tzinfo=UTC))
    for url in (
        "https://user:pass@sec.gov/?CIK=1",
        "https://sec.gov:444/?CIK=1",
        "https://not-sec.gov/?CIK=1",
        "https://sec.gov/?CIK=2",
    ):
        mapping.evidence_source = url
        assert reviewed_cik(mapping) is None
    mapping.evidence_source = "https://sec.gov/?CIK=1"
    mapping.identifier_value = "١٢٣٤٥٦٧٨٩٠"
    assert reviewed_cik(mapping) is None


@pytest.mark.parametrize(
    "scope,provider,expected",
    [
        ("valid", "sec_edgar", True),
        ("wrong_company", "sec_edgar", False),
        ("wrong_cik", "sec_edgar", False),
        ("malformed", "sec_edgar", False),
        ("valid", "other", False),
    ],
)
def test_fact_identity_requires_matching_batch_metadata(
    scope: str, provider: str, expected: bool
) -> None:
    company = uuid4()
    values = {"company_id": str(company), "cik": "0000000001"}
    if scope == "wrong_company":
        values["company_id"] = str(uuid4())
    elif scope == "wrong_cik":
        values["cik"] = "0000000002"
    elif scope == "malformed":
        values = {}
    batch = ReportedFundamentalBatch(provider_id=provider, query_scope=values)
    assert fact_cik_matches(company, "0000000001", "0000000001", batch) is expected
    assert not fact_cik_matches(company, None, "0000000001", batch)
    assert not fact_cik_matches(company, "0000000001", "0000000001", None)
