"""Canonical, auditable Watchlist Rank calculation.

The documented rank is an ordinal Expected IRR sort, not a composite. Native and
legacy normalized return semantics are kept in separate run cohorts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelMigrationAssessment,
    FinancialModelOutput,
    FinancialModelRevision,
    Listing,
    ModelOutputSnapshot,
    ModelOutputSnapshotKind,
    PriceObservation,
    RankingEntryStatus,
    ScoreAssessment,
    ScoreDefinition,
    ScoreDefinitionStatus,
    ScoreDimension,
    Security,
)
from portfolio_api.market_data import FRESH_DAYS

NATIVE_RETURN_SEMANTICS = "NATIVE_METHOD_OUTPUT"
LEGACY_RETURN_SEMANTICS = "LEGACY_NORMALIZED_FIELD"
RANK_CONTEXT_VERSION = "watchlist-rank-inputs-v1"


@dataclass(frozen=True)
class RankCandidate:
    semantics: str
    ticker: str
    value: Decimal
    input_snapshot: dict[str, Any]


def expected_irr_positions(
    rows: list[tuple[UUID, str, Decimal]],
) -> dict[UUID, int]:
    """Apply the workbook's exact descending-value / ascending-ticker ordinal rule."""
    ordered = sorted(rows, key=lambda row: (-row[2], row[1]))
    return {
        company_id: position for position, (company_id, _ticker, _value) in enumerate(ordered, 1)
    }


