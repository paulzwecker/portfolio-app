"""Dedicated role authentication for model proposal submission and review routes."""

import hmac
from typing import Literal

from fastapi import HTTPException, Request

from portfolio_api.settings import Settings

ProposalRole = Literal["AGENT", "REVIEWER"]


def _same_token(supplied: str, expected: str | None) -> bool:
    return expected is not None and hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    )


def require_agent(request: Request, supplied: str) -> str:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(503, "Model proposal authentication is not configured.")
    if settings.model_proposal_agent_token is None or not settings.model_proposal_agent_id:
        raise HTTPException(503, "Model proposal agent authentication is not configured.")
    if not _same_token(supplied, settings.model_proposal_agent_token.get_secret_value()):
        raise HTTPException(401, "Model proposal agent authentication required.")
    return settings.model_proposal_agent_id


def require_reviewer(request: Request, supplied: str) -> str:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(503, "Model proposal authentication is not configured.")
    if settings.model_proposal_reviewer_token is None or not settings.model_proposal_reviewer_id:
        raise HTTPException(503, "Model proposal reviewer authentication is not configured.")
    if not _same_token(supplied, settings.model_proposal_reviewer_token.get_secret_value()):
        raise HTTPException(401, "Model proposal reviewer authentication required.")
    return settings.model_proposal_reviewer_id


def require_proposal_reader(request: Request, supplied: str) -> tuple[ProposalRole, str]:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(503, "Model proposal authentication is not configured.")
    if settings.model_proposal_agent_token is not None and _same_token(
        supplied, settings.model_proposal_agent_token.get_secret_value()
    ):
        if not settings.model_proposal_agent_id:
            raise HTTPException(503, "Model proposal agent authentication is not configured.")
        return "AGENT", settings.model_proposal_agent_id
    if settings.model_proposal_reviewer_token is not None and _same_token(
        supplied, settings.model_proposal_reviewer_token.get_secret_value()
    ):
        if not settings.model_proposal_reviewer_id:
            raise HTTPException(503, "Model proposal reviewer authentication is not configured.")
        return "REVIEWER", settings.model_proposal_reviewer_id
    if (
        settings.model_proposal_agent_token is None
        or settings.model_proposal_reviewer_token is None
    ):
        raise HTTPException(503, "Model proposal authentication is not configured.")
    raise HTTPException(401, "Model proposal authentication required.")
