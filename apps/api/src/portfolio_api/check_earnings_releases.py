"""Run the same release check as the inbox for supported held listings."""

import argparse
from uuid import UUID

from sqlalchemy.orm import Session

from portfolio_api import earnings_release_source as source
from portfolio_api.database import create_database_engine
from portfolio_api.earnings_inbox import earnings_inbox
from portfolio_api.earnings_release_review import check_release
from portfolio_api.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", required=True, type=UUID)
    args = parser.parse_args()
    settings = Settings()
    if not (settings.recurring_operations_enabled and settings.earnings_release_checks_enabled):
        parser.error("Recurring operations must be explicitly enabled")
    engine = create_database_engine(
        settings, write_operation="scheduled_earnings_drafts", write_operation_kind="ingestion"
    )
    if engine is None:
        parser.error("Database target is missing")
    failures = 0
    try:
        with Session(engine) as db:
            scope = {
                row.listing_id: row.listing
                for row in earnings_inbox(db, args.portfolio).rows
                if row.listing in source.ISSUERS and row.revision_number
            }
        for listing_id, listing in scope.items():
            try:
                with Session(engine) as db, db.begin():
                    result = check_release(db, settings, args.portfolio, listing_id)
                print(listing, result.message)
            except Exception as error:
                failures += 1
                print(listing, "Check failed:", type(error).__name__)
    finally:
        engine.dispose()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
