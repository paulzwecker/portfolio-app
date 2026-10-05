"""Deterministic import of normalized cached model outputs and recorded history.

This module reads the frozen Model Output Contract and the explicit revision ledger. It
never evaluates spreadsheet formulas or imports assumptions/projections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import (
    Company,
    Listing,
    ModelOutputImportBatch,
    ModelOutputSnapshot,
    ModelOutputSnapshotKind,
    Security,
    now,
)
from portfolio_api.legacy_import import Workbook
from portfolio_api.settings import Settings

NAMESPACE = UUID("3d31ab8a-c035-4632-b96e-33f121b2e104")
DEFAULT_WORKBOOK = Path("reference/workbook/Portfolio_Watchlist.xlsx")
CONTRACT_VERSION = "v1"
NUMERIC_FIELDS = (
    "bear_fv",
    "base_fv",
    "bull_fv",
    "bear_probability",
    "base_probability",
    "bull_probability",
    "weighted_fv",
    "weighted_upside",
    "expected_cash_flow_irr",
    "hurdle",
    "expected_excess",
    "forward_fundamental_cagr",
)
CONTRACT_ROWS = {
    "bear_fv": 4,
    "base_fv": 5,
    "bull_fv": 6,
    "bear_probability": 7,
    "base_probability": 8,
    "bull_probability": 9,
    "weighted_fv": 10,
    "weighted_upside": 11,
    "expected_cash_flow_irr": 12,
    "hurdle": 13,
    "expected_excess": 14,
    "forward_fundamental_cagr": 15,
}
HISTORY_COLUMNS = {
    "forward_fundamental_cagr": "M",
    "bear_fv": "N",
    "base_fv": "O",
    "bull_fv": "P",
    "weighted_fv": "Q",
    "expected_cash_flow_irr": "R",
    "hurdle": "S",
    "expected_excess": "T",
}
REPRESENTATIVE_NATIVE_OUTPUT_CELLS = {
    # These three model archetypes are the representative contract audit agreed in
    # docs/migration.md: DCF, residual-income, and owner-cash-flow.
    "P-GOOGL": {"bear_fv": "E4", "base_fv": "F4", "bull_fv": "G4"},
    "W-HDFC": {"bear_fv": "B77", "base_fv": "C77", "bull_fv": "D77"},
    "W-TOST": {"bear_fv": "M46", "base_fv": "M47", "bull_fv": "M48"},
}
CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _stable_id(key: str) -> UUID:
    return uuid5(NAMESPACE, key)


def _cell_values(row: dict[str, Any]) -> dict[str, str | None]:
    return {key: cell.value for key, cell in row.items()}


def _cell_value(cells: dict[str, Any], address: str) -> str | None:
    cell = cells.get(address)
    return cell.value if cell is not None else None


def _source_ref(workbook: Workbook, sheet: str, cells: str) -> str:
    return f"{workbook.path.name}:{sheet}!{cells}#sha256:{workbook.sha256}"


def _decimal(raw_value: str | None) -> Decimal | None:
    if raw_value is None or not raw_value.strip():
        return None
    raw = raw_value.strip()
    try:
        value = Decimal(raw[:-1].strip()) / Decimal(100) if raw.endswith("%") else Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _timestamp(raw_value: str | None) -> datetime | None:
    if raw_value is None or not raw_value.strip():
        return None
    normalized = raw_value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _normalize_label(raw_value: str | None) -> str:
    if raw_value is None:
        return ""
    value = re.sub(r"\s*/\s*share\b", "", raw_value.strip(), flags=re.IGNORECASE)
    value = re.sub(r"\b(bear|base|bull)\s+prob\b", r"\1 probability", value, flags=re.I)
    value = re.sub(r"\bweighted\s+fv\b", "weighted fair value", value, flags=re.I)
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    aliases = {
        "expectedcfirr": "expectedcashflowirr",
        "fundamentalcagr": "forwardfundamentalcagr",
        "durability": "10ydurability",
    }
    return aliases.get(normalized, normalized)


def _expected_contract_labels(workbook: Workbook) -> dict[int, str]:
    result: dict[int, str] = {}
    for source_row, contract_row in zip(range(5, 23), range(3, 21), strict=True):
        cell = workbook.cell("Model Contract", f"A{source_row}")
        if cell.value is not None:
            result[contract_row] = _normalize_label(cell.value)
    return result


def _explicit_currency(cells: dict[str, Any]) -> tuple[str | None, str | None]:
    """Read only a documented currency label followed by its adjacent ISO code."""
    label_pattern = re.compile(
        r"^(valuation currency|accounting\s*/\s*model currency|model\s*/\s*accounting currency|"
        r"model currency|accounting currency|home currency|valuation\s*/\s*accounting currency|"
        r"currency)$",
        re.IGNORECASE,
    )
    found: dict[str, str] = {}
    for address, cell in cells.items():
        label = cell.value.strip() if cell.value else ""
        if not label_pattern.fullmatch(label):
            continue
        match = CELL_RE.fullmatch(address)
        if match is None:
            continue
        column = 0
        for character in match.group(1):
            column = column * 26 + ord(character) - 64
        row = int(match.group(2))
        for offset in (1, 2, 3):
            number = column + offset
            letters = ""
            while number:
                number, remainder = divmod(number - 1, 26)
                letters = chr(remainder + 65) + letters
            candidate = cells.get(f"{letters}{row}")
            value = candidate.value.strip().upper() if candidate and candidate.value else ""
            if re.fullmatch(r"[A-Z]{3}", value):
                found[value] = address
                break
    if len(found) == 1:
        currency = next(iter(found))
        return currency, next(iter(found.values()))
    return None, None


def _empty_outputs() -> dict[str, Decimal | None]:
    return dict.fromkeys(NUMERIC_FIELDS)


def _read_output_values(
    *,
    cells: dict[str, Any],
    coordinate: Callable[[int], str],
    source: str,
    validate_contract_labels: bool,
    expected_labels: dict[int, str],
) -> tuple[dict[str, Decimal | None], list[dict[str, str]]]:
    outputs = _empty_outputs()
    issues: list[dict[str, str]] = []
    if validate_contract_labels:
        for row_number, expected in expected_labels.items():
            actual = cells.get(f"AZ{row_number}")
            if _normalize_label(actual.value if actual else None) != expected:
                issues.append(
                    {
                        "field": "contract_labels",
                        "reason": f"Contract label at AZ{row_number} does not match v1.",
                        "raw_value": actual.value if actual and actual.value else "",
                        "source": f"{source}!AZ{row_number}",
                    }
                )
        if issues:
            return outputs, issues
    for field_name, row_number in CONTRACT_ROWS.items():
        address = coordinate(row_number)
        cell = cells.get(address)
        raw_value = cell.value if cell else None
        value = _decimal(raw_value)
        if raw_value is None or not raw_value.strip():
            continue
        if value is None:
            issues.append(
                {
                    "field": field_name,
                    "reason": "Cached contract value is not a finite decimal.",
                    "raw_value": raw_value,
                    "source": f"{source}!{address}",
                }
            )
            continue
        if field_name.endswith("_probability") and not Decimal(0) <= value <= Decimal(1):
            issues.append(
                {
                    "field": field_name,
                    "reason": "Scenario probability is outside the inclusive 0 to 1 range.",
                    "raw_value": raw_value,
                    "source": f"{source}!{address}",
                }
            )
            continue
        outputs[field_name] = value
    return outputs, issues


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _quality(
    outputs: dict[str, Decimal | None], issues: list[dict[str, str]], *, available: bool
) -> str:
    if not available:
        return "UNAVAILABLE"
    if issues:
        return "DATA_CHECK"
    return "COMPLETE" if all(outputs[field] is not None for field in NUMERIC_FIELDS) else "PARTIAL"


def _company_crosswalk(
    workbook: Workbook, session: Session, issues: list[dict[str, str]]
) -> dict[str, tuple[str, UUID]]:
    source_names: dict[str, str] = {}
    for _row_number, row in workbook.rows("Universe Registry", 5):
        values = _cell_values(row)
        ticker = (values.get("A") or "").strip().upper()
        name = (values.get("B") or "").strip()
        if ticker and name:
            source_names[ticker] = name

    companies_by_name: dict[str, list[Company]] = {}
    for company in session.scalars(select(Company).where(Company.is_demo.is_(False))):
        companies_by_name.setdefault(company.name, []).append(company)
    listing_company_ids: dict[str, set[UUID]] = {}
    for listing, security in session.execute(
        select(Listing, Security).join(Security, Security.id == Listing.security_id)
    ):
        if security.company_id is not None:
            listing_company_ids.setdefault(listing.ticker.strip().upper(), set()).add(
                security.company_id
            )

    result: dict[str, tuple[str, UUID]] = {}
    for ticker, name in source_names.items():
        candidates = companies_by_name.get(name, [])
        if len(candidates) == 1:
            result[ticker] = name, candidates[0].id
            continue
        source_listing_ids = listing_company_ids.get(ticker, set())
        matching = [candidate for candidate in candidates if candidate.id in source_listing_ids]
        if len(matching) == 1:
            result[ticker] = name, matching[0].id
            continue
        issues.append(
            {
                "code": "COMPANY_IDENTITY_UNRESOLVED",
                "severity": "ERROR",
                "source": f"Universe Registry ticker {ticker}",
                "message": (
                    f"No unique non-demo application company matches {name!r}; no model output "
                    "was attached to a company."
                ),
            }
        )
    return result


@dataclass
class ImportPlan:
    workbook: Workbook
    observed_at: datetime
    source_digest: str
    batch_id: UUID
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def report(self, *, status: str = "DRY_RUN") -> dict[str, Any]:
        return {
            "status": status,
            "observed_at": self.observed_at.isoformat(),
            "effective_time_policy": (
                "Only the Model Revision History As-of Timestamp is treated as effective time. "
                "The current Model Output Contract has no effective timestamp; its observed time "
                "is recorded separately and is not substituted for effective time."
            ),
            "source": self.workbook.path.name,
            "workbook_sha256": self.workbook.sha256,
            "source_digest": self.source_digest,
            "batch_id": str(self.batch_id),
            **self.summary,
            "candidate_snapshot_count": len(self.snapshots),
            "unresolved_issues": self.issues,
        }


def build_import(
    session: Session, path: Path = DEFAULT_WORKBOOK, observed_at: datetime | None = None
) -> ImportPlan:
    observed = observed_at or now()
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("Observed time must include a timezone offset")
    workbook = Workbook.read(
        path,
        lambda name: (
            name in {"Universe Registry", "Model Contract", "Model Revision History"}
            or name.startswith(("P-", "W-"))
        ),
    )
    digest = hashlib.sha256(
        f"model-output-contract-v1:{workbook.sha256}".encode("ascii")
    ).hexdigest()
    batch_id = _stable_id(f"batch:{digest}")
    issues: list[dict[str, str]] = []
    crosswalk = _company_crosswalk(workbook, session, issues)
    expected_labels = _expected_contract_labels(workbook)
    snapshots: list[dict[str, Any]] = []
    contract_statuses: Counter[str] = Counter()
    currency_counts: Counter[str] = Counter()
    output_counts: Counter[str] = Counter()
    contract_discovered = 0
    contract_published = 0
    history_source_rows = 0
    history_without_outputs = 0
    history_bad_timestamp = 0
    history_invalid_values = 0
    source_contract_statuses: Counter[str] = Counter()

    model_tabs = {
        name: cells for name, cells in workbook.sheets.items() if name.startswith(("P-", "W-"))
    }
    for model_key, cells in sorted(model_tabs.items()):
        suffix_ticker = model_key[2:].strip().upper()
        source_ticker = (_cell_value(cells, "BA3") or "").strip().upper()
        raw_status = (_cell_value(cells, "BA20") or "").strip()
        status_key = raw_status.upper()
        if status_key == "PASS":
            contract_status = "PASS"
        elif status_key.startswith("NOT MAPPED"):
            contract_status = "NOT_MAPPED"
        elif not raw_status:
            contract_status = "NO_CONTRACT"
        else:
            contract_status = "DATA_CHECK"
        source_contract_statuses[contract_status] += 1

        value_issues: list[dict[str, str]] = []
        if contract_status == "PASS" and (source_ticker != suffix_ticker or not source_ticker):
            identity_issue = {
                "field": "ticker",
                "reason": "Published ticker does not match the source model-tab identity.",
                "raw_value": source_ticker,
                "source": f"{model_key}!BA3",
            }
            value_issues.append(identity_issue)
            issues.append(
                {
                    "code": "CONTRACT_TICKER_MISMATCH",
                    "severity": "ERROR",
                    "source": f"{model_key}!BA3",
                    "message": (
                        f"Published ticker {source_ticker!r} does not match model-tab identity "
                        f"{suffix_ticker!r}; numeric contract values were withheld."
                    ),
                }
            )
            contract_status = "DATA_CHECK"
        outputs: dict[str, Decimal | None] = _empty_outputs()
        available = contract_status == "PASS"
        if available:
            outputs, parsed_issues = _read_output_values(
                cells=cells,
                coordinate=lambda row_number: f"BA{row_number}",
                source=model_key,
                validate_contract_labels=True,
                expected_labels=expected_labels,
            )
            label_issues = [item for item in parsed_issues if item["field"] == "contract_labels"]
            value_issues = [item for item in parsed_issues if item["field"] != "contract_labels"]
            if label_issues:
                issues.append(
                    {
                        "code": "CONTRACT_LAYOUT_MISMATCH",
                        "severity": "ERROR",
                        "source": model_key,
                        "message": (
                            "Published output block labels do not align with Model Contract v1."
                        ),
                    }
                )
                contract_status = "DATA_CHECK"
                outputs = _empty_outputs()
                available = False
                value_issues = label_issues
            else:
                issues.extend(
                    {
                        "code": "OUTPUT_VALUE_INVALID",
                        "severity": "WARNING",
                        "source": item["source"],
                        "message": (
                            f"{item['field']}: {item['reason']} Raw value={item['raw_value']!r}"
                        ),
                    }
                    for item in value_issues
                )
        model_currency, currency_cell = _explicit_currency(cells)
        currency_status = "DOCUMENTED" if model_currency else "UNKNOWN"
        currency_counts[currency_status] += 1
        if not model_currency and contract_status == "PASS":
            issues.append(
                {
                    "code": "MODEL_CURRENCY_UNDOCUMENTED",
                    "severity": "WARNING",
                    "source": model_key,
                    "message": (
                        "No explicit model-currency label and code were found; "
                        "currency remains null."
                    ),
                }
            )
        company_ticker = source_ticker if source_ticker == suffix_ticker else suffix_ticker
        identity = crosswalk.get(company_ticker)
        if identity is None:
            issues.append(
                {
                    "code": "MODEL_COMPANY_UNRESOLVED",
                    "severity": "ERROR" if contract_status != "NO_CONTRACT" else "WARNING",
                    "source": model_key,
                    "message": (
                        f"No exact source-to-application identity for {company_ticker!r}; "
                        "no model snapshot was created."
                    ),
                }
            )
            continue
        _, company_id = identity
        source = _source_ref(workbook, model_key, "AZ3:BA20")
        quality = _quality(outputs, value_issues, available=available)
        if contract_status in {"NOT_MAPPED", "NO_CONTRACT"}:
            quality = "UNAVAILABLE"
        raw_contract = {
            "model_key": model_key,
            "ticker": source_ticker,
            "status": raw_status,
            "labels": [_cell_value(cells, f"AZ{row}") for row in range(3, 21)],
            "currency": model_currency,
            "currency_cell": currency_cell,
            "outputs": {
                key: str(value) if value is not None else None for key, value in outputs.items()
            },
            "field_issues": value_issues,
            "model_status": _cell_value(cells, "BA19"),
        }
        fingerprint = _fingerprint(raw_contract)
        snapshot_key = f"CONTRACT:{fingerprint}"
        snapshot = {
            "id": _stable_id(f"snapshot:{company_ticker}:{model_key}:{snapshot_key}"),
            "company_id": company_id,
            "batch_id": batch_id,
            "model_key": model_key,
            "snapshot_key": snapshot_key,
            "source_fingerprint": fingerprint,
            "snapshot_kind": ModelOutputSnapshotKind.CURRENT_CONTRACT,
            "contract_version": CONTRACT_VERSION if raw_status else None,
            "contract_status": contract_status,
            "output_quality": quality,
            "model_currency": model_currency,
            "currency_status": currency_status,
            "currency_source_ref": (
                _source_ref(workbook, model_key, f"{currency_cell}:{currency_cell}")
                if currency_cell
                else None
            ),
            "model_status": _cell_value(cells, "BA19") or None,
            "effective_at": None,
            "recorded_at": observed,
            "actor": "IMPORT",
            "source": source,
            "source_revision_id": None,
            "revision_source": None,
            "revision_type": None,
            "source_actor": None,
            "rationale": None,
            "evidence": None,
            "notes": None,
            "field_issues": value_issues,
            **outputs,
        }
        snapshots.append(snapshot)
        contract_discovered += 1
        contract_statuses[contract_status] += 1
        contract_published += contract_status == "PASS" and quality != "UNAVAILABLE"
        for field_name, value in outputs.items():
            output_counts[field_name] += value is not None

    for row_number, row in workbook.rows("Model Revision History", 4):
        values = _cell_values(row)
        revision_id = (values.get("A") or "").strip()
        if not revision_id:
            continue
        history_source_rows += 1
        ticker = (values.get("C") or "").strip().upper()
        identity = crosswalk.get(ticker)
        if identity is None:
            issues.append(
                {
                    "code": "HISTORY_COMPANY_UNRESOLVED",
                    "severity": "ERROR",
                    "source": f"Model Revision History!A{row_number}:Z{row_number}",
                    "message": (
                        f"No exact source-to-application identity for {ticker!r}; row withheld."
                    ),
                }
            )
            continue
        output_raw = {name: values.get(column) for name, column in HISTORY_COLUMNS.items()}
        if not any(value is not None and value.strip() for value in output_raw.values()):
            history_without_outputs += 1
            continue
        outputs = _empty_outputs()
        history_field_issues: list[dict[str, str]] = []
        for field_name, raw_value in output_raw.items():
            if raw_value is None or not raw_value.strip():
                continue
            value = _decimal(raw_value)
            if value is None:
                history_invalid_values += 1
                history_field_issues.append(
                    {
                        "field": field_name,
                        "reason": "Recorded revision value is not a finite decimal.",
                        "raw_value": raw_value,
                        "source": (
                            f"Model Revision History!{HISTORY_COLUMNS[field_name]}{row_number}"
                        ),
                    }
                )
                issues.append(
                    {
                        "code": "HISTORY_OUTPUT_VALUE_INVALID",
                        "severity": "WARNING",
                        "source": (
                            f"Model Revision History!{HISTORY_COLUMNS[field_name]}{row_number}"
                        ),
                        "message": (
                            f"{field_name}: invalid recorded numeric value {raw_value!r}; "
                            "the snapshot field remains null."
                        ),
                    }
                )
            else:
                outputs[field_name] = value
        effective = _timestamp(values.get("B"))
        if effective is None:
            history_bad_timestamp += 1
            history_field_issues.append(
                {
                    "field": "effective_at",
                    "reason": (
                        "Recorded As-of Timestamp is missing or invalid; effective time remains "
                        "unknown."
                    ),
                    "raw_value": values.get("B") or "",
                    "source": f"Model Revision History!B{row_number}",
                }
            )
            issues.append(
                {
                    "code": "HISTORY_EFFECTIVE_TIME_INVALID",
                    "severity": "WARNING",
                    "source": f"Model Revision History!B{row_number}",
                    "message": (
                        "Invalid or missing source timestamp; effective time remains unknown."
                    ),
                }
            )
        model_key = (values.get("E") or "").strip() or f"LEGACY:{ticker}"
        source = _source_ref(workbook, "Model Revision History", f"A{row_number}:Z{row_number}")
        source_model_cells = workbook.sheets.get(model_key, {})
        currency, currency_cell = _explicit_currency(source_model_cells)
        currency_status = "DOCUMENTED" if currency else "UNKNOWN"
        _, company_id = identity
        content_payload = {
            "revision_id": revision_id,
            "row": values,
            "outputs": {
                key: str(value) if value is not None else None for key, value in outputs.items()
            },
            "field_issues": history_field_issues,
            "model_currency": currency,
        }
        fingerprint = _fingerprint(content_payload)
        snapshot_key = f"LEGACY:{revision_id}"
        quality = _quality(outputs, history_field_issues, available=True)
        # Blank outputs are intentional and remain null. An invalid nonblank source cell
        # yields DATA_CHECK while the raw value and exact source cell stay in field_issues.
        snapshot = {
            "id": _stable_id(f"snapshot:{ticker}:{model_key}:{snapshot_key}"),
            "company_id": company_id,
            "batch_id": batch_id,
            "model_key": model_key,
            "snapshot_key": snapshot_key,
            "source_fingerprint": fingerprint,
            "snapshot_kind": ModelOutputSnapshotKind.LEGACY_REVISION,
            "contract_version": None,
            "contract_status": "HISTORICAL_ONLY",
            "output_quality": quality,
            "model_currency": currency,
            "currency_status": currency_status,
            "currency_source_ref": (
                _source_ref(workbook, model_key, f"{currency_cell}:{currency_cell}")
                if currency_cell
                else None
            ),
            "model_status": values.get("U") or None,
            "effective_at": effective,
            "recorded_at": observed,
            "actor": "IMPORT",
            "source": source,
            "source_revision_id": revision_id,
            "revision_source": values.get("G") or None,
            "revision_type": values.get("H") or None,
            "source_actor": values.get("Y") or None,
            "rationale": values.get("W") or None,
            "evidence": values.get("X") or None,
            "notes": values.get("Z") or None,
            "field_issues": history_field_issues,
            **outputs,
        }
        snapshots.append(snapshot)
        for field_name, value in outputs.items():
            output_counts[field_name] += value is not None

    representative_comparisons: list[dict[str, str]] = []
    representative_mismatches: list[dict[str, str]] = []
    for model_key, field_cells in REPRESENTATIVE_NATIVE_OUTPUT_CELLS.items():
        contract_snapshot = next(
            (
                snapshot
                for snapshot in snapshots
                if snapshot["snapshot_kind"] == ModelOutputSnapshotKind.CURRENT_CONTRACT
                and snapshot["model_key"] == model_key
            ),
            None,
        )
        source_cells = model_tabs.get(model_key)
        for field_name, address in field_cells.items():
            expected = _decimal(_cell_value(source_cells or {}, address))
            actual = contract_snapshot.get(field_name) if contract_snapshot else None
            comparison = {
                "model_key": model_key,
                "field": field_name,
                "native_cell": address,
                "native_value": str(expected) if expected is not None else "",
                "contract_value": str(actual) if actual is not None else "",
            }
            representative_comparisons.append(comparison)
            if expected is None or actual != expected:
                representative_mismatches.append(comparison)
                issues.append(
                    {
                        "code": "REPRESENTATIVE_OUTPUT_MISMATCH",
                        "severity": "ERROR",
                        "source": (
                            f"{model_key}!{address} vs {model_key}!BA{CONTRACT_ROWS[field_name]}"
                        ),
                        "message": (
                            f"{field_name} cached source output does not reconcile: "
                            f"native={expected!s}, contract={actual!s}."
                        ),
                    }
                )

    summary: dict[str, Any] = {
        "counts": {
            "model_tabs": len(model_tabs),
            "current_contract_rows_matched": contract_discovered,
            "current_outputs_published": int(contract_published),
            "source_contract_status": dict(source_contract_statuses),
            "current_contract_status": dict(contract_statuses),
            "legacy_history_rows": history_source_rows,
            "legacy_history_snapshots": sum(
                snapshot["snapshot_kind"] == ModelOutputSnapshotKind.LEGACY_REVISION
                for snapshot in snapshots
            ),
            "legacy_history_rows_without_output_values": history_without_outputs,
            "legacy_history_rows_with_unknown_effective_time": history_bad_timestamp,
            "legacy_history_invalid_numeric_cells": history_invalid_values,
        },
        "model_currency_coverage": dict(currency_counts),
        "non_null_output_values": dict(output_counts),
        "field_reconciliation": {
            "method": (
                "Exact Decimal comparison of cached contract cells and nine representative "
                "native model cells; history fields are ingested as recorded. No formulas "
                "evaluated."
            ),
            "representative_comparisons": representative_comparisons,
            "representative_comparison_count": len(representative_comparisons),
            "mismatches": len(representative_mismatches),
            "mismatch_details": representative_mismatches,
            "source_issue_count": 0,
        },
        "ownership_exclusions": [
            (
                "Lifecycle and 10Y Durability / Compounder Quality are read from their canonical "
                "domains, not model snapshots."
            ),
            "Current price, holdings, targets, assumptions and projections are not imported.",
        ],
    }
    summary["field_reconciliation"]["source_issue_count"] = sum(
        1 for item in issues if item["severity"] in {"ERROR", "WARNING"}
    )
    return ImportPlan(
        workbook=workbook,
        observed_at=observed.astimezone(UTC),
        source_digest=digest,
        batch_id=batch_id,
        snapshots=snapshots,
        issues=issues,
        summary=summary,
    )


def apply_import(session: Session, plan: ImportPlan) -> dict[str, Any]:
    reconciliation = plan.summary.get("field_reconciliation", {})
    if reconciliation.get("mismatches", 0):
        raise ValueError("Model output import has representative source mismatches")
    existing_batch = session.scalar(
        select(ModelOutputImportBatch).where(
            ModelOutputImportBatch.source_digest == plan.source_digest
        )
    )
    if existing_batch is not None:
        stored = existing_batch.reconciliation
        return {
            **(stored if isinstance(stored, dict) else plan.report()),
            "status": "ALREADY_APPLIED",
            "batch_id": str(existing_batch.id),
            "persisted_snapshots_added": 0,
            "identical_snapshots_reused": len(plan.snapshots),
        }

    report = plan.report(status="APPLIED")
    batch = ModelOutputImportBatch(
        id=plan.batch_id,
        source_digest=plan.source_digest,
        workbook_sha256=plan.workbook.sha256,
        observed_at=plan.observed_at,
        recorded_at=plan.observed_at,
        reconciliation=report,
    )
    session.add(batch)
    session.flush()

    added = 0
    reused = 0
    source_conflicts: list[str] = []
    for values in plan.snapshots:
        existing = session.scalar(
            select(ModelOutputSnapshot).where(
                ModelOutputSnapshot.company_id == values["company_id"],
                ModelOutputSnapshot.model_key == values["model_key"],
                ModelOutputSnapshot.snapshot_key == values["snapshot_key"],
            )
        )
        if existing is not None:
            if existing.source_fingerprint != values["source_fingerprint"]:
                source_conflicts.append(
                    f"{values['model_key']}:{values['snapshot_key']} changed under the same "
                    "source revision key"
                )
            else:
                reused += 1
            continue
        session.add(ModelOutputSnapshot(**values))
        added += 1
    if source_conflicts:
        raise ValueError(
            "Source changed an existing immutable revision: " + "; ".join(source_conflicts)
        )
    session.flush()

    mismatches: list[dict[str, str]] = []
    compared_values = 0
    for expected in plan.snapshots:
        stored = session.scalar(
            select(ModelOutputSnapshot).where(
                ModelOutputSnapshot.company_id == expected["company_id"],
                ModelOutputSnapshot.model_key == expected["model_key"],
                ModelOutputSnapshot.snapshot_key == expected["snapshot_key"],
            )
        )
        if stored is None:
            mismatches.append(
                {
                    "model_key": expected["model_key"],
                    "field": "snapshot",
                    "reason": "Persisted row missing",
                }
            )
            continue
        for field_name in NUMERIC_FIELDS:
            source_value = expected[field_name]
            stored_value = getattr(stored, field_name)
            if source_value is not None or stored_value is not None:
                compared_values += 1
                if source_value != stored_value:
                    mismatches.append(
                        {
                            "model_key": expected["model_key"],
                            "field": field_name,
                            "source": str(source_value),
                            "persisted": str(stored_value),
                        }
                    )
    report.update(
        {
            "status": "APPLIED" if not mismatches else "RECONCILIATION_FAILED",
            "batch_id": str(plan.batch_id),
            "persisted_snapshots_added": added,
            "identical_snapshots_reused": reused,
            "persisted_output_values_compared": compared_values,
            "persisted_output_value_mismatches": len(mismatches),
            "mismatches": mismatches[:100],
        }
    )
    # Finalize the receipt within the same uncommitted transaction. Once committed, the
    # import-batch and its immutable snapshots are guarded from ordinary ORM mutation.
    session.execute(
        update(ModelOutputImportBatch)
        .where(ModelOutputImportBatch.id == batch.id)
        .values(reconciliation=report)
        .execution_options(synchronize_session=False)
    )
    session.flush()
    return report


def run_cli(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=repo / DEFAULT_WORKBOOK)
    parser.add_argument(
        "--observed-at",
        type=datetime.fromisoformat,
        help="Optional timezone-aware import time. It is never used as effective time.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Persist the import in one transaction."
    )
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path.")
    args = parser.parse_args(argv)
    if args.observed_at is not None and (
        args.observed_at.tzinfo is None or args.observed_at.utcoffset() is None
    ):
        parser.error("--observed-at must include a timezone offset")
    engine = create_database_engine(Settings())
    if engine is None:
        print("Set DATABASE_URL before running model-output import.", file=sys.stderr)
        return 2
    try:
        with Session(engine) as session:
            if args.apply:
                with session.begin():
                    plan = build_import(session, args.workbook, args.observed_at)
                    report = apply_import(session, plan)
            else:
                plan = build_import(session, args.workbook, args.observed_at)
                report = plan.report()
                existing = session.scalar(
                    select(ModelOutputImportBatch).where(
                        ModelOutputImportBatch.source_digest == plan.source_digest
                    )
                )
                if existing:
                    report["already_applied"] = True
        # Keep stdout portable to Windows shells that do not use UTF-8 by default.
        rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
        print(rendered)
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        return 0 if report.get("status") != "RECONCILIATION_FAILED" else 1
    except (OSError, ValueError, KeyError) as error:
        print(f"Model-output import failed: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli())
