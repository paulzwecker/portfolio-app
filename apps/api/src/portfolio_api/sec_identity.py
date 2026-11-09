"""Conservative recorded SEC identity checks for canonical read views."""

import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from portfolio_api.domain.models import CompanyProviderIdentifier, ReportedFundamentalBatch

SEC_PROVIDER_ID = "sec_edgar"


def reviewed_cik(mapping: CompanyProviderIdentifier) -> str | None:
    """Validate recorded mapping metadata; this does not authenticate SEC evidence."""
    cik = mapping.identifier_value
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        return None
    try:
        url = urlsplit(mapping.evidence_source)
        host = url.hostname.casefold().rstrip(".") if url.hostname else ""
        if (
            mapping.provider_id != SEC_PROVIDER_ID
            or mapping.identifier_type != "SEC_CIK"
            or not mapping.provider_company_name.strip()
            or url.scheme != "https"
            or not (host == "sec.gov" or host.endswith(".sec.gov"))
            or url.username
            or url.password
            or url.port not in {None, 443}
            or re.search(rf"(?<![0-9]){int(cik)}(?![0-9])", f"{url.path}?{url.query}") is None
        ):
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    return cik


def mapping_known_at(
    mapping: CompanyProviderIdentifier, effective_cutoff: datetime | None, known_at: datetime | None
) -> bool:
    return (effective_cutoff is None or mapping.effective_at <= effective_cutoff) and (
        known_at is None or mapping.recorded_at <= known_at
    )


def fact_cik_matches(
    company_id: UUID, cik: str | None, entity_id: str, batch: ReportedFundamentalBatch | None
) -> bool:
    if cik is None or batch is None or batch.provider_id != SEC_PROVIDER_ID:
        return False
    scope = batch.query_scope
    return (
        isinstance(scope, dict)
        and scope.get("company_id") == str(company_id)
        and scope.get("cik") == cik
        and entity_id == cik
    )
