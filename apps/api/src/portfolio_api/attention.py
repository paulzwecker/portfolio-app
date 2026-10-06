"""Conservative, read-only attention feed composed from immutable domain history."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas as s
from portfolio_api.domain.consensus_policy import select_consensus_source
from portfolio_api.domain.models import (
    Company,
    ConsensusEstimateObservation,
    ConsensusEstimateProviderMapping,
    CurrentLifecycle,
    ExecutionPaceDecision,
    ExecutionPaceRun,
    FinancialModel,
    FinancialModelOutput,
    FinancialModelRevision,
    Lifecycle,
    LifecycleEvent,
    Listing,
    ModelOutputSnapshot,
    PriceObservation,
    RankingDefinition,
    RankingEntry,
    RankingRun,
    Security,
    SourceDocument,
)

PRICE_FRESH_DAYS = 5  # documented current-quote freshness window
EXPECTED_IRR_MOVE = Decimal("0.05")  # conservative feed threshold, not an investment rule
CONSENSUS_MOVE = Decimal("0.05")  # relative change; positive same-provider baseline only
PRICE_MOVE = Decimal("0.10")  # one-session split-adjusted move; operational alert threshold
RANK_MOVE = 3  # minimum place movement to avoid routine rerun noise


def _date_time(value: date | datetime | None) -> tuple[datetime | None, str]:
    if value is None:
        return None, "UNKNOWN"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC), "TIMESTAMP"
    return datetime.combine(value, time.min, tzinfo=UTC), "DATE"


def _event(
    *,
    issuer: Company | None,
    lifecycle: str | None,
    event_type: str,
    severity: str,
    title: str,
    explanation: str,
    effective_at: date | datetime | None,
    recorded_at: datetime | None,
    source_domain: str,
    source_id: object | None,
    source_reference: str | None = None,
    prior_value: object | None = None,
    current_value: object | None = None,
    unit: str | None = None,
    status: str = "INFORMATIONAL",
) -> s.AttentionEventRead:
    when, precision = _date_time(effective_at)
    company_id = issuer.id if issuer else None
    return s.AttentionEventRead(
        id=f"{source_domain}:{source_id}"
        if source_id is not None
        else f"{source_domain}:{company_id}:{event_type}",
        company_id=company_id,
        company_name=issuer.name if issuer else None,
        lifecycle=Lifecycle(lifecycle) if lifecycle else None,
        event_type=event_type,
        severity=severity,
        status=status,
        title=title,
        explanation=explanation,
        effective_at=when,
        time_precision=precision,
        recorded_at=recorded_at,
        source_domain=source_domain,
        source_id=str(source_id) if source_id is not None else None,
        source_reference=source_reference,
        href=f"/company/{company_id}" if company_id else None,
        prior_value=str(prior_value) if prior_value is not None else None,
        current_value=str(current_value) if current_value is not None else None,
        unit=unit,
    )


def _sort_key(item: s.AttentionEventRead) -> tuple[datetime, datetime, str]:
    oldest = datetime.min.replace(tzinfo=UTC)
    return (
        item.effective_at or item.recorded_at or oldest,
        item.recorded_at or oldest,
        item.id,
    )


def _within(value: date | datetime | None, cutoff: datetime, as_of: datetime) -> bool:
    instant, _ = _date_time(value)
    return instant is not None and cutoff <= instant <= as_of


def deduplicate_and_order(events: list[s.AttentionEventRead]) -> list[s.AttentionEventRead]:
    """Stable source-identity de-duplication and event-time ordering."""
    unique = {item.id: item for item in events}
    return sorted(unique.values(), key=_sort_key, reverse=True)


def attention_feed(
    session: Session,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 30,
    company_id: UUID | None = None,
    event_type: str | None = None,
    lifecycle: Lifecycle | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> s.AttentionFeedRead:
    """Compose recent material changes and current missing/stale states from source records."""
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    cutoff = now - timedelta(days=lookback_days)
    states = dict(
        session.execute(
            select(CurrentLifecycle.company_id, LifecycleEvent.new_state).join(
                LifecycleEvent, LifecycleEvent.id == CurrentLifecycle.event_id
            )
        ).all()
    )
    if lifecycle:
        company_ids = {key for key, value in states.items() if value == lifecycle.value}
    else:
        company_ids = {key for key, value in states.items() if value != Lifecycle.DROP.value}
    issuers = (
        {
            issuer.id: issuer
            for issuer in session.scalars(select(Company).where(Company.id.in_(company_ids))).all()
        }
        if company_ids
        else {}
    )
    if company_id:
        company_ids.intersection_update({company_id})
        issuers = {key: value for key, value in issuers.items() if key == company_id}
    states = {key: value for key, value in states.items() if key in company_ids}
    events: list[s.AttentionEventRead] = []

    def add(**kwargs: Any) -> None:
        events.append(_event(**kwargs))

    # Native model edits are inherently material revisions. A substantial IRR movement
    # is folded into the same source revision event, avoiding duplicate alerts.
    revisions = (
        session.execute(
            select(FinancialModelRevision, FinancialModel)
            .join(FinancialModel, FinancialModel.id == FinancialModelRevision.model_id)
            .where(FinancialModel.company_id.in_(company_ids))
            .order_by(FinancialModelRevision.model_id, FinancialModelRevision.revision_number)
        ).all()
        if company_ids
        else []
    )
    outputs = {row.revision_id: row for row in session.scalars(select(FinancialModelOutput)).all()}
    by_model: dict[UUID, list[tuple[FinancialModelRevision, FinancialModel]]] = defaultdict(list)
    for revision, model in revisions:
        by_model[model.id].append((revision, model))
    for model_chain in by_model.values():
        for revision_index, (model_revision, model_identity) in enumerate(model_chain):
            revision_time = (
                model_revision.effective_at
                if model_revision.actor == "IMPORT"
                else model_revision.recorded_at
            )
            if not _within(revision_time, cutoff, now):
                continue
            current_output = outputs.get(model_revision.id)
            prior_revision = model_chain[revision_index - 1][0] if revision_index else None
            prior_output = outputs.get(prior_revision.id) if prior_revision else None
            previous_irr = (
                prior_output.expected_cash_flow_irr
                if prior_output and prior_output.status == "COMPLETE"
                else None
            )
            current_irr = (
                current_output.expected_cash_flow_irr
                if current_output and current_output.status == "COMPLETE"
                else None
            )
            previous_fv = (
                prior_output.weighted_fv
                if prior_output and prior_output.status == "COMPLETE"
                else None
            )
            current_fv = (
                current_output.weighted_fv
                if current_output and current_output.status == "COMPLETE"
                else None
            )
            irr_delta = (
                current_irr - previous_irr
                if current_irr is not None and previous_irr is not None
                else None
            )
            fv_change = (
                current_fv / previous_fv - Decimal(1)
                if current_fv is not None
                and previous_fv is not None
                and previous_fv > 0
                and prior_output is not None
                and current_output is not None
                and prior_output.model_currency == current_output.model_currency
                else None
            )
            material_fv_change = fv_change is not None and abs(fv_change) >= Decimal("0.10")
            is_irr_change = (
                irr_delta is not None
                and abs(irr_delta) >= EXPECTED_IRR_MOVE
                and prior_revision is not None
                and prior_revision.model_type == model_revision.model_type
                and prior_revision.methodology_version == model_revision.methodology_version
            )
            if is_irr_change:
                assert previous_irr is not None and current_irr is not None
                explanation = (
                    f"{model_revision.model_type} revision {model_revision.revision_number}; "
                    f"deterministic output moved from {previous_irr:.1%} "
                    f"to {current_irr:.1%}. {model_revision.rationale}"
                )
            else:
                explanation = (
                    f"{model_revision.model_type} accepted revision "
                    f"{model_revision.revision_number}. {model_revision.rationale}"
                )
            if material_fv_change:
                assert previous_fv is not None and current_fv is not None
                assert current_output is not None
                explanation += (
                    f" Weighted Fair Value moved {fv_change:+.1%} "
                    f"({previous_fv} to {current_fv} {current_output.model_currency})."
                )
            add(
                issuer=issuers.get(model_identity.company_id),
                lifecycle=states.get(model_identity.company_id),
                event_type="EXPECTED_IRR_CHANGE" if is_irr_change else "MODEL_REVISION",
                severity="HIGH"
                if is_irr_change and irr_delta is not None and abs(irr_delta) >= Decimal("0.10")
                else "MEDIUM",
                title=(
                    "Expected IRR changed materially"
                    if is_irr_change
                    else f"Model revision {model_revision.revision_number}"
                ),
                explanation=explanation,
                effective_at=model_revision.effective_at,
                recorded_at=model_revision.recorded_at,
                source_domain="financial_model_revision",
                source_id=model_revision.id,
                source_reference=model_revision.source,
                prior_value=(
                    f"{previous_irr:.1%}"
                    if is_irr_change
                    else previous_fv
                    if material_fv_change
                    else None
                ),
                current_value=(
                    f"{current_irr:.1%}"
                    if is_irr_change
                    else current_fv
                    if material_fv_change
                    else None
                ),
                unit=(
                    "Expected IRR"
                    if is_irr_change
                    else "model currency per share"
                    if material_fv_change
                    else None
                ),
            )

    for snapshot in (
        session.scalars(
            select(ModelOutputSnapshot).where(
                ModelOutputSnapshot.company_id.in_(company_ids),
            )
        ).all()
        if company_ids
        else []
    ):
        if not _within(snapshot.effective_at or snapshot.recorded_at, cutoff, now):
            continue
        add(
            issuer=issuers.get(snapshot.company_id),
            lifecycle=states.get(snapshot.company_id),
            event_type="MODEL_OUTPUT_IMPORT",
            severity="MEDIUM",
            title="Imported model output recorded",
            explanation=(
                f"{snapshot.model_key} · {snapshot.output_quality} · "
                f"{snapshot.contract_status}. "
                f"{snapshot.rationale or snapshot.notes or 'Imported legacy output snapshot.'}"
            ),
            effective_at=snapshot.effective_at,
            recorded_at=snapshot.recorded_at,
            source_domain="model_output_snapshot",
            source_id=snapshot.id,
            source_reference=snapshot.source,
        )

    # Use only the selected primary/fallback stream; never compare providers or units.
    mappings_by_company: dict[UUID, list[ConsensusEstimateProviderMapping]] = defaultdict(list)
    for provider_mapping in (
        session.scalars(
            select(ConsensusEstimateProviderMapping).where(
                ConsensusEstimateProviderMapping.company_id.in_(company_ids),
                ConsensusEstimateProviderMapping.effective_from <= now,
            )
        ).all()
        if company_ids
        else []
    ):
        mappings_by_company[provider_mapping.company_id].append(provider_mapping)
    selected_mapping = {
        issuer_id: select_consensus_source(mappings)[0]
        for issuer_id, mappings in mappings_by_company.items()
    }
    estimates = (
        session.scalars(
            select(ConsensusEstimateObservation)
            .where(ConsensusEstimateObservation.company_id.in_(company_ids))
            .order_by(
                ConsensusEstimateObservation.company_id,
                ConsensusEstimateObservation.metric,
                ConsensusEstimateObservation.forecast_period,
                ConsensusEstimateObservation.snapshot_date,
                ConsensusEstimateObservation.recorded_at,
            )
        ).all()
        if company_ids
        else []
    )
    estimate_chains: dict[
        tuple[UUID, str, str, str, str | None, str], list[ConsensusEstimateObservation]
    ] = defaultdict(list)
    for observation in estimates:
        selected_source = selected_mapping.get(observation.company_id)
        if selected_source and observation.provider_mapping_id == selected_source.id:
            key = (
                observation.company_id,
                observation.provider_id,
                observation.metric,
                observation.forecast_period,
                observation.currency,
                observation.unit,
            )
            estimate_chains[key].append(observation)
    for estimate_chain in estimate_chains.values():
        for prior_estimate, current_estimate in zip(
            estimate_chain, estimate_chain[1:], strict=False
        ):
            if not _within(
                current_estimate.observed_at or current_estimate.snapshot_date,
                cutoff,
                now,
            ):
                continue
            if (
                prior_estimate.data_quality != "PASS"
                or current_estimate.data_quality != "PASS"
                or prior_estimate.value <= 0
            ):
                continue
            change = current_estimate.value / prior_estimate.value - Decimal(1)
            if abs(change) < CONSENSUS_MOVE:
                continue
            effective = current_estimate.observed_at or current_estimate.snapshot_date
            add(
                issuer=issuers.get(current_estimate.company_id),
                lifecycle=states.get(current_estimate.company_id),
                event_type="CONSENSUS_REVISION",
                severity="MEDIUM",
                title=f"{current_estimate.metric} consensus moved {change:+.1%}",
                explanation=(
                    f"{current_estimate.provider_id} {current_estimate.forecast_period} "
                    f"estimate changed from {prior_estimate.value} to "
                    f"{current_estimate.value}; provider, metric, period, "
                    "currency and unit are held constant."
                ),
                effective_at=effective,
                recorded_at=current_estimate.recorded_at,
                source_domain="consensus_estimate_observation",
                source_id=current_estimate.id,
                source_reference=current_estimate.source_ref,
                prior_value=prior_estimate.value,
                current_value=current_estimate.value,
                unit=f"{current_estimate.currency or ''} {current_estimate.unit}".strip(),
            )

    # Each current filing is one item; superseded source records do not create duplicate alerts.
    replaced_docs = set(
        session.scalars(
            select(SourceDocument.supersedes_document_id).where(
                SourceDocument.supersedes_document_id.is_not(None)
            )
        ).all()
    )
    for document in (
        session.scalars(
            select(SourceDocument).where(
                SourceDocument.company_id.in_(company_ids),
            )
        ).all()
        if company_ids
        else []
    ):
        if document.id in replaced_docs:
            continue
        filing_time = document.published_at or document.filed_at or document.recorded_at
        if not _within(filing_time, cutoff, now):
            continue
        add(
            issuer=issuers.get(document.company_id),
            lifecycle=states.get(document.company_id),
            event_type="NEW_FILING",
            severity="MEDIUM",
            title=f"New {document.document_type}: {document.title}",
            explanation=(
                f"{document.source_name} · "
                f"{document.reporting_period or 'reporting period unavailable'}."
            ),
            effective_at=document.published_at or document.filed_at,
            recorded_at=document.recorded_at,
            source_domain="source_document",
            source_id=document.id,
            source_reference=document.canonical_url,
        )

    # Price move rule is deliberately simple: one adjacent clean daily session, same listing,
    # split-adjusted series, at least 10%; corrections and stale gaps are not market moves.
    listings = (
        session.execute(
            select(Listing, Security)
            .join(Security, Security.id == Listing.security_id)
            .where(Security.company_id.in_(company_ids))
        ).all()
        if company_ids
        else []
    )
    listings_by_id = {listing.id: (listing, security) for listing, security in listings}
    price_rows = (
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.listing_id.in_(listings_by_id),
                PriceObservation.price_kind == "DAILY_CLOSE",
                PriceObservation.market_date >= now - timedelta(days=lookback_days + 5),
                PriceObservation.market_date <= now,
            )
            .order_by(
                PriceObservation.listing_id,
                PriceObservation.market_date,
                PriceObservation.recorded_at,
            )
        ).all()
        if listings_by_id
        else []
    )
    price_chains: dict[UUID, list[PriceObservation]] = defaultdict(list)
    superseded_prices = set(
        session.scalars(
            select(PriceObservation.supersedes_observation_id).where(
                PriceObservation.supersedes_observation_id.is_not(None)
            )
        ).all()
    )
    for price_observation in price_rows:
        if (
            price_observation.id not in superseded_prices
            and price_observation.supersedes_observation_id is None
        ):
            price_chains[price_observation.listing_id].append(price_observation)
    for listing_id, price_chain in price_chains.items():
        listing, security = listings_by_id[listing_id]
        if security.company_id is None:
            continue
        company = issuers.get(security.company_id)
        state = states.get(security.company_id)
        for prior_price, current_price in zip(price_chain, price_chain[1:], strict=False):
            if not _within(current_price.market_date, cutoff, now):
                continue
            if prior_price.data_quality != "PASS" or current_price.data_quality != "PASS":
                continue
            if (
                prior_price.split_adjusted_close is None
                or current_price.split_adjusted_close is None
                or prior_price.split_adjusted_close <= 0
            ):
                continue
            if (current_price.market_date - prior_price.market_date).days > PRICE_FRESH_DAYS:
                continue
            move = current_price.split_adjusted_close / prior_price.split_adjusted_close - Decimal(
                1
            )
            if abs(move) < PRICE_MOVE:
                continue
            add(
                issuer=company,
                lifecycle=state,
                event_type="PRICE_MOVE",
                severity="HIGH" if abs(move) >= Decimal("0.20") else "MEDIUM",
                title=f"{listing.ticker} moved {move:+.1%} in one session",
                explanation=(
                    "Split-adjusted close versus the previous clean session; this "
                    "threshold is an operational feed rule."
                ),
                effective_at=current_price.market_date,
                recorded_at=current_price.recorded_at,
                source_domain="price_observation",
                source_id=current_price.id,
                source_reference=current_price.source_ref,
                prior_value=prior_price.split_adjusted_close,
                current_value=current_price.split_adjusted_close,
                unit=listing.currency or current_price.currency,
            )

    # Compare immutable ranking and pace snapshots; emit only meaningful transitions.
    rank_rows = (
        session.execute(
            select(RankingRun, RankingDefinition, RankingEntry)
            .join(RankingDefinition, RankingDefinition.id == RankingRun.definition_id)
            .join(RankingEntry, RankingEntry.run_id == RankingRun.id)
            .where(RankingEntry.company_id.in_(company_ids))
            .order_by(RankingDefinition.ranking_type, RankingEntry.company_id, RankingRun.as_of)
        ).all()
        if company_ids
        else []
    )
    rank_chains: dict[
        tuple[UUID, UUID],
        list[tuple[RankingRun, RankingEntry, RankingDefinition]],
    ] = defaultdict(list)
    for ranking_run, definition, ranking_entry in rank_rows:
        rank_chains[(ranking_entry.company_id, definition.id)].append(
            (ranking_run, ranking_entry, definition)
        )
    for (issuer_id, _definition_id), ranking_chain in rank_chains.items():
        for (_, prior_entry, _), (current_rank_run, current_entry, definition) in zip(
            ranking_chain, ranking_chain[1:], strict=False
        ):
            if not _within(current_rank_run.as_of, cutoff, now):
                continue
            changed = prior_entry.status != current_entry.status or (
                prior_entry.position is not None
                and current_entry.position is not None
                and abs(prior_entry.position - current_entry.position) >= RANK_MOVE
            )
            if not changed:
                continue
            before = (
                f"{prior_entry.status}{f' #{prior_entry.position}' if prior_entry.position else ''}"
            )
            after = (
                f"{current_entry.status}"
                f"{f' #{current_entry.position}' if current_entry.position else ''}"
            )
            add(
                issuer=issuers.get(issuer_id),
                lifecycle=states.get(issuer_id),
                event_type="RANK_CHANGE",
                severity="MEDIUM",
                title=f"{definition.ranking_type.title()} Rank changed",
                explanation=f"Latest immutable run changed from {before} to {after}.",
                effective_at=current_rank_run.as_of,
                recorded_at=current_rank_run.recorded_at,
                source_domain="ranking_entry",
                source_id=current_entry.id,
                source_reference=current_rank_run.source,
                prior_value=before,
                current_value=after,
                unit="rank position",
            )

    pace_rows = (
        session.execute(
            select(ExecutionPaceRun, ExecutionPaceDecision)
            .join(ExecutionPaceDecision, ExecutionPaceDecision.run_id == ExecutionPaceRun.id)
            .where(ExecutionPaceDecision.company_id.in_(company_ids))
            .order_by(ExecutionPaceDecision.company_id, ExecutionPaceRun.as_of)
        ).all()
        if company_ids
        else []
    )
    pace_chains: dict[tuple[UUID, str], list[tuple[ExecutionPaceRun, ExecutionPaceDecision]]] = (
        defaultdict(list)
    )
    for pace_run, pace_decision in pace_rows:
        pace_chains[(pace_decision.company_id, pace_run.methodology_version)].append(
            (pace_run, pace_decision)
        )
    for (issuer_id, _methodology_version), pace_chain in pace_chains.items():
        for (_prior_pace_run, prior_decision), (current_pace_run, current_decision) in zip(
            pace_chain, pace_chain[1:], strict=False
        ):
            if not _within(current_pace_run.as_of, cutoff, now):
                continue
            before = prior_decision.pace or prior_decision.decision_status
            after = current_decision.pace or current_decision.decision_status
            if before == after:
                continue
            add(
                issuer=issuers.get(issuer_id),
                lifecycle=states.get(issuer_id),
                event_type="EXECUTION_PACE_CHANGE",
                severity="MEDIUM",
                title="Execution Pace decision changed",
                explanation=(
                    f"Immutable decision changed from {before} to {after}; inspect its "
                    "input snapshot before acting."
                ),
                effective_at=current_pace_run.as_of,
                recorded_at=current_pace_run.recorded_at,
                source_domain="execution_pace_decision",
                source_id=current_decision.id,
                source_reference=current_pace_run.source,
                prior_value=before,
                current_value=after,
                unit="decision state",
            )

    # Current gaps are status items, not synthetic dated events. Only Portfolio/Watchlist
    # companies are expected to have ongoing price/model coverage.
    tracked = {
        key
        for key, value in states.items()
        if value in (Lifecycle.PORTFOLIO.value, Lifecycle.WATCHLIST.value)
    }
    current_quotes = (
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.listing_id.in_(listings_by_id),
                PriceObservation.price_kind == "CURRENT_QUOTE",
                PriceObservation.market_date <= now,
                PriceObservation.recorded_at <= now,
            )
            .order_by(
                PriceObservation.listing_id,
                PriceObservation.market_date.desc(),
                PriceObservation.recorded_at.desc(),
            )
        ).all()
        if listings_by_id
        else []
    )
    latest_by_listing: dict[UUID, PriceObservation] = {}
    for quote in current_quotes:
        latest_by_listing.setdefault(quote.listing_id, quote)
    quotes_by_company: dict[UUID, list[PriceObservation]] = defaultdict(list)
    for listing_id, quote in latest_by_listing.items():
        _, security = listings_by_id[listing_id]
        if security.company_id:
            quotes_by_company[security.company_id].append(quote)
    for issuer_id in tracked:
        company_quotes = quotes_by_company.get(issuer_id, [])
        valid_quote = any(
            quote.data_quality == "PASS"
            and quote.market_date.date() >= (now - timedelta(days=PRICE_FRESH_DAYS)).date()
            for quote in company_quotes
        )
        if not valid_quote:
            reason = (
                "No current quote is recorded"
                if not company_quotes
                else "Current quote coverage is stale or quality-checked"
            )
            reference = (
                max(company_quotes, key=lambda item: item.recorded_at).source_ref
                if company_quotes
                else None
            )
            recorded = max((item.recorded_at for item in company_quotes), default=None)
            add(
                issuer=issuers.get(issuer_id),
                lifecycle=states.get(issuer_id),
                event_type="DATA_QUALITY",
                severity="MEDIUM",
                status="REVIEW",
                title="Market quote needs review",
                explanation=reason,
                effective_at=max((item.market_date for item in company_quotes), default=None),
                recorded_at=recorded,
                source_domain="market_data_coverage",
                source_id=f"market:{issuer_id}:{reason}",
                source_reference=reference,
            )

    native_outputs = {
        revision_id for revision_id, output in outputs.items() if output.status == "COMPLETE"
    }
    snapshot_quality: dict[UUID, bool] = defaultdict(bool)
    for snapshot in (
        session.scalars(
            select(ModelOutputSnapshot).where(ModelOutputSnapshot.company_id.in_(tracked))
        ).all()
        if tracked
        else []
    ):
        if snapshot.output_quality == "COMPLETE" and snapshot.contract_status in (
            "PASS",
            "HISTORICAL_ONLY",
        ):
            snapshot_quality[snapshot.company_id] = True
    model_status: dict[UUID, bool] = defaultdict(bool)
    for model in (
        session.scalars(select(FinancialModel).where(FinancialModel.company_id.in_(tracked))).all()
        if tracked
        else []
    ):
        if model.current_revision_id in native_outputs:
            model_status[model.company_id] = True
    for issuer_id in tracked:
        if model_status[issuer_id] or snapshot_quality[issuer_id]:
            continue
        add(
            issuer=issuers.get(issuer_id),
            lifecycle=states.get(issuer_id),
            event_type="DATA_QUALITY",
            severity="LOW",
            status="REVIEW",
            title="No complete normalized model output",
            explanation=(
                "The active company has no complete native output or complete "
                "imported output snapshot. Missing model values remain unavailable."
            ),
            effective_at=None,
            recorded_at=None,
            source_domain="model_output_coverage",
            source_id=f"model:{issuer_id}:missing",
        )

    ordered = deduplicate_and_order(events)
    if event_type:
        ordered = [item for item in ordered if item.event_type == event_type]
    if severity:
        ordered = [item for item in ordered if item.severity == severity]
    if status:
        ordered = [item for item in ordered if item.status == status]
    total = len(ordered)
    return s.AttentionFeedRead(
        as_of=now, lookback_days=lookback_days, total=total, events=ordered[:limit]
    )
