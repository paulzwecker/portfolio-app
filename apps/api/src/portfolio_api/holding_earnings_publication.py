"""Preview and publish owner-reviewed earnings assessments for an exact portfolio snapshot."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api.database import create_database_engine
from portfolio_api.domain import queries, services
from portfolio_api.domain.models import FinancialModel
from portfolio_api.domain.schemas import Contract, ResearchRevisionPublishContract
from portfolio_api.domain.services import DomainError
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


class BatchInput(Contract):
    snapshot_id: UUID
    assessments: list[dict[str, object]] = Field(min_length=1, max_length=100)


class PublishInput(BatchInput):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class PreviewItem(Contract):
    listing: str
    revision: int
    conclusion: str
    driver: str
    accepted_value: str
    comparable_period: str
    rationale: str
    source: str
    passage: str


class BatchResult(Contract):
    digest: str
    items: list[PreviewItem]
    revision_ids: list[UUID]


def review_batch(db: Session, portfolio_id: UUID, value: BatchInput) -> BatchResult:
    if isinstance(value, PublishInput):
        services.portfolio(db, portfolio_id, lock=True)
    inbox = earnings_inbox(db, portfolio_id)
    if isinstance(value, PublishInput):
        names = {str(item.get("listing")) for item in value.assessments}
        ids_to_lock = {row.listing_id for row in inbox.rows if row.listing in names}
        db.scalars(
            select(FinancialModel.id)
            .where(
                FinancialModel.valuation_listing_id.in_(ids_to_lock),
                FinancialModel.model_type == "UFCF_DCF_10Y_FADE",
            )
            .order_by(FinancialModel.id)
            .with_for_update()
        ).all()
    if inbox.snapshot_id != value.snapshot_id:
        raise DomainError("Holdings changed. Refresh the inbox and preview again.", 409)
    try:
        packets = plan(db, inbox, value.assessments)
    except (KeyError, TypeError, ValueError) as error:
        raise DomainError(
            "Check the listing, accepted revision, driver and evidence.", 422
        ) from error
    manifest = [
        str(portfolio_id),
        str(value.snapshot_id),
        [packet.model_dump(mode="json") for packet in packets],
    ]
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    items = []
    for assessment, packet in zip(value.assessments, packets, strict=True):
        review = packet.earnings_review
        evidence = next(
            (
                item
                for item in packet.evidence
                if str(item.source_url) == packet.source_reference and item.excerpt
            ),
            None,
        )
        if (
            review is None
            or evidence is None
            or not packet.source_reference.startswith("https://")
            or packet.status.value != "PUBLISHED"
            or packet.forecasts
            or packet.trigger_references
        ):
            raise DomainError("Provide a cited earnings assessment for the selected holding.", 422)
        items.append(
            PreviewItem(
                listing=str(assessment["listing"]),
                revision=int(str(assessment["revision_number"])),
                conclusion=review.conclusion,
                driver=review.driver,
                accepted_value=f"{review.accepted_base_year_one:.2%}",
                comparable_period=review.comparable_period,
                rationale=packet.rationale,
                source=packet.source_reference,
                passage=evidence.excerpt or "",
            )
        )
    ids = []
    if isinstance(value, PublishInput):
        if digest != value.digest:
            raise DomainError("Reviewed packets or accepted revisions changed. Preview again.", 409)
        for packet in packets:
            revision, _ = publish_research_revision(db, packet)
            ids.append(revision.id)
        updated = earnings_inbox(db, portfolio_id)
        visible = {(r.listing_id, r.url) for r in updated.rows if r.passage}
        if updated.snapshot_id != value.snapshot_id or any(
            packet.earnings_review is None
            or (packet.earnings_review.listing_id, packet.source_reference) not in visible
            for packet in packets
        ):
            raise DomainError("Publication could not be verified in the current inbox.", 409)
    return BatchResult(digest=digest, items=items, revision_ids=ids)


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
