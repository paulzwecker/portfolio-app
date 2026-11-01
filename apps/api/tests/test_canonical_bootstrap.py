"""Canonical workbook bootstrap coverage uses synthetic workbooks and provider identities only."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from portfolio_api import canonical_bootstrap, legacy_import
from portfolio_api.canonical_bootstrap import (
    IMPORT_VERSION,
    ApprovedWorkbookSnapshot,
    CanonicalBootstrapError,
    ProviderIdentifier,
    _validate_overlay_observation_cutoff,
    apply_canonical_bootstrap,
    build_import_plan,
    import_blocking_issues,
    load_provider_identifiers,
    resolve_approved_snapshot,
)
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    install_database_read_only_guard,
    install_database_write_target_guard,
    verify_database_write_target,
)
from portfolio_api.domain.models import (
    CanonicalBootstrapRun,
    CashPosition,
    Company,
    CompanyProviderIdentifier,
    HoldingPosition,
    HoldingSnapshot,
    LegacyImportBatch,
    Portfolio,
    RankingEntry,
    RankingRun,
    ResearchPriorityInput,
    ScoreAssessment,
    TargetAllocation,
    TargetRevision,
)
from portfolio_api.migrations import alembic_config
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import (
    GOOGLE_SHEET_MIME,
    MARKET_DATA_PROFILE,
    PORTFOLIO_PROFILE,
    XLSX_MIME,
    AcquiredBytes,
    SnapshotStore,
    acquire_snapshot,
)

OBSERVED_AT = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
PORTFOLIO_TARGET = Decimal("0.123456789012")
POSITION_QUANTITY = Decimal("3.1250000001")
CASH_BALANCE = Decimal("250.2500000001")
SYNTHETIC_CIK = "0000000001"


def test_native_google_snapshot_requires_separate_approved_source_value_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    portfolio = ApprovedWorkbookSnapshot(
        run_id="a" * 32,
        profile=PORTFOLIO_PROFILE.key,
        expected_filename=PORTFOLIO_PROFILE.expected_filename,
        sha256="b" * 64,
        path=tmp_path / "portfolio.xlsx",
        acquired_at=OBSERVED_AT,
        schema_fingerprint="c" * 64,
        semantic_sha256="d" * 64,
        workbook=legacy_import.Workbook(Path("portfolio.xlsx"), "b" * 64, {}),
        acquisition_run_id="a" * 32,
        source_identity_sha256="e" * 64,
        source_modified_at="2026-10-31T09:59:00Z",
        source_mime_type=GOOGLE_SHEET_MIME,
    )
    market = ApprovedWorkbookSnapshot(
        run_id="f" * 32,
        profile=MARKET_DATA_PROFILE.key,
        expected_filename=MARKET_DATA_PROFILE.expected_filename,
        sha256="1" * 64,
        path=tmp_path / "market.xlsx",
        acquired_at=OBSERVED_AT,
        schema_fingerprint="2" * 64,
        workbook=None,
        acquisition_run_id="f" * 32,
        source_mime_type=XLSX_MIME,
    )
    monkeypatch.setattr(
        canonical_bootstrap,
        "resolve_approved_snapshot",
        lambda _store, run_id, **_kwargs: portfolio if run_id == portfolio.run_id else market,
    )

    with pytest.raises(CanonicalBootstrapError, match="requires an explicitly approved"):
        build_import_plan(
            SnapshotStore(tmp_path / "private-store"), portfolio.run_id, market.run_id
        )


def _sheet_xml(cells: dict[str, str]) -> str:
    rows: dict[int, list[str]] = {}
    for address, value in cells.items():
        row_number = int("".join(character for character in address if character.isdigit()))
        node = f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        rows.setdefault(row_number, []).append(node)
    row_xml = "".join(
        f'<row r="{row}">{"".join(items)}</row>' for row, items in sorted(rows.items())
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{row_xml}</sheetData></worksheet>"
    )


def _xlsx(names: tuple[str, ...], cells_by_sheet: dict[str, dict[str, str]]) -> bytes:
    sheet_nodes = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_nodes}</sheets></workbook>"
    )
    relations = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index, _name in enumerate(names, start=1)
    )
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relations}</Relationships>",
        )
        for index, name in enumerate(names, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _sheet_xml(cells_by_sheet.get(name, {})),
            )
    return output.getvalue()


def synthetic_workbooks(
    *,
    target: str = str(PORTFOLIO_TARGET),
    position_quantity: str = str(POSITION_QUANTITY),
    current_weight: str = "0.25",
    listing_basis: str = "Common Stock",
) -> tuple[bytes, bytes]:
    portfolio_cells: dict[str, dict[str, str]] = {}
    for sheet in PORTFOLIO_PROFILE.required_sheets:
        if sheet == "Candidate Ranking":
            portfolio_cells[sheet] = {"A1": "Priority Seed", "B1": "Ticker"}
        elif sheet == "Model Contract":
            portfolio_cells[sheet] = {"A5": "Synthetic model contract v1"}
        elif sheet == "Model Revision History":
            portfolio_cells[sheet] = {"A3": "Revision"}
        elif sheet == "Estimate History":
            portfolio_cells[sheet] = {"A1": "Estimate"}
        else:
            row = dict(PORTFOLIO_PROFILE.header_rows).get(sheet, 4)
            portfolio_cells[sheet] = {f"A{row}": f"Synthetic {sheet} header"}
    portfolio_cells["P-SYN"] = {"A4": "Synthetic detail"}
    portfolio_cells["W-CAND"] = {"A4": "Synthetic detail"}
    portfolio_cells["Universe Registry"].update(
        {
            "A5": "SYN",
            "B5": "Synthetic Example Corporation",
            "C5": "Portfolio",
            "D5": current_weight,
            "F5": target,
            "J5": "1",
            "L5": "1",
            "A6": "CAND",
            "B6": "Synthetic Candidate Corporation",
            "C6": "Candidate - High",
            "D6": "0",
            "F6": "0",
            "J6": "1",
        }
    )
    portfolio_cells["Current Holdings"].update(
        {
            "A1": "Synthetic holdings fixture",
            "A2": "Title",
            "A3": "Title",
            "A4": "Kind",
            "L4": "Portfolio total EUR",
            "A5": "stock",
            "B5": "SYN",
            "D5": "SYN",
            "E5": position_quantity,
            "A6": "cash component",
            "E6": str(CASH_BALANCE),
            "G6": "EUR",
        }
    )
    portfolio_cells["Target Architecture"].update(
        {
            "P3": target,
            "A4": "Ticker",
            "D4": "Weight",
            "A5": "SYN",
            "D5": target,
            "A6": "CAND",
            "D6": "0",
            "A7": "RESERVE",
            "D7": "0",
        }
    )
    portfolio_cells["10Y Durability"].update(
        {
            "A5": "SYN",
            "G5": "4.25",
            "K5": "Synthetic durability rationale",
            "L5": "https://example.test/source",
        }
    )
    portfolio_cells["Compounder Quality"].update(
        {
            "A5": "SYN",
            "B5": "Synthetic Example Corporation",
            "G5": "4.125",
            "K5": "Synthetic quality rationale",
            "L5": "https://example.test/source",
        }
    )
    portfolio_cells["Candidate Ranking"].update({"A2": "50000.125", "B2": "CAND"})
    portfolio_cells["P-SYN"].update(
        {
            "A4": "Synthetic detail",
            "A7": "Execution Score",
            "B7": "3.75",
            "A8": "Risk Score",
            "B8": "2.25",
        }
    )
    portfolio_cells["W-CAND"].update({"A4": "Synthetic detail"})
    portfolio_names = (*PORTFOLIO_PROFILE.required_sheets, "P-SYN", "W-CAND")
    portfolio = _xlsx(portfolio_names, portfolio_cells)

    market_cells: dict[str, dict[str, str]] = {}
    for sheet in MARKET_DATA_PROFILE.required_sheets:
        row = dict(MARKET_DATA_PROFILE.header_rows).get(sheet, 3)
        market_cells[sheet] = {f"A{row}": f"Synthetic {sheet} header"}
    market_cells["Listings"].update(
        {
            "A5": "SYN",
            "B5": "Synthetic Example Corporation",
            "C5": "XNYS:SYN",
            "D5": "XNYS",
            "E5": "USD",
            "G5": listing_basis,
            "K5": "READY",
        }
    )
    market = _xlsx(MARKET_DATA_PROFILE.required_sheets, market_cells)
    return portfolio, market


def _snapshot(
    store: SnapshotStore,
    profile: Any,
    data: bytes,
    *,
    source_identity: str,
    accepted: bool = True,
) -> dict[str, Any]:
    acquired = acquire_snapshot(
        store=store,
        profile=profile,
        source_identity=source_identity,
        fetch=lambda: AcquiredBytes(
            data=data,
            method="synthetic_test_fixture",
            source_revision=None,
            source_modified_at=None,
            source_checksum=None,
            source_mime_type=XLSX_MIME,
        ),
    )
    if acquired["status"] == "ACQUIRED" or not accepted:
        return acquired
    return store.accept_schema_baseline(acquired["run_id"], acquired["artifact_sha256"])


def _provider_input(tmp_path: Path, *, cik: str = SYNTHETIC_CIK) -> tuple[Path, str]:
    data = {
        "format_version": 1,
        "reviewed_by": "synthetic-reviewer",
        "reviewed_at": OBSERVED_AT.isoformat(),
        "mappings": [
            {
                "canonical_ticker": "SYN",
                "identifier_type": "SEC_CIK",
                "identifier_value": cik,
                "provider_company_name": "Synthetic Example Corporation",
                "evidence_source": f"https://www.sec.gov/edgar/browse/?CIK={cik}",
            }
        ],
    }
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    path = tmp_path / "synthetic-provider-identifiers.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _prepared_inputs(
    tmp_path: Path,
    *,
    portfolio_bytes: bytes | None = None,
    market_bytes: bytes | None = None,
) -> tuple[SnapshotStore, Any, Any, Any]:
    portfolio_bytes, market_bytes = (
        (portfolio_bytes, market_bytes)
        if portfolio_bytes is not None and market_bytes is not None
        else synthetic_workbooks()
    )
    store = SnapshotStore(tmp_path / "private-snapshot-store")
    portfolio_manifest = _snapshot(
        store, PORTFOLIO_PROFILE, portfolio_bytes, source_identity="synthetic-portfolio-source"
    )
    market_manifest = _snapshot(
        store, MARKET_DATA_PROFILE, market_bytes, source_identity="synthetic-market-source"
    )
    portfolio, market, plan = build_import_plan(
        store,
        portfolio_manifest["run_id"],
        market_manifest["run_id"],
        observed_at=OBSERVED_AT,
    )
    return store, portfolio, market, plan


def test_live_value_overlay_cannot_be_imported_before_its_observation_window() -> None:
    comparison_completed_at = "2026-10-31T09:02:00+00:00"

    with pytest.raises(CanonicalBootstrapError, match="predates the live value comparison"):
        _validate_overlay_observation_cutoff(
            comparison_completed_at,
            datetime(2026, 10, 31, 9, 1, tzinfo=UTC),
        )

    _validate_overlay_observation_cutoff(
        comparison_completed_at,
        datetime(2026, 10, 31, 9, 2, tzinfo=UTC),
    )


def test_snapshot_import_requires_approved_current_hash_checked_run(tmp_path: Path) -> None:
    portfolio_bytes, _market_bytes = synthetic_workbooks()
    store = SnapshotStore(tmp_path / "private-snapshot-store")
    acquired = _snapshot(
        store,
        PORTFOLIO_PROFILE,
        portfolio_bytes,
        source_identity="synthetic-source",
        accepted=False,
    )
    with pytest.raises(CanonicalBootstrapError, match="not an approved"):
        resolve_approved_snapshot(
            store,
            acquired["run_id"],
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )

    accepted = store.accept_schema_baseline(acquired["run_id"], acquired["artifact_sha256"])
    resolved = resolve_approved_snapshot(
        store,
        accepted["run_id"],
        expected_profile=PORTFOLIO_PROFILE.key,
        expected_contract_version=PORTFOLIO_PROFILE.contract_version,
        expected_filename=PORTFOLIO_PROFILE.expected_filename,
    )
    assert resolved.sha256 == acquired["artifact_sha256"]
    assert resolved.path.read_bytes() == portfolio_bytes
    assert resolved.semantic_sha256 is not None
    assert resolved.workbook is not None


def test_approved_portfolio_snapshot_requires_matching_semantic_fingerprint(
    tmp_path: Path,
) -> None:
    portfolio_bytes, _market_bytes = synthetic_workbooks()
    store = SnapshotStore(tmp_path / "private-snapshot-store")
    acquisition = _snapshot(
        store,
        PORTFOLIO_PROFILE,
        portfolio_bytes,
        source_identity="synthetic-source",
        accepted=False,
    )
    accepted = store.accept_schema_baseline(acquisition["run_id"], acquisition["artifact_sha256"])
    corrupted_sha = "0" * 64
    for run_id in (acquisition["run_id"], accepted["run_id"]):
        path = store.run_root / f"{run_id}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["semantic_sha256"] = corrupted_sha
        path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CanonicalBootstrapError, match="fingerprint differs from its manifest"):
        resolve_approved_snapshot(
            store,
            accepted["run_id"],
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )


def test_pre_fingerprint_portfolio_snapshot_requires_reacquisition(tmp_path: Path) -> None:
    portfolio_bytes, _market_bytes = synthetic_workbooks()
    store = SnapshotStore(tmp_path / "private-snapshot-store")
    acquisition = _snapshot(
        store,
        PORTFOLIO_PROFILE,
        portfolio_bytes,
        source_identity="synthetic-source",
        accepted=False,
    )
    accepted = store.accept_schema_baseline(acquisition["run_id"], acquisition["artifact_sha256"])
    for run_id in (acquisition["run_id"], accepted["run_id"]):
        path = store.run_root / f"{run_id}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("semantic_fingerprint_version", None)
        manifest.pop("semantic_sha256", None)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CanonicalBootstrapError, match="predates importer-value fingerprints"):
        resolve_approved_snapshot(
            store,
            accepted["run_id"],
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )


def test_newer_source_acquisition_invalidates_an_older_snapshot_selection(tmp_path: Path) -> None:
    portfolio_bytes, _market_bytes = synthetic_workbooks()
    store = SnapshotStore(tmp_path / "private-snapshot-store")
    first = _snapshot(store, PORTFOLIO_PROFILE, portfolio_bytes, source_identity="synthetic-source")
    changed_bytes, _ = synthetic_workbooks(target="0.2")
    _newer = _snapshot(store, PORTFOLIO_PROFILE, changed_bytes, source_identity="synthetic-source")
    with pytest.raises(CanonicalBootstrapError, match="newer workbook acquisition"):
        resolve_approved_snapshot(
            store,
            first["run_id"],
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )


def test_source_hash_tampering_is_rejected_and_zero_target_decimal_are_exact(
    tmp_path: Path,
) -> None:
    store, portfolio, _market, plan = _prepared_inputs(tmp_path)
    assert plan.targets["SYN"] == PORTFOLIO_TARGET
    assert plan.targets["CAND"] == Decimal("0")
    assert not import_blocking_issues(plan)
    assert all("Portfolio_Watchlist.xlsx:" in row.source for row in plan.positions)

    blob = store.root / "blobs" / "sha256" / portfolio.sha256 / "workbook.xlsx"
    blob.write_bytes(b"changed synthetic bytes")
    with pytest.raises(CanonicalBootstrapError, match="SHA-256"):
        resolve_approved_snapshot(
            store,
            portfolio.run_id,
            expected_profile=PORTFOLIO_PROFILE.key,
            expected_contract_version=PORTFOLIO_PROFILE.contract_version,
            expected_filename=PORTFOLIO_PROFILE.expected_filename,
        )


def test_incomplete_holdings_do_not_create_a_position_and_lifecycle_is_not_inferred(
    tmp_path: Path,
) -> None:
    portfolio_bytes, market_bytes = synthetic_workbooks(position_quantity="")
    _store, _portfolio, _market, plan = _prepared_inputs(
        tmp_path, portfolio_bytes=portfolio_bytes, market_bytes=market_bytes
    )
    assert plan.positions == []
    assert plan.holdings_partial is True
    assert any(issue.code == "HOLDING_QUANTITY_MISSING" for issue in plan.issues)

    incomplete_bytes, market_bytes = synthetic_workbooks(current_weight="")
    _store, _portfolio, _market, incomplete_plan = _prepared_inputs(
        tmp_path / "incomplete", portfolio_bytes=incomplete_bytes, market_bytes=market_bytes
    )
    company = next(item for item in incomplete_plan.companies if item.ticker == "SYN")
    assert company.lifecycle is None
    assert any(issue.code == "LIFECYCLE_SOURCE_INCOMPLETE" for issue in incomplete_plan.issues)
    assert any(
        issue["code"] == "LIFECYCLE_SOURCE_INCOMPLETE"
        for issue in import_blocking_issues(incomplete_plan)
    )


def test_ambiguous_adr_listing_is_blocked_instead_of_inferred(tmp_path: Path) -> None:
    portfolio_bytes, market_bytes = synthetic_workbooks(listing_basis="American Depositary Receipt")
    _store, _portfolio, _market, plan = _prepared_inputs(
        tmp_path, portfolio_bytes=portfolio_bytes, market_bytes=market_bytes
    )
    assert plan.listings == []
    assert any(
        issue["code"] == "ADR_IDENTITY_UNSUPPORTED" for issue in import_blocking_issues(plan)
    )


def test_target_precision_beyond_canonical_column_scale_is_blocked(tmp_path: Path) -> None:
    portfolio_bytes, market_bytes = synthetic_workbooks(target="0.1234567890123")
    _store, _portfolio, _market, plan = _prepared_inputs(
        tmp_path, portfolio_bytes=portfolio_bytes, market_bytes=market_bytes
    )
    assert any(
        issue["code"] == "TARGET_PRECISION_UNSUPPORTED" for issue in import_blocking_issues(plan)
    )
    assert "SYN" not in plan.targets


def test_reviewed_provider_identity_map_is_hash_pinned_and_exact(tmp_path: Path) -> None:
    provider_path, digest = _provider_input(tmp_path)
    provider_plan = load_provider_identifiers(provider_path, digest, known_tickers={"SYN", "CAND"})
    assert provider_plan.mappings == (
        ProviderIdentifier(
            "SYN",
            SYNTHETIC_CIK,
            "Synthetic Example Corporation",
            f"https://www.sec.gov/edgar/browse/?CIK={SYNTHETIC_CIK}",
        ),
    )
    with pytest.raises(CanonicalBootstrapError, match="does not match"):
        load_provider_identifiers(provider_path, "0" * 64, known_tickers={"SYN", "CAND"})

    duplicate = json.loads(provider_path.read_text())
    duplicate["mappings"].append(dict(duplicate["mappings"][0]))
    duplicate_bytes = (json.dumps(duplicate, sort_keys=True) + "\n").encode()
    provider_path.write_bytes(duplicate_bytes)
    with pytest.raises(CanonicalBootstrapError, match="Duplicate canonical ticker"):
        load_provider_identifiers(
            provider_path,
            hashlib.sha256(duplicate_bytes).hexdigest(),
            known_tickers={"SYN", "CAND"},
        )


def _target_settings(engine: Any, **overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "database_url": SecretStr(engine.url.render_as_string(hide_password=False)),
            "app_env": "development",
            "database_target_environment": "development",
            "database_target_database": engine.url.database,
            "database_local_test_writes_authorized": True,
            **overrides,
        }
    )


@pytest.mark.integration
def test_postgres18_bootstrap_resumes_after_interruption_and_is_idempotent(
    postgres_engine: Any, tmp_path: Path
) -> None:
    store, portfolio, market, plan = _prepared_inputs(tmp_path)
    provider_path, provider_hash = _provider_input(tmp_path)
    provider_plan = load_provider_identifiers(
        provider_path, provider_hash, known_tickers={"SYN", "CAND"}
    )
    settings = _target_settings(postgres_engine)
    audit: list[Mapping[str, Any]] = []
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="canonical_bootstrap_test",
        operation_kind="bootstrap",
        audit_sink=audit.append,
    )
    verify_database_write_target(postgres_engine)

    def interrupt_before_receipt(
        _conn: Any, _cursor: Any, statement: str, _params: Any, _ctx: Any, _many: bool
    ) -> None:
        if "insert into canonical_bootstrap_runs" in statement.casefold():
            raise RuntimeError("synthetic interruption")

    event.listen(postgres_engine, "before_cursor_execute", interrupt_before_receipt)
    try:
        with (
            pytest.raises(RuntimeError, match="synthetic interruption"),
            Session(postgres_engine) as session,
            session.begin(),
        ):
            apply_canonical_bootstrap(
                session,
                portfolio_snapshot=portfolio,
                market_snapshot=market,
                plan=plan,
                provider_plan=provider_plan,
                observed_at=OBSERVED_AT,
                resume=True,
            )
    finally:
        event.remove(postgres_engine, "before_cursor_execute", interrupt_before_receipt)

    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(LegacyImportBatch)) == 0
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 0

    with Session(postgres_engine) as session, session.begin():
        first = apply_canonical_bootstrap(
            session,
            portfolio_snapshot=portfolio,
            market_snapshot=market,
            plan=plan,
            provider_plan=provider_plan,
            observed_at=OBSERVED_AT,
            resume=True,
        )
    assert first["status"] == "APPLIED"
    assert first["bootstrap"]["import_version"] == IMPORT_VERSION
    assert first["bootstrap"]["dependency_order"] == [
        "company-identities",
        "security-listings",
        "portfolio-state",
        "investment-assessments",
        "research-priority",
        "ranking-snapshots",
    ]
    assert first["reconciliation"]["status"] == "MATCHED"

    with Session(postgres_engine) as session:
        counts_before_replay = {
            "holding_snapshots": session.scalar(select(func.count()).select_from(HoldingSnapshot)),
            "holding_positions": session.scalar(select(func.count()).select_from(HoldingPosition)),
            "cash_positions": session.scalar(select(func.count()).select_from(CashPosition)),
            "target_revisions": session.scalar(select(func.count()).select_from(TargetRevision)),
            "target_allocations": session.scalar(
                select(func.count()).select_from(TargetAllocation)
            ),
            "score_assessments": session.scalar(select(func.count()).select_from(ScoreAssessment)),
            "ranking_runs": session.scalar(select(func.count()).select_from(RankingRun)),
            "ranking_entries": session.scalar(select(func.count()).select_from(RankingEntry)),
        }
        repeated = apply_canonical_bootstrap(
            session,
            portfolio_snapshot=portfolio,
            market_snapshot=market,
            plan=plan,
            provider_plan=provider_plan,
            observed_at=OBSERVED_AT,
            resume=True,
        )
        counts_after_replay = {
            "holding_snapshots": session.scalar(select(func.count()).select_from(HoldingSnapshot)),
            "holding_positions": session.scalar(select(func.count()).select_from(HoldingPosition)),
            "cash_positions": session.scalar(select(func.count()).select_from(CashPosition)),
            "target_revisions": session.scalar(select(func.count()).select_from(TargetRevision)),
            "target_allocations": session.scalar(
                select(func.count()).select_from(TargetAllocation)
            ),
            "score_assessments": session.scalar(select(func.count()).select_from(ScoreAssessment)),
            "ranking_runs": session.scalar(select(func.count()).select_from(RankingRun)),
            "ranking_entries": session.scalar(select(func.count()).select_from(RankingEntry)),
        }
        assert repeated["status"] == "ALREADY_APPLIED"
        assert repeated["reconciliation"]["status"] == "MATCHED"
        assert counts_after_replay == counts_before_replay
        assert counts_after_replay["score_assessments"] == len(plan.scores)
        assert counts_after_replay["ranking_runs"] == len(plan.rankings)
        assert counts_after_replay["ranking_entries"] == sum(
            len(rows) for rows in plan.rankings.values()
        )
        assert session.scalar(select(func.count()).select_from(Company)) == 2
        assert session.scalar(select(func.count()).select_from(Portfolio)) == 1
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(HoldingPosition)) == 1
        assert session.scalar(select(func.count()).select_from(CashPosition)) == 1
        assert session.scalar(select(func.count()).select_from(TargetRevision)) == 1
        assert session.scalar(select(func.count()).select_from(TargetAllocation)) == 2
        assert session.scalar(select(func.count()).select_from(ResearchPriorityInput)) == 1
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 1
        assert session.scalar(select(func.count()).select_from(LegacyImportBatch)) == 1
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 1
        target = session.scalar(
            select(TargetAllocation.weight)
            .join(TargetRevision)
            .join(Company)
            .where(Company.name == "Synthetic Candidate Corporation")
        )
        assert target == Decimal("0")
        position = session.scalar(select(HoldingPosition.quantity))
        assert position == POSITION_QUANTITY
        cash = session.scalar(select(CashPosition.balance))
        assert cash == CASH_BALANCE
        receipt = session.scalar(select(CanonicalBootstrapRun))
        assert receipt is not None
        assert receipt.portfolio_snapshot_run_id == portfolio.run_id
        assert receipt.market_snapshot_run_id == market.run_id
        assert receipt.provider_identifiers_sha256 == provider_hash
        assert audit
        assert all("password" not in str(item).casefold() for item in audit)


@pytest.mark.integration
def test_canonical_bootstrap_imports_at_last_recorded_production_schema(
    postgres_engine: Any, tmp_path: Path
) -> None:
    """R7's canonical importer must work at 6c without the later sync/ingestion migrations."""
    with postgres_engine.begin() as connection:
        config = alembic_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "6c2eaf0b8147")
        assert set(MigrationContext.configure(connection).get_current_heads()) == {"6c2eaf0b8147"}

    _store, portfolio, market, plan = _prepared_inputs(tmp_path)
    with Session(postgres_engine) as session, session.begin():
        report = apply_canonical_bootstrap(
            session,
            portfolio_snapshot=portfolio,
            market_snapshot=market,
            plan=plan,
            provider_plan=None,
            observed_at=OBSERVED_AT,
            resume=True,
        )

    assert report["status"] == "APPLIED"
    assert report["reconciliation"]["status"] == "MATCHED"
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 2
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 1


