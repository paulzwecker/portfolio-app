"""Frozen publication inspection and native preview with no database mutations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from portfolio_api.bootstrap_preflight import verify_database_read_only_preflight
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import DatabaseWriteTargetError, _is_loopback
from portfolio_api.domain.models import FinancialModel
from portfolio_api.domain.services import DomainError
from portfolio_api.google_sheets_sync import (
    MAX_CONTRACT_BYTES,
    ParsedContract,
    parse_portable_contract,
    preview_portable_contract,
)
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import (
    SnapshotStore,
    WorkbookSourceError,
    _assert_private_location,
)


class PublicationPreflightError(ValueError):
    """A fixed error code safe for terminal output."""


def load_publication(path: Path, expected_sha256: str) -> tuple[str, ParsedContract]:
    """Read once, hash the exact bytes, then validate the existing publication contract."""
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise PublicationPreflightError("PUBLICATION_HASH_INVALID")
    source = _assert_private_location(path, label="model publication")
    with source.open("rb") as stream:
        payload = stream.read(MAX_CONTRACT_BYTES + 1)
    if len(payload) > MAX_CONTRACT_BYTES:
        raise PublicationPreflightError("PUBLICATION_TOO_LARGE")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise PublicationPreflightError("PUBLICATION_HASH_MISMATCH")
    try:
        raw = payload.decode("utf-8")
        parsed = parse_portable_contract(raw)
    except ValidationError:
        raise PublicationPreflightError("PUBLICATION_SCHEMA_INVALID") from None
    except (UnicodeError, ValueError):
        raise PublicationPreflightError("PUBLICATION_CONTRACT_INVALID") from None
    if parsed.publication is None:
        raise PublicationPreflightError("PUBLICATION_ENVELOPE_REQUIRED")
    return raw, parsed


def preview_publication(session: Session, parsed: ParsedContract) -> dict[str, object]:
    """Use the inbox's native preview without creating a sync run or candidate."""
    model = session.get(FinancialModel, parsed.model_id)
    if model is None:
        return {"status": "MISSING_CANONICAL_MODEL", "model_id": str(parsed.model_id)}
    try:
        return preview_portable_contract(session, model.id, parsed)
    except DomainError as error:
        return {"status": "CONFLICT" if error.status == 409 else "INVALID", "reason": error.detail}


def run_preflight(
    *,
    source: Path,
    expected_sha256: str,
    store_root: Path,
    target_environment: str | None,
    settings: Settings | None = None,
) -> dict[str, object]:
    raw, parsed = load_publication(source, expected_sha256)
    store = SnapshotStore(store_root / "model-publication-preflight")
    report: dict[str, object] = {
        "contract_type": "ModelPublicationPreflightV1",
        "contract_version": "1.0.0",
        "run_id": uuid4().hex,
        "checked_at": datetime.now(UTC).isoformat(),
        "publication_sha256": expected_sha256,
        "publication_json": raw,
        "source_verification": "FROZEN_FILE_ONLY",
        "inbox_capture_checked": False,
        "model_id": str(parsed.model_id),
        "company_id": str(parsed.company_id),
        "valuation_listing_id": str(parsed.valuation_listing_id),
        "model_type": parsed.model_type,
        "model_currency": parsed.model_currency,
        "base_revision_id": str(parsed.base_revision_id),
        "status": "SCHEMA_VALID",
        "native_calculation_checked": False,
        "acceptance_authorized": False,
    }
    if target_environment is not None:
        configuration = settings or Settings()
        engine = create_database_engine(configuration, read_only=True)
        if engine is None:
            raise PublicationPreflightError("DATABASE_NOT_CONFIGURED")
        try:
            engine.update_execution_options(isolation_level="REPEATABLE READ")
            heads = verify_database_read_only_preflight(
                engine,
                configured_target_environment=configuration.database_target_environment,
                requested_target_environment=target_environment,
            )
            with Session(engine, autoflush=False) as session, session.begin():
                identity = session.execute(
                    text("SELECT current_database(), current_schema()")
                ).one()
                preview = preview_publication(session, parsed)
                remote = engine.url.host is not None and not _is_loopback(engine.url.host)
                report.update(
                    {
                        "status": "READY_FOR_REVIEW"
                        if preview.get("status") == "READY"
                        else preview.get("status", "INVALID"),
                        "native_calculation_checked": preview.get("calculated_outputs") is not None,
                        "preview": preview,
                        "target": {
                            "environment": target_environment,
                            "provider": "neon" if remote else "local_postgresql",
                            "project_id": configuration.neon_project_id if remote else None,
                            "branch_id": configuration.neon_branch_id if remote else None,
                            "endpoint_id": configuration.neon_endpoint_id if remote else None,
                            "database": identity[0],
                            "schema": identity[1],
                            "alembic_heads": sorted(heads),
                        },
                    }
                )
        finally:
            engine.dispose()
    store._write_manifest(report)
    return {
        key: report[key]
        for key in (
            "run_id",
            "status",
            "publication_sha256",
            "native_calculation_checked",
            "acceptance_authorized",
        )
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "preview"])
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--publication-sha256", required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--target-environment", choices=["development", "rehearsal", "production"])
    args = parser.parse_args(argv)
    if (args.command == "preview") != (args.target_environment is not None):
        parser.error("Only preview requires --target-environment")
    try:
        result = run_preflight(
            source=args.publication,
            expected_sha256=args.publication_sha256,
            store_root=args.store,
            target_environment=args.target_environment,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        ValidationError,
        DatabaseWriteTargetError,
        WorkbookSourceError,
    ) as error:
        code = str(error) if isinstance(error, PublicationPreflightError) else "PREFLIGHT_FAILED"
        if isinstance(error, (DatabaseWriteTargetError, WorkbookSourceError)):
            code = error.code
        print(json.dumps({"status": "BLOCKED", "code": code}))
        return 2
    except Exception:
        # Driver/provider exceptions can contain connection strings or source values.
        print(json.dumps({"status": "BLOCKED", "code": "PREFLIGHT_FAILED"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"SCHEMA_VALID", "READY_FOR_REVIEW"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
