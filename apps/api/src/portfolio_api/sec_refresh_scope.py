"""Frozen issuer selection for bounded SEC refreshes through existing ingestion runs."""

import hashlib
import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import Company, Portfolio
from portfolio_api.fundamentals_bootstrap import (
    FundamentalsBootstrapError,
    _current_lifecycle,
    _load_reviewed_cik_mappings,
    _portfolio_research_selection,
)
from portfolio_api.source_documents import SEC_DOCUMENT_NORMALIZER_VERSION

SEC_SCOPE_VERSION = "sec-issuer-refresh-v2"
LEGACY_SEC_SCOPE_VERSION = "sec-issuer-refresh-v1"
MAX_SEC_ISSUERS = 30
MAX_SEC_HISTORY_FILES = 5


class SecRefreshScopeError(ValueError):
    """A frozen SEC refresh cannot safely reach its provider."""


def _mapping_values(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "lifecycle"} for item in items]


def _mapping_hash(items: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(_mapping_values(items), sort_keys=True).encode()).hexdigest()


def capture_sec_refresh_scope(
    session: Session,
    *,
    company_ids: set[UUID] | None,
    run_date: date,
    request_id: UUID | None,
) -> dict[str, Any] | None:
    selection: dict[str, Any]
    try:
        if company_ids is not None:
            companies = session.scalars(
                select(Company).where(Company.id.in_(company_ids)).order_by(Company.id)
            ).all()
            if len(companies) != len(company_ids):
                raise SecRefreshScopeError("The requested canonical SEC issuer was not found.")
            lifecycle = _current_lifecycle(session)
            selection = {
                "kind": "explicit-companies",
                "companies": [
                    {
                        "company_id": str(item.id),
                        "company_name": item.name,
                        "lifecycle": lifecycle.get(item.id),
                        "selection_basis": ["EXPLICIT_REQUEST"],
                    }
                    for item in companies
                ],
            }
        else:
            portfolios = list(session.scalars(select(Portfolio.id).limit(2)))
            if not portfolios:
                # Preserve the legacy lifecycle-only universe before portfolio bootstrap.
                return None
            if len(portfolios) != 1:
                raise SecRefreshScopeError(
                    "Scheduled SEC refresh requires one explicit portfolio scope."
                )
            selection = _portfolio_research_selection(session, portfolios[0])
        ordered_ids = [item["company_id"] for item in selection["companies"]]
        current = {str(item.company_id): item for item in _load_reviewed_cik_mappings(session)}
        mappings = [current[item].manifest() for item in ordered_ids if item in current]
    except FundamentalsBootstrapError as error:
        raise SecRefreshScopeError(str(error)) from None
    if len(mappings) > MAX_SEC_ISSUERS:
        raise SecRefreshScopeError(
            "SEC refresh exceeds the 30 mapped-issuer budget. Review a narrower scope."
        )
    return {
        "scope": "sec_issuer_refresh",
        "sec_scope_version": SEC_SCOPE_VERSION,
        "source_document_normalizer_version": SEC_DOCUMENT_NORMALIZER_VERSION,
        "scope_date": run_date.isoformat(),
        "operational_request_id": str(request_id) if request_id else None,
        "company_ids": ordered_ids,
        "company_states": [
            {"company_id": item["company_id"], "lifecycle": item["lifecycle"]}
            for item in selection["companies"]
        ],
        "selection": selection,
        "verified_cik_mappings": mappings,
        "mapping_sha256": _mapping_hash(mappings),
        "max_mapped_issuers": MAX_SEC_ISSUERS,
        "max_new_history_files": MAX_SEC_HISTORY_FILES,
    }


def validate_sec_refresh_scope(session: Session, scope: dict[str, Any]) -> list[UUID]:
    try:
        raw_ids = scope["company_ids"]
        mappings = scope["verified_cik_mappings"]
        if (
            scope["scope"] != "sec_issuer_refresh"
            or scope["sec_scope_version"] != SEC_SCOPE_VERSION
            or scope["source_document_normalizer_version"] != SEC_DOCUMENT_NORMALIZER_VERSION
            or scope["max_mapped_issuers"] != MAX_SEC_ISSUERS
            or scope["max_new_history_files"] != MAX_SEC_HISTORY_FILES
            or not isinstance(raw_ids, list)
            or not all(isinstance(item, str) for item in raw_ids)
            or len(set(raw_ids)) != len(raw_ids)
            or not isinstance(mappings, list)
            or len(mappings) > MAX_SEC_ISSUERS
            or not all(isinstance(item, dict) for item in mappings)
        ):
            raise SecRefreshScopeError("The frozen SEC scope is malformed or exceeds its budget.")
        ordered = [UUID(item) for item in raw_ids]
        if [item["company_id"] for item in scope["selection"]["companies"]] != raw_ids:
            raise SecRefreshScopeError("The frozen SEC selection differs from its issuer scope.")
        if any(item["company_id"] not in raw_ids for item in mappings) or len(
            {item["company_id"] for item in mappings}
        ) != len(mappings):
            raise SecRefreshScopeError("The frozen SEC mapping set differs from its issuer scope.")
        if _mapping_hash(mappings) != scope["mapping_sha256"]:
            raise SecRefreshScopeError("The frozen SEC mapping fingerprint changed.")
        current = {
            str(item.mapping_id): item.manifest() for item in _load_reviewed_cik_mappings(session)
        }
        live = [current[item["mapping_identifier_id"]] for item in mappings]
        if _mapping_values(live) != _mapping_values(mappings):
            raise SecRefreshScopeError("A reviewed SEC identity changed after scope capture.")
    except (KeyError, TypeError, ValueError, FundamentalsBootstrapError) as error:
        if isinstance(error, SecRefreshScopeError):
            raise
        raise SecRefreshScopeError(
            "The frozen SEC scope or reviewed issuer mapping is invalid."
        ) from None
    return ordered