@pytest.mark.integration
def test_local_bootstrap_target_guard_rejects_wrong_environment_before_writes(
    postgres_engine: Any,
) -> None:
    settings = _target_settings(postgres_engine, database_target_environment="rehearsal")
    install_database_write_target_guard(
        postgres_engine,
        settings,
        operation="canonical_bootstrap_wrong_target_test",
        operation_kind="bootstrap",
    )
    with pytest.raises(DatabaseWriteTargetError, match="local_target_environment_mismatch"):
        verify_database_write_target(postgres_engine)
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0


@pytest.mark.integration
def test_canonical_bootstrap_preview_uses_read_only_postgres_and_writes_no_receipt(
    postgres_engine: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, portfolio, market, _plan = _prepared_inputs(tmp_path)
    target_database = postgres_engine.url.database
    assert target_database is not None and target_database.endswith("_test")
    with postgres_engine.connect() as connection:
        schema = connection.execute(select(func.current_schema())).scalar_one()
    settings = _target_settings(
        postgres_engine,
        database_local_test_writes_authorized=False,
        database_local_writes_authorized=False,
        database_production_writes_authorized=False,
    )
    read_engine = create_engine(
        postgres_engine.url,
        connect_args={
            "options": (
                f"-c search_path={schema} -c statement_timeout=5000 "
                "-c default_transaction_read_only=on"
            )
        },
        hide_parameters=True,
    )
    install_database_read_only_guard(read_engine, settings)
    attempted_mutations: list[str] = []

    def record_mutation_attempt(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        from portfolio_api.database_write_target import _statement_may_write

        if _statement_may_write(statement, context):
            attempted_mutations.append(statement)

    event.listen(read_engine, "before_cursor_execute", record_mutation_attempt)
    monkeypatch.setattr(canonical_bootstrap, "Settings", lambda: settings)

    def provide_read_only_engine(*_args: Any, **kwargs: Any) -> Any:
        assert kwargs["read_only"] is True
        return read_engine

    monkeypatch.setattr(canonical_bootstrap, "create_database_engine", provide_read_only_engine)
    try:
        exit_code = canonical_bootstrap.main(
            [
                "preview",
                "--store",
                str(store.root),
                "--portfolio-run",
                portfolio.run_id,
                "--market-run",
                market.run_id,
                "--target-environment",
                "development",
            ]
        )
        output = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert output["status"] in {"READY", "READY_WITH_SOURCE_GAPS"}
        assert attempted_mutations == []
    finally:
        read_engine.dispose()

    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
        assert session.scalar(select(func.count()).select_from(Portfolio)) == 0
        assert session.scalar(select(func.count()).select_from(HoldingSnapshot)) == 0
        assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 0
        assert session.scalar(select(func.count()).select_from(LegacyImportBatch)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("command", ["apply", "resume"])
def test_bootstrap_apply_and_resume_keep_the_write_authorization_gate(
    command: str,
    postgres_engine: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, portfolio, market, _plan = _prepared_inputs(tmp_path)
    settings = _target_settings(
        postgres_engine,
        database_local_test_writes_authorized=False,
        database_local_writes_authorized=False,
        database_production_writes_authorized=False,
    )
    with postgres_engine.connect() as connection:
        schema = connection.execute(select(func.current_schema())).scalar_one()
    guarded_engine = create_engine(
        postgres_engine.url,
        connect_args={"options": f"-c search_path={schema} -c statement_timeout=5000"},
        hide_parameters=True,
    )
    install_database_write_target_guard(
        guarded_engine,
        settings,
        operation="canonical_portfolio_bootstrap",
        operation_kind="bootstrap",
    )
    monkeypatch.setattr(canonical_bootstrap, "Settings", lambda: settings)

    def provide_write_engine(*_args: Any, **kwargs: Any) -> Any:
        assert kwargs["read_only"] is False
        return guarded_engine

    monkeypatch.setattr(canonical_bootstrap, "create_database_engine", provide_write_engine)

    try:
        exit_code = canonical_bootstrap.main(
            [
                command,
                "--store",
                str(store.root),
                "--portfolio-run",
                portfolio.run_id,
                "--market-run",
                market.run_id,
                "--target-environment",
                "development",
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert "local_test_write_not_authorized" in caplog.text
        assert captured.err
        with Session(postgres_engine) as session:
            assert session.scalar(select(func.count()).select_from(Company)) == 0
            assert session.scalar(select(func.count()).select_from(CanonicalBootstrapRun)) == 0
    finally:
        guarded_engine.dispose()
