"""Import only explicitly READY listing identities from the reviewed provider crosswalk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain.models import Company, Listing, Security
from portfolio_api.settings import REPOSITORY_PATH, Settings
from portfolio_api.yahoo_finance import YahooListingCrosswalk, load_yahoo_crosswalk

CROSSWALK_PATH = REPOSITORY_PATH / "reference" / "market-data" / "providers" / "yahoo-listings.json"


def build_mapping_plan(session: Session, crosswalk: YahooListingCrosswalk) -> dict[str, Any]:
    additions: list[dict[str, Any]] = []
    existing: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    for mapping in crosswalk.mappings:
        if mapping.identity_status != "READY_FOR_CANONICAL_IMPORT":
            continue
        required = (
            mapping.canonical_company_id,
            mapping.canonical_company_name,
            mapping.canonical_security_id,
            mapping.canonical_listing_id,
            mapping.identity_source_ref,
        )
        if any(value is None for value in required):
            issues.append(
                {
                    "identity": f"{mapping.venue}:{mapping.ticker}:{mapping.currency}",
                    "issue": "CANONICAL_IDENTITY_EVIDENCE_INCOMPLETE",
                }
            )
            continue
        company_id = mapping.canonical_company_id
        security_id = mapping.canonical_security_id
        listing_id = mapping.canonical_listing_id
        company = session.get(Company, company_id)
        identity = f"{mapping.venue}:{mapping.ticker}:{mapping.currency}"
        if company is None or company.name != mapping.canonical_company_name:
            issues.append({"identity": identity, "issue": "CANONICAL_COMPANY_MISMATCH"})
            continue
        by_market_key = session.scalar(
            select(Listing).where(Listing.venue == mapping.venue, Listing.ticker == mapping.ticker)
        )
        by_id = session.get(Listing, listing_id)
        security = session.get(Security, security_id)
        if by_market_key is not None:
            if (
                by_market_key.id == listing_id
                and by_market_key.security_id == security_id
                and by_market_key.currency == mapping.currency
            ):
                existing.append({"identity": identity, "listing_id": str(listing_id)})
            else:
                issues.append({"identity": identity, "issue": "LISTING_KEY_ALREADY_OWNED"})
            continue
        if by_id is not None and (
            security is None
            or by_id.security_id != security_id
            or by_id.venue != mapping.venue
            or by_id.ticker != mapping.ticker
        ):
            issues.append({"identity": identity, "issue": "CANONICAL_LISTING_ID_CONFLICT"})
            continue
        if security is not None and (
            security.company_id != company_id
            or security.security_type != mapping.security_type
            or security.share_class != mapping.canonical_share_class
        ):
            issues.append({"identity": identity, "issue": "CANONICAL_SECURITY_ID_CONFLICT"})
            continue
        additions.append(
            {
                "identity": identity,
                "company_id": str(company_id),
                "company_name": company.name,
                "security_id": str(security_id),
                "listing_id": str(listing_id),
                "security_type": mapping.security_type,
                "share_class": mapping.canonical_share_class,
                "currency": mapping.currency,
                "provider_symbol": mapping.provider_symbol,
                "source_ref": mapping.identity_source_ref,
                "needs_security": security is None,
            }
        )
    return {
        "status": "READY" if not issues else "DATA_CHECK",
        "provider_id": crosswalk.provider_id,
        "source_workbook": "reference/workbook/Market Data.xlsx",
        "candidate_count": len(additions),
        "already_present_count": len(existing),
        "unresolved": issues,
        "additions": additions,
    }


def apply_mapping_plan(session: Session, crosswalk: YahooListingCrosswalk) -> dict[str, Any]:
    report = build_mapping_plan(session, crosswalk)
    if report["unresolved"]:
        raise ValueError("Canonical listing import is blocked by unresolved identity conflicts")
    imported = 0
    for mapping in crosswalk.mappings:
        if mapping.identity_status != "READY_FOR_CANONICAL_IMPORT":
            continue
        if (
            mapping.canonical_company_id is None
            or mapping.canonical_company_name is None
            or mapping.canonical_security_id is None
            or mapping.canonical_listing_id is None
            or mapping.identity_source_ref is None
        ):
            continue
        current = session.get(Listing, mapping.canonical_listing_id)
        if current is not None:
            continue
        security = session.get(Security, mapping.canonical_security_id)
        if security is None:
            session.add(
                Security(
                    id=mapping.canonical_security_id,
                    company_id=mapping.canonical_company_id,
                    name=mapping.canonical_company_name,
                    security_type=mapping.security_type,
                    share_class=mapping.canonical_share_class,
                )
            )
            # Security and Listing are independent ORM mappers with a database FK.
            # Flush the parent explicitly; otherwise a later Listing lookup can
            # trigger autoflush before SQLAlchemy orders the new parent first.
            session.flush()
        session.add(
            Listing(
                id=mapping.canonical_listing_id,
                security_id=mapping.canonical_security_id,
                venue=mapping.venue,
                ticker=mapping.ticker,
                currency=mapping.currency,
                identity_source_ref=mapping.identity_source_ref,
            )
        )
        imported += 1
    session.flush()
    return {
        **report,
        "status": "APPLIED" if imported else "ALREADY_APPLIED",
        "imported_listing_count": imported,
        "imported_security_count": sum(
            bool(item["needs_security"]) for item in report["additions"]
        ),
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create reviewed listing identities.")
    parser.add_argument("--report", type=Path, help="Write a JSON preview or result report.")
    parser.add_argument("--crosswalk", type=Path, default=CROSSWALK_PATH)
    args = parser.parse_args(argv)
    engine = create_database_engine(Settings())
    if engine is None:
        parser.error("DATABASE_URL is required to resolve canonical company identities")
    try:
        crosswalk = load_yahoo_crosswalk(args.crosswalk)
        with Session(engine) as session:
            if args.apply:
                with session.begin():
                    report = apply_mapping_plan(session, crosswalk)
            else:
                report = build_mapping_plan(session, crosswalk)
            output = json.dumps(report, indent=2, sort_keys=True)
    finally:
        engine.dispose()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] not in {"DATA_CHECK"} else 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