def build_watchlist_rank_entries(
    session: Session,
    companies: list[Company],
    lifecycle_by_company: dict[UUID, str],
    as_of: datetime,
) -> list[tuple[UUID, RankingEntryStatus, str, int | None, dict[str, Any] | None]]:
    """Snapshot current supported inputs and rank only one comparable IRR cohort."""
    company_ids = {company.id for company in companies}
    if not company_ids:
        return []
    as_of = as_of.astimezone(UTC)

    score_contexts = _score_contexts(session, company_ids, as_of)
    native_models = list(
        session.scalars(
            select(FinancialModel)
            .where(
                FinancialModel.company_id.in_(company_ids),
                FinancialModel.created_at <= as_of,
            )
            .order_by(FinancialModel.company_id, FinancialModel.model_name, FinancialModel.id)
        )
    )
    models_by_company: dict[UUID, list[FinancialModel]] = defaultdict(list)
    models_by_id = {model.id: model for model in native_models}
    for model in native_models:
        models_by_company[model.company_id].append(model)

    revisions = (
        list(
            session.scalars(
                select(FinancialModelRevision)
                .where(
                    FinancialModelRevision.model_id.in_(models_by_id),
                    FinancialModelRevision.effective_at <= as_of,
                    FinancialModelRevision.recorded_at <= as_of,
                )
                .order_by(
                    FinancialModelRevision.model_id,
                    FinancialModelRevision.revision_number,
                    FinancialModelRevision.recorded_at,
                )
            )
        )
        if models_by_id
        else []
    )
    revision_by_model: dict[UUID, FinancialModelRevision] = {}
    for revision in revisions:
        revision_by_model[revision.model_id] = revision
    outputs = (
        list(
            session.scalars(
                select(FinancialModelOutput).where(
                    FinancialModelOutput.revision_id.in_([revision.id for revision in revisions])
                )
            )
        )
        if revisions
        else []
    )
    output_by_revision = {output.revision_id: output for output in outputs}

    legacy_rows = list(
        session.scalars(
            select(ModelOutputSnapshot)
            .where(
                ModelOutputSnapshot.company_id.in_(company_ids),
                ModelOutputSnapshot.snapshot_kind == ModelOutputSnapshotKind.CURRENT_CONTRACT,
                ModelOutputSnapshot.recorded_at <= as_of,
                (ModelOutputSnapshot.effective_at.is_(None))
                | (ModelOutputSnapshot.effective_at <= as_of),
            )
            .order_by(
                ModelOutputSnapshot.company_id,
                ModelOutputSnapshot.model_key,
                ModelOutputSnapshot.recorded_at.desc(),
                ModelOutputSnapshot.id,
            )
        )
    )
    latest_legacy: dict[tuple[UUID, str], ModelOutputSnapshot] = {}
    for legacy_snapshot in legacy_rows:
        latest_legacy.setdefault(
            (legacy_snapshot.company_id, legacy_snapshot.model_key), legacy_snapshot
        )
    legacy_by_company: dict[UUID, list[ModelOutputSnapshot]] = defaultdict(list)
    for (company_id, _model_key), legacy_snapshot in latest_legacy.items():
        legacy_by_company[company_id].append(legacy_snapshot)

    base: dict[UUID, RankCandidate] = {}
    errors: dict[UUID, tuple[RankingEntryStatus, str, dict[str, Any] | None]] = {}
    for company in companies:
        if lifecycle_by_company.get(company.id) != "WATCHLIST":
            errors[company.id] = (
                RankingEntryStatus.NOT_ELIGIBLE,
                "Canonical Watchlist Rank includes explicit WATCHLIST lifecycle only.",
                None,
            )
            continue

        score_snapshot = score_contexts[company.id]
        models = models_by_company.get(company.id, [])
        eligible_native = [
            (model, revision_by_model[model.id])
            for model in models
            if model.id in revision_by_model
        ]
        if len(eligible_native) > 1:
            errors[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "More than one accepted native model series is effective for this company; "
                "the rank cannot choose a methodology or listing.",
                None,
            )
            continue
        if eligible_native:
            model, revision = eligible_native[0]
            output = output_by_revision.get(revision.id)
            if output is None:
                errors[company.id] = (
                    RankingEntryStatus.DATA_CHECK,
                    "The accepted native model revision has no retained output.",
                    None,
                )
                continue
            source_snapshot = _native_source_snapshot(session, model, revision, output)
            entry_context = _input_snapshot(
                output.expected_cash_flow_irr,
                NATIVE_RETURN_SEMANTICS,
                source_snapshot,
                score_snapshot,
                output.forward_fundamental_cagr,
                output.weighted_fv,
                output.hurdle,
                output.expected_excess,
            )
            if output.expected_cash_flow_irr is None:
                errors[company.id] = (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    output.irr_unavailable_reason
                    or "The accepted native model has no valid Expected IRR.",
                    entry_context,
                )
                continue
            native_error = _native_output_error(session, model, output, as_of)
            if native_error:
                errors[company.id] = (
                    RankingEntryStatus.DATA_CHECK,
                    native_error,
                    entry_context,
                )
                continue
            ticker = cast(str | None, source_snapshot["listing_ticker"])
            if ticker is None:
                errors[company.id] = (
                    RankingEntryStatus.DATA_CHECK,
                    "No exact valuation-listing ticker is available for the documented tie-break.",
                    entry_context,
                )
                continue
            base[company.id] = RankCandidate(
                NATIVE_RETURN_SEMANTICS, ticker, output.expected_cash_flow_irr, entry_context
            )
            continue

        # An existing model identity with no accepted revision as of this run does
        # not supersede an available imported current contract.
        contracts = legacy_by_company.get(company.id, [])
        if len(contracts) > 1:
            errors[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "Multiple current model-output contracts exist; no single Expected IRR input "
                "can be selected safely.",
                None,
            )
            continue
        if not contracts:
            errors[company.id] = (
                RankingEntryStatus.INPUTS_UNAVAILABLE,
                "No point-in-time current model output provides an Expected IRR.",
                None,
            )
            continue
        contract = contracts[0]
        source_snapshot = _legacy_source_snapshot(session, contract, as_of)
        entry_context = _input_snapshot(
            contract.expected_cash_flow_irr,
            LEGACY_RETURN_SEMANTICS,
            source_snapshot,
            score_snapshot,
            contract.forward_fundamental_cagr,
            contract.weighted_fv,
            contract.hurdle,
            contract.expected_excess,
        )
        legacy_error = _legacy_output_error(contract)
        if legacy_error:
            status = (
                RankingEntryStatus.INPUTS_UNAVAILABLE
                if contract.expected_cash_flow_irr is None
                or contract.output_quality == "UNAVAILABLE"
                else RankingEntryStatus.DATA_CHECK
            )
            errors[company.id] = (status, legacy_error, entry_context)
            continue
        assert contract.expected_cash_flow_irr is not None
        ticker = cast(str | None, source_snapshot["listing_ticker"])
        if ticker is None:
            errors[company.id] = (
                RankingEntryStatus.DATA_CHECK,
                "No exact or unique listing maps to the legacy model key; the ticker tie-break "
                "cannot be reconstructed.",
                entry_context,
            )
            continue
        assert contract.expected_cash_flow_irr is not None
        base[company.id] = RankCandidate(
            LEGACY_RETURN_SEMANTICS,
            ticker,
            contract.expected_cash_flow_irr,
            entry_context,
        )

    # Never sort native method IRR against an imported legacy normalized field.
    selected_semantics = (
        NATIVE_RETURN_SEMANTICS
        if any(item.semantics == NATIVE_RETURN_SEMANTICS for item in base.values())
        else LEGACY_RETURN_SEMANTICS
    )
    result: dict[UUID, tuple[RankingEntryStatus, str, int | None, dict[str, Any] | None]] = {}
    comparable: list[tuple[UUID, str, Decimal, dict[str, Any]]] = []
    for company_id, candidate in base.items():
        if candidate.semantics != selected_semantics:
            result[company_id] = (
                RankingEntryStatus.DATA_CHECK,
                "Native shareholder-cash-flow IRR and legacy normalized Expected IRR are not "
                "assumed comparable; this run ranks only the native cohort.",
                None,
                candidate.input_snapshot,
            )
            continue
        comparable.append((company_id, candidate.ticker, candidate.value, candidate.input_snapshot))

    duplicate_tickers = {
        ticker for ticker, count in Counter(item[1] for item in comparable).items() if count > 1
    }
    sortable: list[tuple[UUID, str, Decimal]] = []
    for company_id, ticker, value, snapshot in comparable:
        if ticker in duplicate_tickers:
            result[company_id] = (
                RankingEntryStatus.DATA_CHECK,
                f"Ticker {ticker} is not unique in the eligible population; the workbook tie-break "
                "cannot assign an auditable ordinal.",
                None,
                snapshot,
            )
        else:
            sortable.append((company_id, ticker, value))
    positions = expected_irr_positions(sortable)
    snapshots_by_company = {
        company_id: snapshot for company_id, _ticker, _value, snapshot in comparable
    }
    semantics_label = (
        "native Expected Cash-Flow IRR"
        if selected_semantics == NATIVE_RETURN_SEMANTICS
        else "legacy normalized Expected IRR"
    )
    for company_id, position in positions.items():
        result[company_id] = (
            RankingEntryStatus.RANKED,
            f"Ranked by {semantics_label} descending, then canonical listing ticker ascending. "
            "Durability and Compounder Quality are retained as separate context; no numeric gate "
            "threshold or composite score is inferred.",
            position,
            snapshots_by_company[company_id],
        )
    for company_id, (status, reason, input_snapshot) in errors.items():
        result.setdefault(company_id, (status, reason, None, input_snapshot))

    return [
        (
            company.id,
            *result.get(
                company.id,
                (
                    RankingEntryStatus.INPUTS_UNAVAILABLE,
                    "Expected IRR input could not be established for this run.",
                    None,
                    None,
                ),
            ),
        )
        for company in companies
    ]


