"""Booking Q3 2026: primary SEC evidence to a reviewable, non-trading decision brief.

This narrowly scoped read-only pilot compares a verified filing with the
least-privilege canonical issuer context. It does not create proposals, accept
observations, write to a database or infer a valuation change.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from portfolio_api.company_agent_context import CompanyAgentContextV1
from portfolio_api.data_universe_proposal_handoff import prepare_handoff
from portfolio_api.data_universe_public_evidence import (
    BKNG_Q3_2026_CIK,
    BKNG_Q3_2026_URL,
    _booking_filing_values,
    _ReleaseHTML,
    fetch_official_booking_filing,
    verify_booking_q3_2026_pack,
)
from portfolio_api.data_universe_shadow import EvidencePackV1, _fetch_scoped_context
from portfolio_api.domain import schemas as s
from portfolio_api.settings import REPOSITORY_PATH


class BookingQuarterSignal(s.Contract):
    metric_key: str
    quarter: Literal["2026Q3"] = "2026Q3"
    prior_quarter: Literal["2025Q3"] = "2025Q3"
    reported_2026: Decimal
    reported_2025: Decimal
    reported_yoy_percent: Decimal
    unit: str
    scale: Decimal
    currency: str | None
    rounded_values: Literal[True] = True
    growth_basis: Literal["COMPANY_REPORTED_YOY"] = "COMPANY_REPORTED_YOY"
    source_reference: str


class BookingDecisionQuestion(s.Contract):
    key: str
    hypothesis_to_test: str
    supporting_metric_keys: list[str]
    missing_evidence: str
    proposed_model_change: None = None


class BookingEvidenceDecisionBrief(s.Contract):
    contract_type: Literal["BookingEvidenceDecisionBriefV1"] = "BookingEvidenceDecisionBriefV1"
    contract_version: Literal["1.0.0"] = "1.0.0"
    company_id: UUID
    issuer_cik: str = BKNG_Q3_2026_CIK
    issuer_ticker: Literal["BKNG"] = "BKNG"
    source_reference: str = BKNG_Q3_2026_URL
    source_published_on: date
    source_sha256: str
    source_checked_at: datetime
    context_known_at: datetime
    quarter_signals: list[BookingQuarterSignal]
    canonical_comparison_status: str
    canonical_findings: list[dict[str, str]]
    next_review_step: Literal[
        "REVIEW_METRIC_DEFINITIONS",
        "REVIEW_KPI_OBSERVATIONS",
        "ALREADY_MATCHED",
        "RESOLVE_CONFLICT",
        "CONTEXT_INCOMPLETE",
    ]
    ready_batch_type: str | None
    ready_external_batch_id: str | None
    deferred_batch_types: list[str]
    decision_questions: list[BookingDecisionQuestion]
    valuation_impact_status: Literal["NOT_ESTIMATED"] = "NOT_ESTIMATED"
    fair_value_change: None = None
    expected_irr_change: None = None
    accepted_model_changed: Literal[False] = False
    proposal_submitted: Literal[False] = False
    canonical_writes_performed: Literal[False] = False


_LABELS: tuple[tuple[str, str], ...] = (
    ("bkng.room_nights", "Room nights"),
    ("bkng.flight_tickets", "Flight tickets"),
    ("bkng.gross_bookings", "Total gross bookings"),
)


def _reported_yoy(cell_text: str) -> Decimal:
    match = re.fullmatch(r"\s*(\(?)(\d+(?:\.\d+)?)\)?\s*%\s*", cell_text)
    if match is None or cell_text.count("(") != cell_text.count(")"):
        raise ValueError("Quarterly growth percentage is malformed")
    number = Decimal(match.group(2))
    return -number if match.group(1) else number


def booking_quarter_signals(pack: EvidencePackV1, html: bytes) -> list[BookingQuarterSignal]:
    """Extract 2026/2025 *quarterly* comparatives and reported growth only.

    SEC tables also contain nine-month columns. Do not treat them as the
    quarter, or calculate a fake precise growth rate from rounded millions.
    """
    verified = verify_booking_q3_2026_pack(pack, html)
    if verified["status"] != "SOURCE_MATCHED":
        raise ValueError("Issuer source has not been verified")
    parser = _ReleaseHTML()
    parser.feed(html.decode("utf-8", errors="strict"))
    definitions = {row.metric_key: row for row in pack.metric_definitions}
    signals: list[BookingQuarterSignal] = []
    for key, label in _LABELS:
        matches: list[tuple[int, int, Decimal]] = []
        for table in parser.tables:
            values = _booking_filing_values(table, label)
            if values is None:
                continue
            rows = [row for row in table if row and row[0].casefold() == label.casefold()]
            if len(rows) != 1:
                raise ValueError("Booking metric row cannot be uniquely identified")
            # The source carries both three-month and nine-month rates.
            # The first is tied to the 2026/2025 quarterly column pair.
            percentages = re.findall(
                r"(?<![A-Za-z0-9])\(?\d+(?:\.\d+)?\)?\s*%",
                " ".join(rows[0][1:]),
            )
            if len(percentages) != 2:
                raise ValueError(f"Booking {label} reported quarter growth is ambiguous")
            growth = _reported_yoy(percentages[0])
            current, previous = values
            # The company rounds each figure to millions, so the growth
            # computed from the displayed totals can differ materially.
            # Accept only a stated growth that is plausible under rounding.
            low = (
                (Decimal(current) - Decimal("0.5")) / (Decimal(previous) + Decimal("0.5")) - 1
            ) * 100
            high = (
                (Decimal(current) + Decimal("0.5")) / (Decimal(previous) - Decimal("0.5")) - 1
            ) * 100
            if not low - Decimal("0.1") <= growth <= high + Decimal("0.1"):
                raise ValueError(f"Booking {label} growth contradicts rounded quarter values")
            matches.append((current, previous, growth))
        if len(matches) != 1:
            raise ValueError(f"Booking {label} comparison is missing or ambiguous")
        current, previous, growth = matches[0]
        definition = definitions[key]
        signals.append(
            BookingQuarterSignal(
                metric_key=key,
                reported_2026=Decimal(current),
                reported_2025=Decimal(previous),
                reported_yoy_percent=growth,
                unit=definition.canonical_unit,
                scale=definition.canonical_scale,
                currency="USD" if key == "bkng.gross_bookings" else None,
                source_reference=BKNG_Q3_2026_URL,
            )
        )
    return signals


def build_booking_decision_brief(
    context: CompanyAgentContextV1, pack: EvidencePackV1, html: bytes
) -> BookingEvidenceDecisionBrief:
    """Fail closed for changed issuer context or source; never estimate FV/IRR."""
    verification = verify_booking_q3_2026_pack(pack, html)
    handoff = prepare_handoff(context, pack, verification)
    signals = booking_quarter_signals(pack, html)
    status = handoff["shadow_status"]
    batches = handoff["ready_batches"]
    first = batches[0] if batches else None
    step: Literal[
        "REVIEW_METRIC_DEFINITIONS",
        "REVIEW_KPI_OBSERVATIONS",
        "ALREADY_MATCHED",
        "RESOLVE_CONFLICT",
        "CONTEXT_INCOMPLETE",
    ]
    if status == "NEEDS_HUMAN_RESOLUTION":
        step = "RESOLVE_CONFLICT"
    elif status == "INCOMPLETE_CONTEXT":
        step = "CONTEXT_INCOMPLETE"
    elif status == "MATCHED":
        step = "ALREADY_MATCHED"
    elif (
        first is not None
        and len(batches) == 1
        and first["contract_type"] == "MetricDefinitionBatchV1"
    ):
        step = "REVIEW_METRIC_DEFINITIONS"
    elif (
        first is not None
        and len(batches) == 1
        and first["contract_type"] == "KPIObservationBatchV1"
    ):
        step = "REVIEW_KPI_OBSERVATIONS"
    else:
        raise ValueError("Unexpected or unsafe observation-review handoff")

    questions = [
        BookingDecisionQuestion(
            key="DEMAND_AND_MONETIZATION",
            hypothesis_to_test=(
                "Does room-night growth, together with gross-bookings growth, "
                "support the accepted revenue-growth path after ADR, currency "
                "effects and booking mix are reconciled?"
            ),
            supporting_metric_keys=["bkng.room_nights", "bkng.gross_bookings"],
            missing_evidence=(
                "Revenue recognition, constant-currency ADR, merchant/agency "
                "mix and the current accepted model assumptions"
            ),
        ),
        BookingDecisionQuestion(
            key="FLIGHT_CONTRIBUTION",
            hypothesis_to_test=(
                "Is flight-ticket growth generating incremental economic value "
                "rather than only higher booking volume?"
            ),
            supporting_metric_keys=["bkng.flight_tickets"],
            missing_evidence=(
                "Flight economics, take rate, contribution margin and model-driver linkage"
            ),
        ),
        BookingDecisionQuestion(
            key="CASH_CONVERSION",
            hypothesis_to_test=(
                "Do cash generation and normalized margins support any revision "
                "to long-term free-cash-flow assumptions?"
            ),
            supporting_metric_keys=["bkng.gross_bookings"],
            missing_evidence=(
                "Reported cash-flow statement, adjustments, capital requirements "
                "and accepted FCF projection"
            ),
        ),
    ]
    return BookingEvidenceDecisionBrief(
        company_id=context.company.id,
        source_published_on=pack.source_published_on,
        source_sha256=verification["source_sha256"],
        source_checked_at=datetime.fromisoformat(verification["checked_at"]),
        context_known_at=context.known_at,
        quarter_signals=signals,
        canonical_comparison_status=status,
        canonical_findings=handoff["findings"],
        next_review_step=step,
        ready_batch_type=first["contract_type"] if first else None,
        ready_external_batch_id=first["external_batch_id"] if first else None,
        deferred_batch_types=handoff["deferred_batch_types"],
        decision_questions=questions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument(
        "--api-base-url", help="Approved HTTPS API; scoped read token from environment"
    )
    origin.add_argument("--context-file", type=Path, help="Isolated offline scoped context JSON")
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--source-pack", type=Path, required=True)
    parser.add_argument("--source-html", type=Path, help="Only for an isolated offline context")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.expanduser().resolve()
    if target.is_relative_to(REPOSITORY_PATH.resolve()) or target.exists():
        parser.error("Private report must be outside the repository and not overwrite a file")
    if (args.context_file is None) != (args.source_html is None):
        parser.error("Offline contexts require offline issuer HTML; live API requires live SEC")
    pack = EvidencePackV1.model_validate_json(args.source_pack.read_text(encoding="utf-8"))
    if args.api_base_url is None:
        assert args.context_file is not None and args.source_html is not None
        context_data = json.loads(args.context_file.read_text(encoding="utf-8"))
        html = args.source_html.read_bytes()
    else:
        # Always fetch public SEC evidence before sending the private scoped
        # request, and never accept a local HTML substitute on the live path.
        html = fetch_official_booking_filing(pack)
        context_data = _fetch_scoped_context(args.api_base_url, args.company_id)
    context = CompanyAgentContextV1.model_validate(context_data)
    if context.company.id != args.company_id:
        raise ValueError("Scoped company identity does not match the requested UUID")
    brief = build_booking_decision_brief(context, pack, html)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(brief.model_dump(mode="json"), stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        f"{brief.next_review_step}: {len(brief.quarter_signals)} sourced metrics, "
        "no model/portfolio writes; private brief created"
    )


if __name__ == "__main__":
    main()
