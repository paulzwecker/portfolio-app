"""Guarded, model-only canonical identity bootstrap for the P-GOOGL package.

This operation creates only Company, Security and Listing identity rows plus an
immutable receipt. It never creates lifecycle, portfolio, holdings, targets or a
financial-model revision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.bootstrap_preflight import (
    validate_target_selection,
    verify_database_preflight,
)
from portfolio_api.database import create_database_engine
from portfolio_api.database_write_target import (
    DatabaseWriteTargetError,
    verify_database_read_target,
)
from portfolio_api.domain.models import (
    Company,
    Listing,
    ModelIdentityBootstrapReceipt,
    Security,
)
from portfolio_api.financial_model_package import (
    FinancialModelPackage,
    FinancialModelPackageStore,
    PackageError,
    _validate_package_shape,
    validate_financial_model_package,
)
from portfolio_api.legacy_import import _stable_id
from portfolio_api.settings import Settings

IDENTITY_MAPPING_VERSION = "p-googl-canonical-identity-v1"
IDENTITY_PREVIEW_SCHEMA_HEADS = frozenset(
    {
        "6c2eaf0b8147",
        "b16d4f8a2c91",
        "c17a0b9d4e62",
        "3e5c8a1d7b42",
        "9f2a6d4c81b7",
    }
)
IDENTITY_PREVIEW_REQUIRED_TABLES = ("companies", "securities", "listings")


@dataclass(frozen=True)
class ReviewedIdentityMapping:
    source_model_key: str
    package_contract_version: str
    company_name: str
    canonical_ticker: str
    security_name: str
    security_type: str
    listing_ticker: str
    listing_venue: str
    listing_currency: str
    model_currency: str
    security_key: str

    @property
    def company_id(self) -> UUID:
        return _stable_id("company", self.canonical_ticker)

    @property
    def security_id(self) -> UUID:
        return _stable_id("security", self.security_key)

    @property
    def listing_id(self) -> UUID:
        return _stable_id("listing", f"{self.listing_venue}:{self.listing_ticker}")

    def as_dict(self) -> dict[str, str]:
        return {
            "mapping_version": IDENTITY_MAPPING_VERSION,
            "source_model_key": self.source_model_key,
            "package_contract_version": self.package_contract_version,
            "company_name": self.company_name,
            "canonical_ticker": self.canonical_ticker,
            "security_name": self.security_name,
            "security_type": self.security_type,
            "listing_ticker": self.listing_ticker,
            "listing_venue": self.listing_venue,
            "listing_currency": self.listing_currency,
            "model_currency": self.model_currency,
            "security_key": self.security_key,
            "company_id": str(self.company_id),
            "security_id": str(self.security_id),
            "listing_id": str(self.listing_id),
        }


P_GOOGL_IDENTITY_MAPPING = ReviewedIdentityMapping(
    source_model_key="P-GOOGL",
    package_contract_version="financial-model-package-v1",
    company_name="Alphabet",
    canonical_ticker="GOOGL",
    security_name="Alphabet",
    security_type="COMMON_STOCK",
    listing_ticker="GOOGL",
    listing_venue="NASDAQ",
    listing_currency="USD",
    model_currency="USD",
    security_key="GOOGL",
)


class ModelIdentityBootstrapError(ValueError):
    """Sanitized package, mapping or identity reconciliation failure."""


class ModelIdentityConflict(ModelIdentityBootstrapError):
    """Existing canonical identity conflicts with the explicit reviewed mapping."""


def verify_model_identity_read_only_preflight(
    engine: Engine,
    *,
    configured_target_environment: str | None,
    requested_target_environment: str,
) -> set[str]:
    """Verify exact target and the known schema subset required by identity preview."""
    validate_target_selection(configured_target_environment, requested_target_environment)
    verify_database_read_target(engine, required_tables=IDENTITY_PREVIEW_REQUIRED_TABLES)
    try:
        with engine.connect() as connection:
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
            connection.rollback()
    except Exception:
        raise ModelIdentityBootstrapError(
            "Could not read the identity-preview schema revision."
        ) from None
    validate_identity_preview_heads(current_heads)
    return current_heads


def validate_identity_preview_heads(current_heads: set[str]) -> None:
    """Allow only known schema revisions with the unchanged canonical identity tables."""
    if len(current_heads) != 1 or not current_heads <= IDENTITY_PREVIEW_SCHEMA_HEADS:
        raise ModelIdentityBootstrapError(
            "The identity preview supports only one explicitly reviewed canonical schema head."
        )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping_digest() -> str:
    return _sha256(_canonical_json(P_GOOGL_IDENTITY_MAPPING.as_dict()))


def _validated_input(package: FinancialModelPackage, payload_sha256: str) -> dict[str, str]:
    if len(payload_sha256) != 64 or any(char not in "0123456789abcdef" for char in payload_sha256):
        raise ModelIdentityBootstrapError("The model package hash is invalid.")
    serialized = _canonical_json(package.model_dump(mode="json"))
    if _sha256(serialized) != payload_sha256:
        raise ModelIdentityBootstrapError("The model package hash does not match its contents.")
    identity = package.identity
    expected_identity = {
        "source_model_key": P_GOOGL_IDENTITY_MAPPING.source_model_key,
        "company_name": P_GOOGL_IDENTITY_MAPPING.company_name,
        "canonical_ticker": P_GOOGL_IDENTITY_MAPPING.canonical_ticker,
        "listing_ticker": P_GOOGL_IDENTITY_MAPPING.listing_ticker,
        "listing_venue": P_GOOGL_IDENTITY_MAPPING.listing_venue,
        "security_type": P_GOOGL_IDENTITY_MAPPING.security_type,
        "listing_currency": P_GOOGL_IDENTITY_MAPPING.listing_currency,
        "model_currency": P_GOOGL_IDENTITY_MAPPING.model_currency,
    }
    if package.contract_version != P_GOOGL_IDENTITY_MAPPING.package_contract_version or any(
        getattr(identity, field) != value for field, value in expected_identity.items()
    ):
        raise ModelIdentityBootstrapError(
            "The package identity does not match the explicit P-GOOGL canonical mapping."
        )
    if package.revision.acceptance_state != "PROPOSAL_NOT_ACCEPTED":
        raise ModelIdentityBootstrapError("Only an unaccepted model package can be mapped.")
    try:
        _validate_package_shape(package)
    except (PackageError, ValueError):
        raise ModelIdentityBootstrapError(
            "The source package is not a valid supported P-GOOGL model package."
        ) from None
    validated = validate_financial_model_package(package, payload_sha256)
    if validated.parity_report.get("status") != "PARITY_PASS":
        raise ModelIdentityBootstrapError(
            "The P-GOOGL package must pass its existing deterministic model validation first."
        )
    mapping_hash = _mapping_digest()
    input_digest = _sha256(
        _canonical_json(
            {
                "mapping_sha256": mapping_hash,
                "package_sha256": payload_sha256,
                "source_model_key": P_GOOGL_IDENTITY_MAPPING.source_model_key,
            }
        )
    )
    return {"mapping_sha256": mapping_hash, "input_digest": input_digest}


def _stable_identity_rows(
    session: Session,
) -> tuple[Company | None, Security | None, Listing | None]:
    mapping = P_GOOGL_IDENTITY_MAPPING
    company = session.get(Company, mapping.company_id)
    security = session.get(Security, mapping.security_id)
    listing = session.get(Listing, mapping.listing_id)

    if company is not None and (company.is_demo or company.name != mapping.company_name):
        raise ModelIdentityConflict(
            "The deterministic canonical company ID is occupied by a different identity."
        )
    if security is not None and (
        security.is_demo
        or security.company_id != mapping.company_id
        or security.name != mapping.security_name
        or security.security_type != mapping.security_type
        or security.share_class is not None
        or security.underlying_security_id is not None
    ):
        raise ModelIdentityConflict(
            "The deterministic canonical security ID conflicts with the reviewed mapping."
        )
    if listing is not None and (
        listing.is_demo
        or listing.security_id != mapping.security_id
        or listing.venue != mapping.listing_venue
        or listing.ticker != mapping.listing_ticker
        or listing.currency != mapping.listing_currency
    ):
        raise ModelIdentityConflict(
            "The deterministic canonical listing ID conflicts with the reviewed mapping."
        )

    if company is None:
        name_matches = session.scalars(
            select(Company).where(
                Company.name == mapping.company_name,
                Company.is_demo.is_(False),
            )
        ).all()
        if name_matches:
            raise ModelIdentityConflict(
                "A non-deterministic canonical company with the mapped name exists; "
                "reconcile its identity before bootstrapping."
            )

    listing_collision = session.scalar(
        select(Listing).where(
            Listing.venue == mapping.listing_venue,
            Listing.ticker == mapping.listing_ticker,
        )
    )
    if listing_collision is not None and listing_collision.id != mapping.listing_id:
        raise ModelIdentityConflict(
            "The exact venue and ticker are already assigned to another canonical listing."
        )
    return company, security, listing


def preview_model_identity_bootstrap(
    session: Session,
    package: FinancialModelPackage,
    payload_sha256: str,
) -> dict[str, object]:
    """Return the exact model-only identity diff without changing database state."""
    hashes = _validated_input(package, payload_sha256)
    mapping = P_GOOGL_IDENTITY_MAPPING
    receipt_table_available = sa_inspect(session.connection()).has_table(
        ModelIdentityBootstrapReceipt.__tablename__
    )
    receipt = (
        session.scalar(
            select(ModelIdentityBootstrapReceipt).where(
                ModelIdentityBootstrapReceipt.input_digest == hashes["input_digest"]
            )
        )
        if receipt_table_available
        else None
    )
    company, security, listing = _stable_identity_rows(session)
    if receipt is not None:
        if (
            receipt.company_id != mapping.company_id
            or receipt.security_id != mapping.security_id
            or receipt.listing_id != mapping.listing_id
            or receipt.package_sha256 != payload_sha256
        ):
            raise ModelIdentityConflict(
                "The existing identity receipt does not match the immutable package mapping."
            )
        status = "ALREADY_APPLIED"
    elif company is None and security is None and listing is None:
        status = "READY_TO_CREATE"
    elif company is not None and security is not None and listing is not None:
        status = "IDENTITY_PRESENT_RECEIPT_MISSING"
    else:
        status = "READY_TO_COMPLETE"
    return {
        "status": status,
        "mapping_version": IDENTITY_MAPPING_VERSION,
        "mapping_sha256": hashes["mapping_sha256"],
        "input_digest": hashes["input_digest"],
        "source_model_key": mapping.source_model_key,
        "package_sha256": payload_sha256,
        "source_identity_sha256": package.source.source_identity_sha256,
        "source_modified_at": package.source.modified_time,
        "source_revision_id": package.source.drive_revision_id,
        "receipt_id": str(receipt.id) if receipt is not None else None,
        "receipt_schema_available": receipt_table_available,
        "apply_available": receipt_table_available,
        "canonical_identity": {
            "company_name": mapping.company_name,
            "canonical_ticker": mapping.canonical_ticker,
            "company_reporting_currency": None,
            "security_name": mapping.security_name,
            "security_type": mapping.security_type,
            "share_class": None,
            "listing_venue": mapping.listing_venue,
            "listing_ticker": mapping.listing_ticker,
            "listing_currency": mapping.listing_currency,
            "model_currency": mapping.model_currency,
        },
        "canonical_ids": {
            "company_id": str(mapping.company_id),
            "security_id": str(mapping.security_id),
            "listing_id": str(mapping.listing_id),
        },
        "records": {
            "companies": int(company is None),
            "securities": int(security is None),
            "listings": int(listing is None),
            "receipts": int(receipt is None),
            "lifecycle_events": 0,
            "portfolios": 0,
            "holdings": 0,
            "cash_positions": 0,
            "target_revisions": 0,
            "financial_model_revisions": 0,
        },
        "changes": {
            "company": "CREATE" if company is None else "REUSE_EXACT_STABLE_ID",
            "security": "CREATE" if security is None else "REUSE_EXACT_STABLE_ID",
            "listing": "CREATE" if listing is None else "REUSE_EXACT_STABLE_ID",
            "receipt": (
                "CREATE"
                if receipt is None and receipt_table_available
                else "CREATE_REQUIRES_MIGRATION"
                if receipt is None
                else "REUSE_IDENTICAL_RECEIPT"
            ),
        },
        "read_only": True,
    }


def apply_model_identity_bootstrap(
    session: Session,
    package: FinancialModelPackage,
    payload_sha256: str,
    *,
    observed_at: datetime,
) -> dict[str, object]:
    """Insert the P-GOOGL identity chain and immutable source receipt in caller transaction."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ModelIdentityBootstrapError("The package capture timestamp must include a timezone.")
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise ModelIdentityBootstrapError(
            "Identity bootstrap requires PostgreSQL transaction locks."
        )
    lock_key = int.from_bytes(
        hashlib.sha256(b"model-identity-bootstrap:P-GOOGL").digest()[:8],
        byteorder="big",
        signed=True,
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    preview = preview_model_identity_bootstrap(session, package, payload_sha256)
    if preview["apply_available"] is not True:
        raise ModelIdentityBootstrapError("Apply requires the model identity receipt migration.")
    if preview["status"] == "ALREADY_APPLIED":
        return preview

    mapping = P_GOOGL_IDENTITY_MAPPING
    changes = cast(dict[str, str], preview["changes"])
    company, security, listing = _stable_identity_rows(session)
    if company is None:
        company = Company(
            id=mapping.company_id,
            name=mapping.company_name,
            reporting_currency=None,
            is_demo=False,
        )
        session.add(company)
        session.flush()
    if security is None:
        security = Security(
            id=mapping.security_id,
            company_id=company.id,
            name=mapping.security_name,
            security_type=mapping.security_type,
            share_class=None,
            underlying_security_id=None,
            is_demo=False,
        )
        session.add(security)
        session.flush()
    if listing is None:
        listing = Listing(
            id=mapping.listing_id,
            security_id=security.id,
            venue=mapping.listing_venue,
            ticker=mapping.listing_ticker,
            currency=mapping.listing_currency,
            identity_source_ref="financial-model-package-v1:P-GOOGL",
            is_demo=False,
        )
        session.add(listing)
        session.flush()

    receipt = ModelIdentityBootstrapReceipt(
        input_digest=str(preview["input_digest"]),
        mapping_sha256=str(preview["mapping_sha256"]),
        mapping_version=IDENTITY_MAPPING_VERSION,
        source_model_key=mapping.source_model_key,
        package_sha256=payload_sha256,
        source_identity_sha256=package.source.source_identity_sha256,
        source_modified_at=package.source.modified_time,
        source_revision_id=package.source.drive_revision_id,
        company_id=company.id,
        security_id=security.id,
        listing_id=listing.id,
        observed_at=observed_at.astimezone(UTC),
        status="APPLIED",
        report={
            "mapping_version": IDENTITY_MAPPING_VERSION,
            "package_sha256": payload_sha256,
            "source_identity_sha256": package.source.source_identity_sha256,
            "canonical_ids": {
                "company_id": str(company.id),
                "security_id": str(security.id),
                "listing_id": str(listing.id),
            },
            "created": {
                "company": changes["company"] == "CREATE",
                "security": changes["security"] == "CREATE",
                "listing": changes["listing"] == "CREATE",
            },
            "lifecycle_created": False,
            "portfolio_records_created": False,
            "financial_model_revision_created": False,
        },
    )
    session.add(receipt)
    session.flush()
    return {
        **preview,
        "status": "APPLIED",
        "receipt_id": str(receipt.id),
        "records": {
            "companies": int(changes["company"] == "CREATE"),
            "securities": int(changes["security"] == "CREATE"),
            "listings": int(changes["listing"] == "CREATE"),
            "receipts": 1,
            "lifecycle_events": 0,
            "portfolios": 0,
            "holdings": 0,
            "cash_positions": 0,
            "target_revisions": 0,
            "financial_model_revisions": 0,
        },
        "read_only": False,
    }


def _captured_at(package_run: dict[str, Any]) -> datetime:
    raw = package_run.get("captured_at")
    if not isinstance(raw, str):
        raise ModelIdentityBootstrapError("The package manifest has no capture timestamp.")
    try:
        captured_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ModelIdentityBootstrapError("The package capture timestamp is invalid.") from None
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ModelIdentityBootstrapError("The package capture timestamp must include a timezone.")
    return captured_at.astimezone(UTC)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "apply"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--store", type=Path)
        sub.add_argument("--run-id", required=True)
        sub.add_argument("--payload-sha256", required=True)
        sub.add_argument(
            "--target-environment",
            choices=("development", "rehearsal", "production"),
            required=True,
        )
        if command == "apply":
            sub.add_argument("--expected-payload-sha256", required=True)
            sub.add_argument("--approve-payload-sha256", required=True)
            sub.add_argument(
                "--confirm-explicit-identity-bootstrap", action="store_true", required=True
            )
    args = parser.parse_args(argv)
    try:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if args.store is None and not local_app_data:
            raise ModelIdentityBootstrapError(
                "Set --store or LOCALAPPDATA to the private package snapshot store."
            )
        store_root = args.store
        if store_root is None:
            assert local_app_data is not None
            store_root = Path(local_app_data) / "PortfolioResearch" / "workbook-snapshots"
        package_store = FinancialModelPackageStore(store_root)
        package_run = package_store.load(args.run_id, args.payload_sha256)
        _validated_input(package_run.package, package_run.payload_sha256)

        settings = Settings()
        read_only = args.command == "preview"
        if read_only:
            engine = create_database_engine(settings, read_only=True)
        else:
            if (
                args.expected_payload_sha256 != package_run.payload_sha256
                or args.approve_payload_sha256 != package_run.payload_sha256
            ):
                raise ModelIdentityBootstrapError(
                    "The expected and approved hashes must match the stored package."
                )
            engine = create_database_engine(
                settings,
                write_operation="model_identity_bootstrap",
                write_operation_kind="bootstrap",
            )
        if engine is None:
            raise ModelIdentityBootstrapError("DATABASE_URL is required for this operation.")
        try:
            if read_only:
                verify_model_identity_read_only_preflight(
                    engine,
                    configured_target_environment=settings.database_target_environment,
                    requested_target_environment=args.target_environment,
                )
            else:
                verify_database_preflight(
                    engine,
                    configured_target_environment=settings.database_target_environment,
                    requested_target_environment=args.target_environment,
                )
            with Session(engine) as session, session.begin():
                report = (
                    preview_model_identity_bootstrap(
                        session, package_run.package, package_run.payload_sha256
                    )
                    if read_only
                    else apply_model_identity_bootstrap(
                        session,
                        package_run.package,
                        package_run.payload_sha256,
                        observed_at=_captured_at(package_run.manifest),
                    )
                )
        finally:
            engine.dispose()
        print(json.dumps(report, sort_keys=True))
        return (
            0
            if report["status"] in {"READY_TO_CREATE", "READY_TO_COMPLETE", "ALREADY_APPLIED"}
            else 2
        )
    except (ModelIdentityBootstrapError, DatabaseWriteTargetError, PackageError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print(
            "Model identity bootstrap failed; no private package values were printed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
