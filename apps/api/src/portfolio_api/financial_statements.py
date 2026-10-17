"""Read-only financial statement workspace composed from canonical source domains."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import queries as q
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import FinancialModel, FinancialModelRevision
from portfolio_api.reported_fundamentals import METRIC_DEFINITIONS
from portfolio_api.research_forecasts import company_research

PeriodType = Literal["ANNUAL", "QUARTERLY"]
UNIT_MAP = {
    "CURRENCY": "currency",
    "CURRENCY_PER_SHARE": "currency_per_share",
    "currency/share": "currency_per_share",
    "SHARES": "shares",
}
FORECAST_METRICS = {
    "REVENUE": ("Revenue", "INCOME_STATEMENT"),
    "EPS": ("EPS", "INCOME_STATEMENT"),
    "EBIT": ("EBIT (forecast definition)", "INCOME_STATEMENT"),
    "EBITDA": ("EBITDA", "INCOME_STATEMENT"),
    "FREE_CASH_FLOW": ("Free cash flow", "CASH_FLOW_STATEMENT"),
    "DILUTED_SHARES": ("Diluted shares (forecast)", "INCOME_STATEMENT"),
}


def _append_cell(row: s.FinancialStatementRowRead, cell: s.FinancialStatementCellRead) -> None:
    prior = next((item for item in row.cells if item.period_end == cell.period_end), None)
    if prior is None:
        row.cells.append(cell)
        return
    # Distinct duration/source contexts at the same end are evidence to inspect,
    # not an instruction to add values or pick whichever happened to arrive last.
    prior.source_ids = sorted(set(prior.source_ids + cell.source_ids), key=str)
    prior.value = None
    prior.selected_source_id = None
    prior.status = "CONFLICT"
    prior.reason = "Multiple duration or forecast contexts share this period end; inspect sources."


def _label(year: int | None, period: str | None, end: date, kind: PeriodType) -> str:
    if year is not None and period:
        return f"FY{year}" + (f" · {period}" if period != "FY" else "")
    return f"{'Year' if kind == 'ANNUAL' else 'Quarter'} ended {end.isoformat()}"


def company_financial_statements(
    session: Session,
    company_id: UUID,
    *,
    period_type: PeriodType = "ANNUAL",
    period_limit: int = 10,
    as_of: date | None = None,
    known_at: datetime | None = None,
) -> s.CompanyFinancialStatementsRead:
    facts = q.company_reported_fundamentals(session, company_id, as_of=as_of, known_at=known_at)
    consensus = q.company_consensus_estimates(session, company_id, as_of, known_at)
    research = company_research(session, company_id, as_of, known_at)
    limitations: list[s.FinancialStatementLimitationRead] = []
    rows: dict[str, s.FinancialStatementRowRead] = {}
    labels: dict[date, set[tuple[int, str]]] = {}
    actual_ends: set[date] = set()
    actual_duration_ends = {
        item.period_end.date() for item in facts.periods if item.period_type == period_type
    }
    annual_ends = {item.period_end.date() for item in facts.periods if item.period_type == "ANNUAL"}

    def row_for(
        metric: str,
        label: str,
        statement: str,
        source: s.FinancialStatementSource,
        source_name: str,
        currency: str | None,
        unit: str,
        stream: str = "",
        scenario: str | None = None,
    ) -> s.FinancialStatementRowRead:
        key = f"{source}:{stream}:{metric}:{currency or 'NONE'}:{unit}:{scenario or ''}"
        if key not in rows:
            rows[key] = s.FinancialStatementRowRead(
                id=key,
                metric=metric,
                label=label,
                statement=cast(
                    Literal["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW_STATEMENT"], statement
                ),
                source_kind=source,
                source_name=source_name,
                scenario=scenario,
                currency=currency,
                unit=unit,
                cells=[],
            )
        return rows[key]

    definitions = {item.metric.value: item for item in METRIC_DEFINITIONS}
    included_facts: list[s.ReportedFundamentalPeriodRead] = []
    for fact in facts.periods:
        end = fact.period_end.date()
        instant_eligible = fact.period_type == "INSTANT" and (
            end in actual_duration_ends or (period_type == "QUARTERLY" and end in annual_ends)
        )
        if fact.period_type != period_type and not instant_eligible:
            continue
        included_facts.append(fact)
        actual_ends.add(end)
        if fact.fiscal_year is not None and fact.fiscal_period:
            fp = (
                "Q4"
                if period_type == "QUARTERLY" and fact.fiscal_period == "FY"
                else fact.fiscal_period
            )
            labels.setdefault(end, set()).add((fact.fiscal_year, fp))
        definition = definitions[fact.metric.value]
        currency_missing = fact.unit in {"currency", "currency_per_share"} and not fact.currency
        cell_status = fact.selection_status
        cell_reason = (
            "Currency is unknown; the reported value is retained for source "
            "inspection but is not chartable."
            if currency_missing
            else None
            if fact.selection_status == "AVAILABLE"
            else "Reported source conflict or data-quality check."
        )
        row = row_for(
            fact.metric.value,
            definition.display_name,
            fact.statement.value,
            "REPORTED_ACTUAL",
            "Reported actuals",
            fact.currency,
            fact.unit,
        )
        _append_cell(
            row,
            s.FinancialStatementCellRead(
                period_end=end,
                value=None if currency_missing else fact.value,
                status="DATA_CHECK" if currency_missing else cell_status,
                reason=cell_reason,
                selected_source_id=(
                    fact.selected_observation.id
                    if fact.selected_observation and not currency_missing
                    else None
                ),
                source_ids=[item.id for item in fact.observations],
            ),
        )

    for definition in METRIC_DEFINITIONS:
        if not any(row.metric == definition.metric.value for row in rows.values()):
            row = row_for(
                definition.metric.value,
                definition.display_name,
                definition.statement.value,
                "REPORTED_ACTUAL",
                "Reported actuals",
                None,
                definition.canonical_unit,
            )
            row.availability_reason = "No eligible reported observation in this period view."
    for metric in ("EPS", "EBITDA", "FREE_CASH_FLOW"):
        label, statement = FORECAST_METRICS[metric]
        row = row_for(
            metric,
            label,
            statement,
            "REPORTED_ACTUAL",
            "Reported actuals",
            None,
            "currency_per_share" if metric == "EPS" else "currency",
        )
        row.availability_reason = (
            "Not supported as a canonical reported fact; no frontend calculation is synthesized."
        )

    for provider in consensus.providers:
        for period in provider.periods:
            if period.period_type != period_type:
                continue
            observation = period.current_observation
            reason = None
            unit = UNIT_MAP.get(period.unit, period.unit)
            if not provider.selected:
                reason = (
                    "Alternate provider remains separate under the consensus continuity policy."
                )
            elif (
                period.period_end is None or observation is None or observation.observed_at is None
            ):
                reason = (
                    "A trustworthy period end and observation timestamp are required for alignment."
                )
            elif period.currency is None or unit not in {"currency", "currency_per_share"}:
                reason = "Currency or unit basis is unknown; alignment is unavailable."
            if reason:
                limitations.append(
                    s.FinancialStatementLimitationRead(
                        source_name=(
                            f"{provider.provider_id} · {period.metric} · {period.forecast_period}"
                        ),
                        reason=reason,
                        reference_id=observation.id if observation else None,
                    )
                )
                continue
            assert observation is not None and period.period_end is not None
            row = row_for(
                period.metric,
                FORECAST_METRICS[period.metric][0],
                "INCOME_STATEMENT",
                "CONSENSUS",
                provider.provider_id,
                period.currency,
                unit,
                provider.provider_id,
            )
            eligible = observation.data_quality == "PASS" and provider.freshness == "FRESH"
            _append_cell(
                row,
                s.FinancialStatementCellRead(
                    period_end=period.period_end,
                    value=observation.value,
                    status="AVAILABLE" if eligible else "DATA_CHECK",
                    reason=None
                    if eligible
                    else (
                        f"Consensus {provider.freshness}; "
                        f"{observation.quality_reason or observation.data_quality}."
                    ),
                    selected_source_id=observation.id,
                    source_ids=[item.id for item in period.history],
                ),
            )

    for stream in research.streams:
        revision = stream.current_revision
        if revision.status != "PUBLISHED":
            continue
        for forecast in revision.forecasts:
            if forecast.period_type != period_type:
                continue
            if forecast.period_end is None:
                limitations.append(
                    s.FinancialStatementLimitationRead(
                        source_name=(
                            f"{revision.author_id} · {forecast.metric.value} · "
                            f"FY{forecast.fiscal_year}"
                        ),
                        reason=(
                            "An explicit period end is required; "
                            "a fiscal-year number alone is not a calendar date."
                        ),
                        reference_id=forecast.id,
                    )
                )
                continue
            metric = forecast.metric.value
            label, statement = FORECAST_METRICS[metric]
            unit = UNIT_MAP.get(forecast.unit, forecast.unit)
            row = row_for(
                metric,
                label,
                statement,
                "AGENT_FORECAST",
                revision.author_id,
                forecast.currency,
                unit,
                stream.stream_key,
                forecast.scenario.value,
            )
            labels.setdefault(forecast.period_end, set()).add(
                (forecast.fiscal_year, forecast.fiscal_period)
            )
            source_ids = [
                prior.id
                for item in stream.history
                for prior in item.forecasts
                if (
                    prior.metric,
                    prior.period_type,
                    prior.period_end,
                    prior.scenario,
                    prior.currency,
                    prior.unit,
                )
                == (
                    forecast.metric,
                    forecast.period_type,
                    forecast.period_end,
                    forecast.scenario,
                    forecast.currency,
                    forecast.unit,
                )
            ]
            _append_cell(
                row,
                s.FinancialStatementCellRead(
                    period_end=forecast.period_end,
                    value=forecast.value,
                    status="AVAILABLE"
                    if forecast.availability_status == "AVAILABLE"
                    else "DATA_CHECK"
                    if forecast.availability_status == "DATA_CHECK"
                    else "UNAVAILABLE",
                    reason=forecast.availability_reason,
                    selected_source_id=forecast.id,
                    source_ids=source_ids,
                ),
            )

    cutoff = datetime.combine(as_of or date.today(), time.max, UTC)
    for model in session.scalars(
        select(FinancialModel).where(FinancialModel.company_id == company_id)
    ):
        revision = session.scalar(
            select(FinancialModelRevision)
            .where(
                FinancialModelRevision.model_id == model.id,
                FinancialModelRevision.effective_at <= cutoff,
                FinancialModelRevision.recorded_at
                <= (known_at or datetime.max.replace(tzinfo=UTC)),
            )
            .order_by(
                FinancialModelRevision.effective_at.desc(),
                FinancialModelRevision.revision_number.desc(),
            )
            .limit(1)
        )
        if revision:
            limitations.append(
                s.FinancialStatementLimitationRead(
                    source_name=f"{model.model_name} · revision {revision.revision_number}",
                    reason=(
                        "Accepted model projections use ordinal forecast years without an explicit "
                        "fiscal-period anchor. Inspect method-specific projections in Valuation."
                    ),
                    reference_id=revision.id,
                )
            )
    limitations.append(
        s.FinancialStatementLimitationRead(
            source_name="Growth & ratios",
            reason=(
                "No canonical growth/ratio or reported EPS, EBITDA, FCF calculation "
                "is implemented. "
                "Missing quarters and year-to-date cash-flow facts are not synthesized."
            ),
        )
    )
    historical_ends = sorted(actual_ends)[-period_limit:]
    forecast_ends = sorted(
        {
            cell.period_end
            for row in rows.values()
            if row.source_kind != "REPORTED_ACTUAL"
            for cell in row.cells
        }
    )
    # Keep a bounded extension beyond the reported window; existing periods can
    # contain actuals and forecasts in independent, explicitly labelled rows.
    first_end = historical_ends[0] if historical_ends else date.min
    extra_ends = [end for end in forecast_ends if end >= first_end and end not in actual_ends][:8]
    ends = sorted(set(historical_ends + extra_ends))
    for row in rows.values():
        row.cells = sorted(
            [cell for cell in row.cells if cell.period_end in ends],
            key=lambda item: item.period_end,
        )
    columns = []
    for end in ends:
        candidates = labels.get(end, set())
        year, column_fp = next(iter(candidates)) if len(candidates) == 1 else (None, None)
        columns.append(
            s.FinancialStatementColumnRead(
                period_end=end,
                label=_label(year, column_fp, end, period_type),
                fiscal_year=year,
                fiscal_period=column_fp,
                is_forecast=end not in actual_ends,
            )
        )
    return s.CompanyFinancialStatementsRead(
        company_id=company_id,
        period_type=period_type,
        as_of=as_of,
        known_at=known_at,
        periods=columns,
        rows=list(rows.values()),
        reported_periods=[item for item in included_facts if item.period_end.date() in ends],
        consensus=consensus,
        research=research,
        limitations=limitations,
        latest_observed_at=facts.latest_observed_at,
    )
