"""Preview and publish owner-reviewed earnings assessments for an exact portfolio snapshot."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain import queries
from portfolio_api.domain.models import FinancialModel
from portfolio_api.domain.schemas import ResearchRevisionPublishContract
from portfolio_api.earnings_inbox import Inbox, earnings_inbox
from portfolio_api.earnings_review_packet import bind_assessment
from portfolio_api.research_forecasts import publish_research_revision
from portfolio_api.settings import Settings


def plan(
    db: Session, inbox: Inbox, assessments: list[dict[str, object]]
) -> list[ResearchRevisionPublishContract]:
    if not assessments:
        raise ValueError("No assessments supplied")
    listings = {row.listing: row.listing_id for row in inbox.rows if row.revision_number}
    packets = []
    seen: set[tuple[str, str]] = set()
    for assessment in assessments:
        listing_id = listings.get(str(assessment.get("listing")))
        if listing_id is None:
            raise ValueError("Assessment must target a modeled listing in the complete snapshot")
        model = db.scalars(
            select(FinancialModel).where(
                FinancialModel.valuation_listing_id == listing_id,
                FinancialModel.model_type == "UFCF_DCF_10Y_FADE",
            )
        ).one()
        packet = bind_assessment(queries.financial_model(db, model.id), assessment)
        key = (packet.stream_key, packet.external_revision_id)
        if key in seen:
            raise ValueError("Duplicate assessment in the reviewed batch")
        seen.add(key)
        packets.append(packet)
    return packets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", required=True, type=UUID)
    parser.add_argument("--snapshot", required=True, type=UUID)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--assessment", type=Path, action="append")
    inputs.add_argument(
        "--pending", action="store_true", help="List publications awaiting assessment"
    )
    parser.add_argument("--apply-digest", help="Apply the exact SHA-256 printed by preview")
    args = parser.parse_args()
    if args.pending and args.apply_digest:
        parser.error("--pending is read-only")
    engine = create_database_engine(
        Settings(),
        read_only=args.apply_digest is None,
        write_operation="holding_earnings_publication",
        write_operation_kind="application",
    )
    if engine is None:
        parser.error("Configure the verified database target")
    try:
        with Session(engine) as db, db.begin():
            inbox = earnings_inbox(db, args.portfolio)
            if inbox.snapshot_id != args.snapshot:
                raise ValueError("Portfolio snapshot changed; review current holdings")
            if args.pending:
                for row in inbox.rows:
                    if row.url and row.revision_number and row.outcome == "Awaiting assessment":
                        print(
                            row.model_dump_json(
                                include={
                                    "listing",
                                    "listing_id",
                                    "company_id",
                                    "revision_number",
                                    "title",
                                    "url",
                                    "period",
                                    "published_at",
                                }
                            )
                        )
                return
            packets = plan(db, inbox, [json.loads(p.read_bytes()) for p in args.assessment])
            manifest = [
                str(args.portfolio),
                str(args.snapshot),
                [packet.model_dump(mode="json") for packet in packets],
            ]
            digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            if args.apply_digest is None:
                print(f"Previewed {len(packets)} assessments. SHA-256 {digest}")
                return
            if args.apply_digest != digest:
                raise ValueError("Reviewed packets or accepted revisions changed")
            receipts = []
            for packet in packets:
                revision, status = publish_research_revision(db, packet)
                receipts.append((revision.id, status))
            result = earnings_inbox(db, args.portfolio)
            if result.snapshot_id != args.snapshot:
                raise ValueError("Portfolio snapshot changed during publication")
            visible = {(row.listing_id, row.url) for row in result.rows if row.passage}
            for packet in packets:
                review = packet.earnings_review
                if review is None or (review.listing_id, packet.source_reference) not in visible:
                    raise ValueError("Published review missing from the portfolio inbox")
        for revision_id, status in receipts:
            print(status, revision_id)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