def _score_contexts(
    session: Session, company_ids: set[UUID], as_of: datetime
) -> dict[UUID, dict[str, Any]]:
    dimensions = (ScoreDimension.DURABILITY_10Y, ScoreDimension.COMPOUNDER_QUALITY)
    definitions = list(
        session.scalars(
            select(ScoreDefinition)
            .where(
                ScoreDefinition.dimension.in_(dimensions),
                ScoreDefinition.status == ScoreDefinitionStatus.ACTIVE,
                ScoreDefinition.effective_from <= as_of,
                ScoreDefinition.recorded_at <= as_of,
            )
            .order_by(ScoreDefinition.dimension, ScoreDefinition.version.desc())
        )
    )
    definition_by_dimension: dict[str, ScoreDefinition] = {}
    for definition in definitions:
        definition_by_dimension.setdefault(definition.dimension, definition)
    assessments = (
        list(
            session.scalars(
                select(ScoreAssessment)
                .where(
                    ScoreAssessment.company_id.in_(company_ids),
                    ScoreAssessment.score_definition_id.in_([item.id for item in definitions]),
                    ScoreAssessment.effective_at <= as_of,
                    ScoreAssessment.recorded_at <= as_of,
                )
                .order_by(
                    ScoreAssessment.company_id,
                    ScoreAssessment.score_definition_id,
                    ScoreAssessment.effective_at.desc(),
                    ScoreAssessment.recorded_at.desc(),
                    ScoreAssessment.id.desc(),
                )
            )
        )
        if definitions
        else []
    )
    latest: dict[tuple[UUID, UUID], ScoreAssessment] = {}
    for assessment in assessments:
        latest.setdefault((assessment.company_id, assessment.score_definition_id), assessment)

    result: dict[UUID, dict[str, Any]] = {}
    for company_id in company_ids:
        score_rows: dict[str, Any] = {}
        for dimension in dimensions:
            key = (
                "durability_10y"
                if dimension == ScoreDimension.DURABILITY_10Y
                else "compounder_quality"
            )
            active_definition: ScoreDefinition | None = definition_by_dimension.get(dimension)
            selected_assessment: ScoreAssessment | None = (
                latest.get((company_id, active_definition.id)) if active_definition else None
            )
            status = selected_assessment.status if selected_assessment else "NOT_ASSESSED"
            score_rows[key] = {
                "score": str(selected_assessment.score)
                if selected_assessment and selected_assessment.score is not None
                else None,
                "status": status,
                "assessment_id": str(selected_assessment.id) if selected_assessment else None,
                "effective_at": (
                    selected_assessment.effective_at.isoformat() if selected_assessment else None
                ),
                "recorded_at": (
                    selected_assessment.recorded_at.isoformat() if selected_assessment else None
                ),
                "rationale": selected_assessment.rationale if selected_assessment else None,
                "source": selected_assessment.source if selected_assessment else None,
            }
        result[company_id] = score_rows
    return result


