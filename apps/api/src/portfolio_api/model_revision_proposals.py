"""Review-gated agent proposals that reuse canonical model calculation services."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries, services
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    AgentModelRevisionProposal,
    FinancialModel,
    FinancialModelRevision,
    FinancialModelType,
    Listing,
    Security,
)
from portfolio_api.model_revision_evidence import persist_model_revision_evidence


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _proposal_read(
    session: Session, item: AgentModelRevisionProposal
) -> s.ModelRevisionProposalRead:
    conflicts = list(
        session.scalars(
            select(AgentModelRevisionProposal.id)
            .where(
                AgentModelRevisionProposal.model_id == item.model_id,
                AgentModelRevisionProposal.base_revision_id == item.base_revision_id,
                AgentModelRevisionProposal.id != item.id,
                AgentModelRevisionProposal.status.in_(("PENDING", "READY", "CONFLICT", "INVALID")),
            )
            .order_by(AgentModelRevisionProposal.submitted_at, AgentModelRevisionProposal.id)
        )
    )
    return s.ModelRevisionProposalRead(
        id=item.id,
        producer_id=item.producer_id,
        proposal=s.FinancialModelRevisionProposalV1.model_validate(item.proposal_data),
        content_fingerprint=item.content_fingerprint,
        status=cast(s.ModelRevisionProposalStatus, item.status),
        issue=item.issue,
        conflicting_proposal_ids=conflicts,
        accepted_revision_id=item.accepted_revision_id,
        reviewer_id=item.reviewer_id,
        decision_note=item.decision_note,
        submitted_at=item.submitted_at,
        reviewed_at=item.reviewed_at,
    )


def _validate_identity(
    session: Session,
    item: s.FinancialModelRevisionProposalV1,
    model: FinancialModel,
) -> FinancialModelRevision:
    current = session.get(FinancialModelRevision, model.current_revision_id)
    if current is None or current.model_id != model.id:
        raise services.DomainError("Current model revision is unavailable", 409)
    if (
        item.model_id != model.id
        or item.company_id != model.company_id
        or item.valuation_listing_id != model.valuation_listing_id
        or item.model_currency != model.model_currency
        or item.method.methodology != model.model_type
    ):
        raise services.DomainError(
            "Proposal company, listing, currency or methodology does not match the canonical model",
            409,
        )
    if isinstance(item.method, s.AgentUfcfDcfProposalMethod):
        proposed_methodology_version = (
            "ufcf-dcf-explicit-tail-v1"
            if any(
                scenario.tail_ufcf_growth is not None for scenario in item.method.inputs.scenarios
            )
            else "ufcf-dcf-fade-v1"
        )
    elif isinstance(item.method, s.AgentOwnerCashFlowProposalMethod):
        proposed_methodology_version = "owner-cash-flow-10y-v1"
    else:
        proposed_methodology_version = "residual-income-10y-fade-v1"
    if item.methodology_version != current.methodology_version or (
        item.methodology_version != proposed_methodology_version
    ):
        raise services.DomainError(
            "Proposal methodology version does not match the accepted revision "
            "and submitted inputs",
            409,
        )
    base = session.get(FinancialModelRevision, item.base_revision_id)
    if (
        base is None
        or base.model_id != model.id
        or base.revision_number != item.base_revision_number
    ):
        raise services.DomainError("The referenced base revision is invalid", 409)
    provenance = s.FinancialModelProposalProvenance(
        author_id="proposal-validation",
        authored_at=item.authored_at,
        source_reference=item.source_reference,
    )
    services._validate_model_proposal_evidence(
        session,
        model,
        "2.1.0",
        provenance,
        item.supporting_evidence,
    )
    return current


def submit_model_revision_proposal(
    session: Session,
    item: s.FinancialModelRevisionProposalV1,
    *,
    producer_id: str,
) -> s.ModelRevisionProposalSubmissionRead:
    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == item.model_id).with_for_update()
    )
    if model is None:
        raise services.DomainError("Financial model not found", 404)
    proposal_data = item.model_dump(mode="json")
    fingerprint = _hash_json({"producer_id": producer_id, "proposal": proposal_data})
    existing = session.scalar(
        select(AgentModelRevisionProposal).where(
            AgentModelRevisionProposal.model_id == item.model_id,
            AgentModelRevisionProposal.producer_id == producer_id,
            AgentModelRevisionProposal.external_revision_id == item.external_revision_id,
        )
    )
    if existing is not None:
        if existing.content_fingerprint != fingerprint:
            raise services.DomainError(
                "This external revision ID was already submitted with different content", 409
            )
        return s.ModelRevisionProposalSubmissionRead(
            proposal=_proposal_read(session, existing), replayed=True
        )

    current = _validate_identity(session, item, model)
    status = "PENDING"
    issue = None
    if item.base_revision_id != current.id or item.base_revision_number != current.revision_number:
        status = "CONFLICT"
        issue = "The proposal base is no longer the current accepted revision."

    conflicts = list(
        session.scalars(
            select(AgentModelRevisionProposal.id).where(
                AgentModelRevisionProposal.model_id == model.id,
                AgentModelRevisionProposal.base_revision_id == item.base_revision_id,
                AgentModelRevisionProposal.status.in_(("PENDING", "READY", "CONFLICT")),
            )
        )
    )
    candidate = AgentModelRevisionProposal(
        model_id=model.id,
        company_id=model.company_id,
        producer_id=producer_id,
        author_id=producer_id,
        external_revision_id=item.external_revision_id,
        base_revision_id=item.base_revision_id,
        base_revision_number=item.base_revision_number,
        valuation_listing_id=item.valuation_listing_id,
        model_type=item.method.methodology,
        methodology_version=item.methodology_version,
        model_currency=item.model_currency,
        authored_at=item.authored_at,
        effective_at=item.effective_at,
        source_reference=item.source_reference,
        rationale=item.rationale,
        proposal_data=proposal_data,
        supporting_evidence=[e.model_dump(mode="json") for e in item.supporting_evidence],
        content_fingerprint=fingerprint,
        status=status,
        issue=issue,
        conflicting_proposal_ids=[str(value) for value in conflicts],
    )
    session.add(candidate)
    session.flush()
    for conflict_id in conflicts:
        prior = session.get(AgentModelRevisionProposal, conflict_id)
        if prior is not None:
            prior.conflicting_proposal_ids = sorted(
                set(prior.conflicting_proposal_ids + [str(candidate.id)])
            )
    return s.ModelRevisionProposalSubmissionRead(
        proposal=_proposal_read(session, candidate), replayed=False
    )


def _inputs_read(
    read: s.FinancialModelRead | s.ExtendedFinancialModelRead,
) -> s.DcfCalculationInput | s.OwnerCashFlowInput | s.ResidualIncomeInput:
    if isinstance(read, s.FinancialModelRead):
        revision = read.current_revision
        scenarios = []
        for scenario in revision.scenarios:
            scenario_data = scenario.model_dump(mode="json", exclude={"id", "revision_id"})
            scenario_data["years"] = [
                year.model_dump(mode="json", exclude={"id", "scenario_id"})
                for year in scenario.years
            ]
            if scenario.tail_ufcf_growth is not None:
                scenario_data["tail_ufcf_growth"] = [
                    tail.model_dump(mode="json", exclude={"id", "scenario_id"})
                    for tail in scenario.tail_ufcf_growth
                ]
            scenarios.append(scenario_data)
        return s.DcfCalculationInput.model_validate(
            {"base": revision.base.model_dump(mode="json"), "scenarios": scenarios}
        )
    extended_revision = read.current_revision
    if isinstance(extended_revision, s.OwnerCashFlowRevisionRead):
        return s.OwnerCashFlowInput(
            base=extended_revision.base, scenarios=extended_revision.scenarios
        )
    if isinstance(extended_revision, s.ResidualIncomeRevisionRead):
        return s.ResidualIncomeInput(
            base=extended_revision.base, scenarios=extended_revision.scenarios
        )
    raise services.DomainError("Canonical model methodology is unsupported", 409)


def _without_revision_ids(value: dict[str, object]) -> dict[str, object]:
    return {
        key: item for key, item in value.items() if key not in {"id", "revision_id", "scenario_id"}
    }


def _canonical_projection_rows(
    rows: list[dict[str, object]], *, scenario_by_id: dict[str, str] | None = None
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        value = dict(row)
        if "scenario" not in value and scenario_by_id is not None:
            scenario_id = value.get("scenario_id")
            if scenario_id is not None:
                value["scenario"] = scenario_by_id.get(str(scenario_id))
        normalized.append(_without_revision_ids(value))

    def order(row: dict[str, object]) -> tuple[str, int]:
        year = row.get("forecast_year")
        return str(row.get("scenario", "")), year if isinstance(year, int) else 0

    return sorted(normalized, key=order)


def _refresh_preview(
    session: Session,
    candidate: AgentModelRevisionProposal,
) -> s.ModelRevisionProposalPreviewRead:
    proposal = s.FinancialModelRevisionProposalV1.model_validate(candidate.proposal_data)
    model = session.get(FinancialModel, candidate.model_id)
    if model is None:
        raise services.DomainError("Financial model not found", 404)
    read: s.FinancialModelRead | s.ExtendedFinancialModelRead
    if model.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        read = queries.financial_model(session, model.id)
    else:
        read = queries.extended_financial_model(session, model.id)
    current_inputs = _inputs_read(read)
    proposed_inputs = proposal.method.inputs
    current_inputs_json = current_inputs.model_dump(mode="json")
    proposed_inputs_json = proposed_inputs.model_dump(mode="json")
    input_changes = [
        s.ModelRevisionProposalDiff(
            field=change.path, before=change.previous, after=change.proposed
        )
        for change in services._additional_input_changes(current_inputs_json, proposed_inputs_json)
    ]
    proposed_calculation: (
        s.FinancialModelCalculationPreviewRead
        | s.OwnerCashFlowCalculationPreviewRead
        | s.ResidualIncomeCalculationPreviewRead
        | None
    ) = None
    current_revision = read.current_revision
    current_outputs = _without_revision_ids(current_revision.outputs.model_dump(mode="json"))
    scenario_by_id = None
    if isinstance(read, s.FinancialModelRead):
        scenario_by_id = {
            str(scenario.id): str(scenario.scenario.value)
            for scenario in read.current_revision.scenarios
        }
    current_projections = _canonical_projection_rows(
        [projection.model_dump(mode="json") for projection in current_revision.projections],
        scenario_by_id=scenario_by_id,
    )
    status: Literal["READY", "CONFLICT", "INVALID"] = "READY"
    reason = None
    if (
        model.current_revision_id != proposal.base_revision_id
        or current_revision.revision_number != proposal.base_revision_number
    ):
        status = "CONFLICT"
        reason = "The accepted model advanced after this proposal was submitted."
    else:
        try:
            if isinstance(proposal.method, s.AgentUfcfDcfProposalMethod):
                proposed_calculation = services.preview_financial_model_revision_calculation(
                    session,
                    model.id,
                    s.FinancialModelRevisionCalculationPreviewCreate(
                        **proposed_inputs.model_dump(),
                        base_revision_id=proposal.base_revision_id,
                    ),
                )
            elif isinstance(proposal.method, s.AgentOwnerCashFlowProposalMethod):
                proposed_calculation = services.preview_owner_cash_flow_revision(
                    session,
                    model.id,
                    s.OwnerCashFlowRevisionPreviewCreate(
                        **proposed_inputs.model_dump(),
                        base_revision_id=proposal.base_revision_id,
                    ),
                )
            else:
                proposed_calculation = services.preview_residual_income_revision(
                    session,
                    model.id,
                    s.ResidualIncomeRevisionPreviewCreate(
                        **proposed_inputs.model_dump(),
                        base_revision_id=proposal.base_revision_id,
                    ),
                )
        except services.DomainError as error:
            status = "CONFLICT" if error.status == 409 else "INVALID"
            reason = error.detail

    proposed_outputs: dict[str, object] | None = None
    proposed_projections: list[dict[str, object]] = []
    output_changes: list[s.ModelRevisionProposalDiff] = []
    if proposed_calculation is not None:
        proposed_outputs = _without_revision_ids(
            proposed_calculation.outputs.model_dump(mode="json")
        )
        proposed_projections = _canonical_projection_rows(
            [projection.model_dump(mode="json") for projection in proposed_calculation.projections]
        )
        output_changes = [
            s.ModelRevisionProposalDiff(
                field=change.path, before=change.previous, after=change.proposed
            )
            for change in services._additional_input_changes(current_outputs, proposed_outputs)
        ]

    fingerprint_payload = {
        "proposal_id": str(candidate.id),
        "current_revision_id": str(read.current_revision_id),
        "current_revision_number": current_revision.revision_number,
        "status": status,
        "reason": reason,
        "current_inputs": current_inputs_json,
        "proposed_inputs": proposed_inputs_json,
        "current_outputs": current_outputs,
        "proposed_outputs": proposed_outputs,
        "current_projections": current_projections,
        "proposed_projections": proposed_projections,
        "input_changes": [change.model_dump(mode="json") for change in input_changes],
        "output_changes": [change.model_dump(mode="json") for change in output_changes],
    }
    fingerprint = _hash_json(fingerprint_payload) if status == "READY" else None
    previewed_at = datetime.now(UTC)
    result = s.ModelRevisionProposalPreviewRead(
        proposal_id=candidate.id,
        status=status,
        reason=reason,
        current_revision_id=read.current_revision_id,
        current_revision_number=current_revision.revision_number,
        input_changes=input_changes,
        output_changes=output_changes,
        current_inputs=current_inputs_json,
        proposed_inputs=proposed_inputs_json,
        current_outputs=current_outputs,
        proposed_outputs=proposed_outputs,
        proposed_projections=proposed_projections,
        preview_fingerprint=fingerprint,
        previewed_at=previewed_at,
    )
    candidate.status = status
    candidate.issue = reason
    candidate.preview_data = result.model_dump(mode="json")
    candidate.preview_fingerprint = fingerprint
    candidate.previewed_at = previewed_at
    return result


def preview_model_revision_proposal(
    session: Session, proposal_id: UUID
) -> s.ModelRevisionProposalPreviewRead:
    candidate = session.scalar(
        select(AgentModelRevisionProposal)
        .where(AgentModelRevisionProposal.id == proposal_id)
        .with_for_update()
    )
    if candidate is None:
        raise services.DomainError("Model proposal not found", 404)
    if candidate.status in {"ACCEPTED", "REJECTED"}:
        raise services.DomainError("Final model proposal decisions cannot be previewed", 409)
    return _refresh_preview(session, candidate)


def _accepted_source_revision(candidate: AgentModelRevisionProposal) -> str:
    return f"agent-proposal:{candidate.id}"


def _accept_candidate(
    session: Session,
    candidate: AgentModelRevisionProposal,
    reviewer_id: str,
    decision_note: str,
) -> FinancialModelRevision:
    proposal = s.FinancialModelRevisionProposalV1.model_validate(candidate.proposal_data)
    model = session.scalar(
        select(FinancialModel).where(FinancialModel.id == candidate.model_id).with_for_update()
    )
    if model is None:
        raise services.DomainError("Financial model not found", 404)
    _validate_identity(session, proposal, model)
    common = {
        "base_revision_id": proposal.base_revision_id,
        "source_revision_id": _accepted_source_revision(candidate),
        "actor": "IMPORT",
        "source": f"Agent-authored proposal: {candidate.producer_id}",
        "rationale": proposal.rationale,
        "effective_at": proposal.effective_at,
    }
    provenance = s.FinancialModelProposalProvenance(
        author_id=candidate.author_id,
        authored_at=proposal.authored_at,
        source_reference=proposal.source_reference,
    )
    if isinstance(proposal.method, s.AgentUfcfDcfProposalMethod):
        dcf_revision_input = s.FinancialModelRevisionCreate.model_validate(
            {**proposal.method.inputs.model_dump(), **common}
        )
        revision = services._append_dcf_revision(
            session,
            model,
            dcf_revision_input,
            contract_digest=candidate.content_fingerprint,
            proposal=provenance,
        )
    elif isinstance(proposal.method, s.AgentOwnerCashFlowProposalMethod):
        owner_revision_input = s.OwnerCashFlowRevisionCreate.model_validate(
            {**proposal.method.inputs.model_dump(), **common}
        )
        revision = services._append_archetype_revision(
            session,
            model,
            owner_revision_input,
            FinancialModelType.OWNER_CASH_FLOW_10Y,
            contract_digest=candidate.content_fingerprint,
            proposal=provenance,
        )
    else:
        residual_revision_input = s.ResidualIncomeRevisionCreate.model_validate(
            {**proposal.method.inputs.model_dump(), **common}
        )
        revision = services._append_archetype_revision(
            session,
            model,
            residual_revision_input,
            FinancialModelType.RESIDUAL_INCOME_10Y_FADE,
            contract_digest=candidate.content_fingerprint,
            proposal=provenance,
        )
    listing = session.get(Listing, model.valuation_listing_id)
    security = session.get(Security, listing.security_id) if listing else None
    if security is None:
        raise services.DomainError("Model listing identity is unavailable", 409)
    persist_model_revision_evidence(
        session,
        revision_id=revision.id,
        company_id=model.company_id,
        security_id=security.id,
        references=proposal.supporting_evidence,
    )
    session.flush()

    # The existing append services calculate again while persisting. Abort the whole
    # transaction if market inputs changed after the reviewed preview was produced.
    accepted_read: s.FinancialModelRead | s.ExtendedFinancialModelRead
    if model.model_type == FinancialModelType.UFCF_DCF_10Y_FADE:
        accepted_read = queries.financial_model(session, model.id)
    else:
        accepted_read = queries.extended_financial_model(session, model.id)
    accepted_revision = accepted_read.current_revision
    accepted_outputs = _without_revision_ids(accepted_revision.outputs.model_dump(mode="json"))
    scenario_by_id = None
    if isinstance(accepted_read, s.FinancialModelRead):
        scenario_by_id = {
            str(scenario.id): str(scenario.scenario.value)
            for scenario in accepted_read.current_revision.scenarios
        }
    accepted_projections = _canonical_projection_rows(
        [projection.model_dump(mode="json") for projection in accepted_revision.projections],
        scenario_by_id=scenario_by_id,
    )
    reviewed = candidate.preview_data or {}
    if accepted_outputs != reviewed.get("proposed_outputs") or accepted_projections != reviewed.get(
        "proposed_projections"
    ):
        raise services.DomainError(
            "Calculated market or model inputs changed during acceptance; preview again",
            409,
        )
    candidate.status = "ACCEPTED"
    candidate.accepted_revision_id = revision.id
    candidate.reviewer_id = reviewer_id
    candidate.decision_note = decision_note
    candidate.reviewed_at = datetime.now(UTC)
    candidate.issue = None
    session.flush()
    return revision


def accept_model_revision_proposal(
    session: Session,
    proposal_id: UUID,
    request: s.ModelRevisionProposalDecisionRequest,
    *,
    reviewer_id: str,
) -> s.ModelRevisionProposalDecisionRead:
    candidate = session.scalar(
        select(AgentModelRevisionProposal)
        .where(AgentModelRevisionProposal.id == proposal_id)
        .with_for_update()
    )
    if candidate is None:
        raise services.DomainError("Model proposal not found", 404)
    if candidate.status == "ACCEPTED" and candidate.accepted_revision_id is not None:
        return s.ModelRevisionProposalDecisionRead(
            status="ACCEPTED",
            proposal=_proposal_read(session, candidate),
            accepted_revision_id=candidate.accepted_revision_id,
        )
    if candidate.status in {"REJECTED", "CONFLICT", "INVALID"}:
        return s.ModelRevisionProposalDecisionRead(
            status=cast(
                Literal["ACCEPTED", "REJECTED", "PREVIEW_CHANGED", "CONFLICT", "INVALID"],
                candidate.status,
            ),
            proposal=_proposal_read(session, candidate),
        )
    if (
        candidate.status != "READY"
        or candidate.preview_fingerprint is None
        or candidate.preview_fingerprint != request.preview_fingerprint
    ):
        raise services.DomainError(
            "A current reviewer preview is required before accepting this proposal", 409
        )
    preview = _refresh_preview(session, candidate)
    if preview.status != "READY":
        return s.ModelRevisionProposalDecisionRead(
            status=preview.status,
            proposal=_proposal_read(session, candidate),
            preview=preview,
        )
    if preview.preview_fingerprint != request.preview_fingerprint:
        return s.ModelRevisionProposalDecisionRead(
            status="PREVIEW_CHANGED",
            proposal=_proposal_read(session, candidate),
            preview=preview,
        )
    revision = _accept_candidate(session, candidate, reviewer_id, request.decision_note)
    return s.ModelRevisionProposalDecisionRead(
        status="ACCEPTED",
        proposal=_proposal_read(session, candidate),
        accepted_revision_id=revision.id,
    )


def reject_model_revision_proposal(
    session: Session,
    proposal_id: UUID,
    decision_note: str,
    *,
    reviewer_id: str,
) -> s.ModelRevisionProposalDecisionRead:
    candidate = session.scalar(
        select(AgentModelRevisionProposal)
        .where(AgentModelRevisionProposal.id == proposal_id)
        .with_for_update()
    )
    if candidate is None:
        raise services.DomainError("Model proposal not found", 404)
    if candidate.status == "REJECTED":
        return s.ModelRevisionProposalDecisionRead(
            status="REJECTED", proposal=_proposal_read(session, candidate)
        )
    if candidate.status == "ACCEPTED":
        raise services.DomainError("An accepted model proposal cannot be rejected", 409)
    candidate.status = "REJECTED"
    candidate.reviewer_id = reviewer_id
    candidate.decision_note = decision_note
    candidate.reviewed_at = datetime.now(UTC)
    candidate.issue = None
    session.flush()
    return s.ModelRevisionProposalDecisionRead(
        status="REJECTED", proposal=_proposal_read(session, candidate)
    )


def get_model_revision_proposal(session: Session, proposal_id: UUID) -> s.ModelRevisionProposalRead:
    item = session.get(AgentModelRevisionProposal, proposal_id)
    if item is None:
        raise services.DomainError("Model proposal not found", 404)
    return _proposal_read(session, item)


def list_model_revision_proposals(
    session: Session,
    *,
    status: str | None = None,
    company_id: UUID | None = None,
    limit: int = 50,
) -> list[s.ModelRevisionProposalRead]:
    statement = select(AgentModelRevisionProposal).order_by(
        AgentModelRevisionProposal.submitted_at.desc(), AgentModelRevisionProposal.id
    )
    if status is not None:
        statement = statement.where(AgentModelRevisionProposal.status == status)
    if company_id is not None:
        statement = statement.where(AgentModelRevisionProposal.company_id == company_id)
    items = list(session.scalars(statement.limit(limit)))
    return [_proposal_read(session, item) for item in items]
