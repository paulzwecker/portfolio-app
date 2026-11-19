"""Scoped credentials for observation proposals (never general API or model-proposal access)."""

import hmac
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import SecretStr

from portfolio_api.settings import Settings

Role = Literal["AGENT", "REVIEWER"]


def _role(request: Request, supplied: str) -> tuple[Role, str]:
    settings = request.app.state.settings
    if not isinstance(settings, Settings) or not settings.observation_proposals_enabled:
        raise HTTPException(503, "Observation proposal workflow is disabled.")
    if (
        request.method != "GET"
        and (
            settings.app_env == "production" or settings.database_target_environment == "production"
        )
        and not settings.database_production_writes_authorized
    ):
        raise HTTPException(
            403, "Production observation proposal writes require owner authorization."
        )
    roles: tuple[tuple[Role, SecretStr | None, str | None], ...] = (
        (
            "AGENT",
            settings.observation_proposal_agent_token,
            settings.observation_proposal_agent_id,
        ),
        (
            "REVIEWER",
            settings.observation_proposal_reviewer_token,
            settings.observation_proposal_reviewer_id,
        ),
    )
    for role, token, identity in roles:
        if (
            token is not None
            and identity is not None
            and hmac.compare_digest(
                supplied.encode("utf-8"), token.get_secret_value().encode("utf-8")
            )
        ):
            return role, identity
    if any(token is None or identity is None for _, token, identity in roles):
        raise HTTPException(503, "Observation proposal role credentials are not configured.")
    raise HTTPException(401, "Observation proposal role authentication required.")


def require_agent(request: Request, supplied: str) -> str:
    role, actor = _role(request, supplied)
    if role != "AGENT":
        raise HTTPException(401, "Observation agent role required.")
    return actor


def require_reviewer(request: Request, supplied: str) -> str:
    role, actor = _role(request, supplied)
    if role != "REVIEWER":
        raise HTTPException(401, "Observation reviewer role required.")
    return actor


def require_reader(request: Request, supplied: str) -> tuple[Role, str]:
    return _role(request, supplied)


def require_acceptance(request: Request, supplied: str) -> str:
    reviewer = require_reviewer(request, supplied)
    settings = request.app.state.settings
    if not settings.observation_acceptance_enabled:
        raise HTTPException(403, "Canonical observation acceptance is disabled.")
    return reviewer