def _native_output_error(
    session: Session,
    model: FinancialModel,
    output: FinancialModelOutput,
    as_of: datetime,
) -> str | None:
    if output.status not in {"COMPLETE", "PARTIAL"}:
        return "The native model output quality does not permit a current Expected IRR."
    if not model.model_currency or output.model_currency != model.model_currency:
        return "Native model currency is missing or inconsistent with its normalized output."
    if output.price_status != "FRESH" or output.price_effective_at is None:
        return "The native Expected IRR has no fresh, dated reference price."
    age_days = (as_of.date() - output.price_effective_at.astimezone(UTC).date()).days
    if age_days < 0 or age_days > FRESH_DAYS:
        return "The native Expected IRR reference price is outside the five-day freshness window."
    latest_price_at = session.scalar(
        select(PriceObservation.market_date)
        .where(
            PriceObservation.listing_id == model.valuation_listing_id,
            PriceObservation.market_date <= as_of,
            PriceObservation.recorded_at <= as_of,
            or_(PriceObservation.observed_at.is_(None), PriceObservation.observed_at <= as_of),
            PriceObservation.data_quality == "PASS",
        )
        .order_by(PriceObservation.market_date.desc())
        .limit(1)
    )
    if (
        latest_price_at is None
        or latest_price_at.astimezone(UTC).date() > output.price_effective_at.astimezone(UTC).date()
    ):
        return (
            "A later exact-listing price exists than the price used by the accepted Expected IRR."
        )
    return None


def _legacy_output_error(snapshot: ModelOutputSnapshot) -> str | None:
    if snapshot.contract_status != "PASS":
        return "The imported current output contract is not in PASS data-quality state."
    if snapshot.output_quality not in {"COMPLETE", "PARTIAL"}:
        return "The imported current model output is not usable."
    if snapshot.expected_cash_flow_irr is None:
        return "The imported current contract has no numeric Expected IRR."
    if snapshot.currency_status != "DOCUMENTED" or snapshot.model_currency is None:
        return (
            "The legacy model currency is unknown; Expected IRR comparability needs a data check."
        )
    if any(
        issue.get("field") in {"expected_cash_flow_irr", "expected_irr"}
        for issue in snapshot.field_issues
    ):
        return "The imported Expected IRR has a field-level data-quality issue."
    return None


