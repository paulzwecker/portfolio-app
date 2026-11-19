"""Least-privilege, opt-in read token for the Data & Universe Steward.

Only GET /v1/companies/{company_id}/agent-context is eligible. This token
never grants general API access or any mutation privileges.
"""

import hmac
import re
from uuid import UUID

from fastapi import HTTPException

from portfolio_api.settings import Settings

_CONTEXT_PATH = re.compile(r"^/v1/companies/([a-fA-F0-9-]{36})/agent-context$")


def authorize_data_universe_read(settings: Settings, *, token: str, method: str, path: str) -> UUID:
    if not settings.data_universe_read_enabled or settings.data_universe_read_token is None:
        raise HTTPException(401, "Data Universe read access is disabled")
    expected = settings.data_universe_read_token.get_secret_value()
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Data Universe read authentication required")
    match = _CONTEXT_PATH.fullmatch(path)
    if method != "GET" or match is None:
        raise HTTPException(403, "Data Universe read credential is limited to company context GET")
    try:
        company_id = UUID(match.group(1))
    except ValueError:
        raise HTTPException(404, "Company context not found") from None
    company_ids = settings.data_universe_read_company_ids or ""
    allowed = {UUID(raw.strip()) for raw in company_ids.split(",") if raw.strip()}
    if company_id not in allowed:
        raise HTTPException(404, "Company context not found")
    return company_id
