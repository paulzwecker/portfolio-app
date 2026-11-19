"""Validated operating-driver paths published alongside accepted model revisions."""

import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.company_observations import (
    CompanyMetricDefinition,
    FinancialModelDriverProjection,
)
from portfolio_api.domain import schemas as s
from portfolio_api.domain.models import FinancialModel


def _decimal(value: Decimal | str) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _canonical(value: dict[str, object]) -> dict[str, object]:
    """Comparable semantic content, excluding database identity and recorded time."""
    data = dict(value)
    data["value"] = _decimal(str(data["value"]))
    data["scale"] = _decimal(str(data["scale"]))
    return data


def validate_driver_inputs(
    session: Session,
    model: FinancialModel,
    items: list[s.FinancialModelDriverProjectionInput],
) -> dict[str, CompanyMetricDefinition]:
    """Reject undefined, cross-company or incompatible operating metric semantics."""
    definitions: dict[str, CompanyMetricDefinition] = {}
    for item in items:
        if item.metric_key not in definitions:
            definition = session.scalar(
                select(CompanyMetricDefinition).where(
                    CompanyMetricDefinition.metric_key == item.metric_key
                )
            )
            if definition is None:
                raise ValueError(f"Model driver metric {item.metric_key} is not registered")
            if definition.company_id not in (None, model.company_id):
                raise ValueError("Model driver belongs to a different company")
            if (
                not definition.active
                or definition.deprecated_at is not None
                or not definition.model_driver_allowed
            ):
                raise ValueError("Metric definition does not allow new model drivers")
            definitions[item.metric_key] = definition
        definition = definitions[item.metric_key]
        if (
            item.unit != definition.canonical_unit
            or item.scale != definition.canonical_scale
            or set(item.scope_json).difference(definition.scope_dimensions)
            or (definition.currency_policy == "NONE" and item.currency is not None)
            or (definition.currency_policy == "REQUIRED" and item.currency is None)
        ):
            raise ValueError(
                "Model driver unit, scale, scope or currency conflicts with definition"
            )
    return definitions


def accepted_driver_snapshot(
    session: Session, model_id: UUID, revision_id: UUID
) -> list[dict[str, object]]:
    """Only the accepted model revision's driver rows, never guessed from financials."""
    rows = session.execute(
        select(FinancialModelDriverProjection, CompanyMetricDefinition)
        .join(
            CompanyMetricDefinition,
            FinancialModelDriverProjection.metric_definition_id == CompanyMetricDefinition.id,
        )
        .where(
            FinancialModelDriverProjection.model_id == model_id,
            FinancialModelDriverProjection.revision_id == revision_id,
        )
    ).all()
    result = []
    for row, definition in rows:
        external = row.external_driver_id.removeprefix(f"{revision_id}:")
        result.append(
            _canonical(
                {
                    "external_driver_id": external,
                    "metric_key": definition.metric_key,
                    "scenario": row.scenario,
                    "forecast_year": row.forecast_year,
                    "period_type": row.period_type,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "value": row.value,
                    "value_qualifier": row.value_qualifier,
                    "unit": row.unit,
                    "scale": row.scale,
                    "currency": row.currency,
                    "basis": row.basis,
                    "scope_json": row.scope_json,
                    "rationale": row.rationale,
                }
            )
        )
    return sorted(result, key=lambda item: json.dumps(item, sort_keys=True))


def proposed_driver_snapshot(
    items: list[s.FinancialModelDriverProjectionInput],
) -> list[dict[str, object]]:
    rows = [_canonical(item.model_dump(mode="json")) for item in items]
    return sorted(rows, key=lambda item: json.dumps(item, sort_keys=True))


def publish_model_drivers(
    session: Session,
    model: FinancialModel,
    revision_id: UUID,
    items: list[s.FinancialModelDriverProjectionInput],
) -> None:
    """One transaction with accepted model revision. Never overwrite prior rows."""
    definitions = validate_driver_inputs(session, model, items)
    for item in items:
        session.add(
            FinancialModelDriverProjection(
                external_driver_id=f"{revision_id}:{item.external_driver_id}",
                model_id=model.id,
                revision_id=revision_id,
                scenario=item.scenario,
                metric_definition_id=definitions[item.metric_key].id,
                forecast_year=item.forecast_year,
                period_type=item.period_type,
                period_start=item.period_start,
                period_end=item.period_end,
                value=item.value,
                value_qualifier=item.value_qualifier,
                unit=item.unit,
                scale=item.scale,
                currency=item.currency,
                basis=item.basis,
                scope_json=item.scope_json,
                rationale=item.rationale,
            )
        )
    session.flush()
