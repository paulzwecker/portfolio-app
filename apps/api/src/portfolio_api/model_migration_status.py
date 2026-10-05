"""Read-only Company Explorer status derived from the reviewed inventory and receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.domain import schemas
from portfolio_api.domain.models import (
    Company,
    FinancialModel,
    FinancialModelMigrationAssessment,
    FinancialModelRevision,
    Listing,
    ModelOutputSnapshot,
    Security,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_PATH = (
    REPOSITORY_ROOT / "docs" / "reconciliation" / "model-migration-inventory-2026-10-05.json"
)


def _inventory_rows() -> list[dict[str, Any]]:
    if not INVENTORY_PATH.exists():
        return []
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], payload.get("models", []))


def _comparison_count(report: dict[str, Any], field: str, key: str) -> int | None:
    group = report.get(field)
    if not isinstance(group, dict):
        return None
    value = group.get(key)
    return value if isinstance(value, int) else None


def company_model_migration_status(
    session: Session, company_id: UUID
) -> schemas.CompanyFinancialModelMigrationRead:
    company = session.get(Company, company_id)
    if company is None:
        raise ValueError("Company not found")

    tickers = set(
        session.scalars(
            select(Listing.ticker)
            .join(Security, Listing.security_id == Security.id)
            .where(Security.company_id == company_id)
        ).all()
    )
    output_rows = session.scalars(
        select(ModelOutputSnapshot).where(
            ModelOutputSnapshot.company_id == company_id,
            ModelOutputSnapshot.snapshot_kind == "CURRENT_CONTRACT",
        )
    ).all()
    outputs_by_key = {row.model_key: row for row in output_rows}
    native_rows = session.scalars(
        select(FinancialModel).where(FinancialModel.company_id == company_id)
    ).all()
    native_by_key = {row.source_model_key: row for row in native_rows if row.source_model_key}
    native_ids = [row.id for row in native_rows]
    assessment_rows = (
        session.scalars(
            select(FinancialModelMigrationAssessment)
            .where(FinancialModelMigrationAssessment.model_id.in_(native_ids))
            .order_by(FinancialModelMigrationAssessment.recorded_at.desc())
        ).all()
        if native_ids
        else []
    )
    assessments_by_model: dict[UUID, FinancialModelMigrationAssessment] = {}
    for assessment in assessment_rows:
        assessments_by_model.setdefault(assessment.model_id, assessment)

    items: list[schemas.CompanyFinancialModelMigrationItemRead] = []
    for row in _inventory_rows():
        ticker = row.get("canonical_ticker")
        model_key = str(row["model_tab"])
        if ticker not in tickers:
            continue
        native = native_by_key.get(model_key)
        output = outputs_by_key.get(model_key)
        migration_assessment = assessments_by_model.get(native.id) if native is not None else None
        parity_status = migration_assessment.status if migration_assessment is not None else None
        if native is not None:
            representation_status = (
                "NATIVE_EDITABLE"
                if parity_status in (None, "PARITY_PASS")
                else "NATIVE_WITH_PARITY_ISSUE"
            )
        elif row["migration_status"] == "UNSUPPORTED_METHOD":
            representation_status = "UNSUPPORTED_LEGACY"
        elif row["lifecycle"] == "DROP":
            representation_status = "LEGACY_ONLY"
        elif output is not None:
            representation_status = "IMPORTED_OUTPUT_ONLY"
        else:
            representation_status = "NOT_IMPORTED"

        report = (
            cast(dict[str, Any], migration_assessment.report)
            if migration_assessment is not None
            else {}
        )
        current_revision = (
            session.get(FinancialModelRevision, native.current_revision_id)
            if native is not None and native.current_revision_id is not None
            else None
        )
        items.append(
            schemas.CompanyFinancialModelMigrationItemRead(
                model_key=model_key,
                company_name=str(row["company_name"]),
                canonical_ticker=ticker,
                lifecycle=str(row["lifecycle"]),
                methodology_family=str(row["methodology_family"]),
                model_currency=row.get("model_currency"),
                inventory_status=row["migration_status"],
                representation_status=representation_status,
                output_snapshot_available=output is not None,
                output_contract_status=(
                    output.contract_status
                    if output is not None
                    else str(row["current_output_status"])
                ),
                native_model_id=native.id if native is not None else None,
                native_revision_number=current_revision.revision_number
                if current_revision is not None
                else None,
                parity_status=parity_status,
                projections_compared=_comparison_count(
                    report, "projection_reconciliation", "compared"
                ),
                projections_passed=_comparison_count(report, "projection_reconciliation", "passed"),
                outputs_compared=_comparison_count(report, "output_reconciliation", "compared"),
                outputs_passed=_comparison_count(report, "output_reconciliation", "passed"),
                blockers=list(row.get("blockers", [])),
                legacy_return_semantics=report.get("legacy_return_semantics"),
            )
        )

    return schemas.CompanyFinancialModelMigrationRead(
        company_id=company_id,
        inventory_available=INVENTORY_PATH.exists(),
        models=items,
    )
