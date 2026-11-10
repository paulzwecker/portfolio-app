"""Conservative recorded SEC identity checks for canonical read views."""

import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from portfolio_api.domain.models import CompanyProviderIdentifier, ReportedFundamentalBatch

SEC_PROVIDER_ID = "sec_edgar"


def sec_evidence_matches_cik(cik: str, evidence_source: str) -> bool:
    """Check the URL's SEC identity syntax, without authenticating its contents."""
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        return False
    try:
        url = urlsplit(evidence_source)
        identifiers = [
            value
            for key, value in parse_qsl(url.query, keep_blank_values=True, max_num_fields=200)
            if key.casefold() == "cik"
        ]
        for pattern in (
            r"/(?:archives/)?edgar/data/([0-9]{1,10})(?:/|$)",
            r"/(?:submissions|api/xbrl/companyfacts)/cik([0-9]{10})\.json$",
        ):
            match = re.search(pattern, url.path, re.IGNORECASE)
            if match:
                identifiers.append(match.group(1))
        host = url.hostname.casefold().rstrip(".") if url.hostname else ""
        if (
            url.scheme != "https"
            or not (host == "sec.gov" or host.endswith(".sec.gov"))
            or url.username
            or url.password
            or url.port not in {None, 443}
            or not identifiers
            or any(
                not re.fullmatch(r"[0-9]{1,10}", value) or int(value) != int(cik)
                for value in identifiers
            )
        ):
            return False
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def reviewed_cik(mapping: CompanyProviderIdentifier) -> str | None:
    """Validate recorded mapping metadata; this does not authenticate SEC evidence."""
    try:
        if (
            mapping.provider_id != SEC_PROVIDER_ID
            or mapping.identifier_type != "SEC_CIK"
            or not mapping.provider_company_name.strip()
            or not sec_evidence_matches_cik(mapping.identifier_value, mapping.evidence_source)
        ):
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    return mapping.identifier_value


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