def _native_source_snapshot(
    session: Session,
    model: FinancialModel,
    revision: FinancialModelRevision,
    output: FinancialModelOutput,
) -> dict[str, Any]:
    listing = session.get(Listing, model.valuation_listing_id)
    migration = session.scalar(
        select(FinancialModelMigrationAssessment)
        .where(FinancialModelMigrationAssessment.revision_id == revision.id)
        .order_by(FinancialModelMigrationAssessment.recorded_at.desc())
        .limit(1)
    )
    return {
        "source_kind": "NATIVE_MODEL_REVISION",
        "record_id": str(output.id),
        "model_id": str(model.id),
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "model_key": model.source_model_key,
        "model_type": revision.model_type,
        "methodology_version": revision.methodology_version,
        "contract_version": None,
        "source_revision_id": revision.source_revision_id,
        "source": revision.source,
        "effective_at": revision.effective_at.isoformat(),
        "recorded_at": revision.recorded_at.isoformat(),
        "effective_time_status": "KNOWN",
        "model_currency": model.model_currency,
        "currency_status": "DOCUMENTED",
        "output_quality": output.status,
        "contract_status": None,
        "price_status": output.price_status,
        "price_effective_at": output.price_effective_at.isoformat()
        if output.price_effective_at
        else None,
        "price_observation_id": str(output.price_observation_id)
        if output.price_observation_id
        else None,
        "listing_id": str(listing.id) if listing else None,
        "listing_ticker": listing.ticker if listing else None,
        "listing_venue": listing.venue if listing else None,
        "migration_status": migration.status if migration else None,
    }


def _legacy_source_snapshot(
    session: Session, snapshot: ModelOutputSnapshot, as_of: datetime
) -> dict[str, Any]:
    models = list(
        session.scalars(
            select(FinancialModel).where(
                FinancialModel.company_id == snapshot.company_id,
                FinancialModel.source_model_key == snapshot.model_key,
                FinancialModel.created_at <= as_of,
            )
        )
    )
    listing: Listing | None = None
    if len(models) == 1:
        listing = session.get(Listing, models[0].valuation_listing_id)
    elif not models:
        listings = list(
            session.scalars(
                select(Listing)
                .join(Security, Security.id == Listing.security_id)
                .where(
                    Security.company_id == snapshot.company_id,
                    Listing.created_at <= as_of,
                    Security.created_at <= as_of,
                )
                .order_by(Listing.ticker, Listing.venue, Listing.id)
            )
        )
        if len(listings) == 1:
            listing = listings[0]
    return {
        "source_kind": "IMPORTED_CURRENT_CONTRACT",
        "record_id": str(snapshot.id),
        "model_id": str(models[0].id) if len(models) == 1 else None,
        "revision_id": None,
        "revision_number": None,
        "model_key": snapshot.model_key,
        "model_type": None,
        "methodology_version": None,
        "contract_version": snapshot.contract_version,
        "source_revision_id": snapshot.source_revision_id,
        "source": snapshot.source,
        "effective_at": snapshot.effective_at.isoformat() if snapshot.effective_at else None,
        "recorded_at": snapshot.recorded_at.isoformat(),
        "effective_time_status": "KNOWN" if snapshot.effective_at else "UNKNOWN",
        "model_currency": snapshot.model_currency,
        "currency_status": snapshot.currency_status,
        "output_quality": snapshot.output_quality,
        "contract_status": snapshot.contract_status,
        "price_status": None,
        "price_effective_at": None,
        "price_observation_id": None,
        "listing_id": str(listing.id) if listing else None,
        "listing_ticker": listing.ticker if listing else None,
        "listing_venue": listing.venue if listing else None,
        "migration_status": None,
    }


def _input_snapshot(
    expected_irr: Decimal | None,
    semantics: str,
    source: dict[str, Any],
    scores: dict[str, Any],
    forward_cagr: Decimal | None,
    weighted_fv: Decimal | None,
    hurdle: Decimal | None,
    expected_excess: Decimal | None,
) -> dict[str, Any]:
    context = s.WatchlistRankInputSnapshot.model_validate(
        {
            "context_version": RANK_CONTEXT_VERSION,
            "expected_irr": expected_irr,
            "return_semantics": semantics,
            "return_source": source,
            **scores,
            "forward_fundamental_cagr": forward_cagr,
            "weighted_fair_value": weighted_fv,
            "hurdle": hurdle,
            "expected_excess": expected_excess,
            "decision_context": "QUALITY_GATE_THRESHOLDS_NOT_DOCUMENTED",
            "context_note": (
                "10Y Durability, Compounder Quality, and forward compounding precede valuation "
                "in the research hierarchy. Their observations remain separate context; this "
                "rank reproduces the documented Expected IRR ordering among explicit Watchlist "
                "members. Numeric quality-gate thresholds and portfolio-fit adjustments are "
                "not documented, so no pass/fail gate is inferred. Missing context stays null."
            ),
        }
    )
    return context.model_dump(mode="json")
