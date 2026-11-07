"""Read-only opening reconciliation and exact settled-booking projections."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_api import portfolio_ledger_contracts as c
from portfolio_api.domain import queries, services
from portfolio_api.domain.models import HoldingSnapshot, Listing, Security


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _listing_identities(session: Session, ids: set[UUID]) -> dict[UUID, c.LedgerListingRead]:
    rows = session.execute(
        select(Listing, Security)
        .join(Security, Security.id == Listing.security_id)
        .where(Listing.id.in_(ids))
        .order_by(Listing.id)
    ).all()
    if len(rows) != len(ids):
        raise services.DomainError(
            "Every ledger position needs an existing exact listing", status=422
        )
    result = {}
    for listing, security in rows:
        if listing.currency is None or security.security_type not in {
            "COMMON_STOCK",
            "ADR",
            "PREFERRED",
            "ETF",
        }:
            raise services.DomainError(
                "Ledger listings require a supported security and currency", status=422
            )
        result[listing.id] = c.LedgerListingRead(
            listing_id=listing.id,
            security_id=security.id,
            company_id=security.company_id,
            ticker=listing.ticker,
            venue=listing.venue,
            currency=listing.currency,
            security_type=security.security_type,
            identity_source_ref=listing.identity_source_ref,
        )
    return result


def portfolio_ledger_anchor(session: Session, portfolio_id: UUID) -> c.PortfolioLedgerAnchorRead:
    services.portfolio(session, portfolio_id)
    known_at = datetime.now(UTC)
    snapshot = session.scalar(
        select(HoldingSnapshot)
        .where(
            HoldingSnapshot.portfolio_id == portfolio_id,
            HoldingSnapshot.effective_at <= known_at,
            HoldingSnapshot.recorded_at <= known_at,
        )
        .order_by(HoldingSnapshot.effective_at.desc(), HoldingSnapshot.recorded_at.desc())
        .limit(1)
    )
    if snapshot is None or snapshot.completeness != "COMPLETE":
        raise services.DomainError(
            "Ledger preview requires the current complete observed snapshot", status=409
        )
    try:
        view = queries.snapshot_read(session, snapshot)
    except ValueError:
        raise services.DomainError(
            "Ledger anchor contains unavailable or invalid balances", status=409
        ) from None
    view = view.model_copy(
        update={
            "positions": sorted(view.positions, key=lambda item: str(item.listing_id)),
            "cash_positions": sorted(view.cash_positions, key=lambda item: item.currency),
        }
    )
    listings = list(_listing_identities(session, {p.listing_id for p in view.positions}).values())
    payload = {
        "contract_version": "portfolio-ledger-preview-v1",
        "snapshot": view.model_dump(mode="json"),
        "listings": [item.model_dump(mode="json") for item in listings],
    }
    return c.PortfolioLedgerAnchorRead(
        portfolio_id=portfolio_id, snapshot=view, listings=listings, anchor_sha256=_digest(payload)
    )


def _totals[Key: (UUID, str)](states: Mapping[UUID, Mapping[Key, Decimal]]) -> dict[Key, Decimal]:
    totals: dict[Key, Decimal] = {}
    for balances in states.values():
        for key, amount in balances.items():
            totals[key] = totals.get(key, Decimal(0)) + amount
    return totals


def _reconciliation[Key: (UUID, str)](
    domain: Literal["POSITION", "CASH"],
    observed: Mapping[Key, Decimal],
    opening: Mapping[Key, Decimal],
) -> list[c.LedgerReconciliationRead]:
    result = []
    for key in sorted(observed.keys() | opening.keys(), key=str):
        expected, proposed = observed.get(key), opening.get(key)
        status: Literal["MATCH", "MISSING_OPENING", "EXTRA_OPENING", "DIFFERENCE"] = "MATCH"
        if proposed is None:
            status = "MISSING_OPENING"
        elif expected is None:
            status = "EXTRA_OPENING"
        elif expected != proposed:
            status = "DIFFERENCE"
        result.append(
            c.LedgerReconciliationRead(
                domain=domain,
                key=str(key),
                observed=expected,
                opening=proposed,
                status=status,
                difference=proposed - expected
                if proposed is not None and expected is not None
                else None,
            )
        )
    return result


def project_ledger(
    anchor: c.PortfolioLedgerAnchorRead,
    value: c.PortfolioLedgerPreviewCreate,
    listings: Mapping[UUID, c.LedgerListingRead],
) -> c.PortfolioLedgerPreviewRead:
    """Pure replay. A reconciled preview grants no acceptance or persistence authority."""
    if (
        anchor.snapshot.completeness != "COMPLETE"
        or any(p.quantity is None for p in anchor.snapshot.positions)
        or any(p.balance is None for p in anchor.snapshot.cash_positions)
    ):
        raise services.DomainError(
            "Ledger preview requires verified complete opening balances", status=409
        )
    if (
        value.anchor_snapshot_id != anchor.snapshot.id
        or value.anchor_sha256 != anchor.anchor_sha256
    ):
        raise services.DomainError(
            "The ledger anchor changed; review the current snapshot again", status=409
        )
    if value.as_of < anchor.snapshot.effective_at:
        raise services.DomainError(
            "The projection cutoff precedes the opening snapshot", status=422
        )
    accounts = {a.account_id: a for a in value.accounts}
    listing_ids = {p.listing_id for a in value.accounts for p in a.positions} | {
        a.listing_id for a in value.activity if isinstance(a, c.LedgerTrade)
    }
    if not listing_ids <= listings.keys():
        raise services.DomainError(
            "Every ledger position needs an existing exact listing", status=422
        )
    for item in value.activity:
        if item.account_id not in accounts or accounts[item.account_id].kind != "BROKERAGE":
            raise services.DomainError(
                "Activity needs an explicitly evidenced brokerage account", status=422
            )
        if not anchor.snapshot.effective_at < item.effective_at <= value.as_of:
            raise services.DomainError(
                "All activity must be after the opening and within the cutoff", status=422
            )
        if isinstance(item, c.LedgerTrade):
            if item.currency != listings[item.listing_id].currency:
                raise services.DomainError(
                    "Trade cash currency must match the exact listing currency", status=422
                )
            if (
                item.trade_date > item.settlement_date
                or item.settlement_date > item.effective_at.date()
            ):
                raise services.DomainError(
                    "Only settled trades within the source booking date are supported", status=422
                )

    ordered_accounts = sorted(value.accounts, key=lambda a: str(a.account_id))
    activity = sorted(value.activity, key=lambda a: (a.effective_at, a.sequence))
    payload = value.model_dump(mode="json")
    payload["accounts"] = [
        a.model_copy(
            update={
                "positions": sorted(a.positions, key=lambda p: str(p.listing_id)),
                "cash": sorted(a.cash, key=lambda p: p.currency),
            }
        ).model_dump(mode="json")
        for a in ordered_accounts
    ]
    payload["activity"] = [a.model_dump(mode="json") for a in activity]
    payload["listing_identities"] = [
        listings[key].model_dump(mode="json") for key in sorted(listing_ids, key=str)
    ]
    positions = {
        a.account_id: {p.listing_id: p.quantity for p in a.positions} for a in value.accounts
    }
    cash = {a.account_id: {p.currency: p.balance for p in a.cash} for a in value.accounts}
    with localcontext() as context:
        context.prec = 80
        reconciliation = _reconciliation(
            "POSITION",
            {p.listing_id: p.quantity for p in anchor.snapshot.positions if p.quantity is not None},
            _totals(positions),
        ) + _reconciliation(
            "CASH",
            {
                p.currency: p.balance
                for p in anchor.snapshot.cash_positions
                if p.balance is not None
            },
            _totals(cash),
        )
        issues = [
            c.LedgerIssueRead(
                code="OPENING_MISMATCH", activity_id=None, account_id=None, asset_key=r.key
            )
            for r in reconciliation
            if r.status != "MATCH"
        ]
        if not issues:
            for item in activity:
                account_cash = cash[item.account_id]
                if isinstance(item, c.LedgerTrade):
                    account_positions = positions[item.account_id]
                    quantity = item.quantity if item.kind == "BUY" else -item.quantity
                    account_positions[item.listing_id] = (
                        account_positions.get(item.listing_id, Decimal(0)) + quantity
                    )
                    amount = -item.gross_cash if item.kind == "BUY" else item.gross_cash
                    amount -= item.fees + item.taxes
                    if account_positions[item.listing_id] < 0:
                        issues.append(
                            c.LedgerIssueRead(
                                code="NEGATIVE_POSITION",
                                activity_id=item.id,
                                account_id=item.account_id,
                                asset_key=str(item.listing_id),
                            )
                        )
                else:
                    amount = item.amount if item.kind == "DEPOSIT" else -item.amount
                account_cash[item.currency] = account_cash.get(item.currency, Decimal(0)) + amount
                if account_cash[item.currency] < 0:
                    issues.append(
                        c.LedgerIssueRead(
                            code="NEGATIVE_CASH",
                            activity_id=item.id,
                            account_id=item.account_id,
                            asset_key=item.currency,
                        )
                    )
            for account_id in positions:
                for key, amount in [*positions[account_id].items(), *cash[account_id].items()]:
                    if abs(amount) >= Decimal("1e18"):
                        issues.append(
                            c.LedgerIssueRead(
                                code="BALANCE_OUT_OF_RANGE",
                                activity_id=None,
                                account_id=account_id,
                                asset_key=str(key),
                            )
                        )
        opening_matches = all(r.status == "MATCH" for r in reconciliation)
        projected_positions = _totals(positions) if opening_matches else {}
        projected_cash = _totals(cash) if opening_matches else {}
        for key, amount in [*projected_positions.items(), *projected_cash.items()]:
            if abs(amount) >= Decimal("1e18"):
                issues.append(
                    c.LedgerIssueRead(
                        code="BALANCE_OUT_OF_RANGE",
                        activity_id=None,
                        account_id=None,
                        asset_key=str(key),
                    )
                )
        return c.PortfolioLedgerPreviewRead(
            contract_version=value.contract_version,
            projection_version="settled-booking-v1",
            preview_only=True,
            status="BLOCKED" if issues else "OPENING_RECONCILED",
            portfolio_id=anchor.portfolio_id,
            anchor_snapshot_id=anchor.snapshot.id,
            anchor_recorded_at=anchor.snapshot.recorded_at,
            anchor_sha256=anchor.anchor_sha256,
            input_sha256=_digest(payload),
            as_of=value.as_of,
            opening_reconciliation=reconciliation,
            activity_count=len(activity),
            issues=issues,
            accounts=[
                c.LedgerAccountProjectionRead(
                    account_id=a.account_id,
                    positions=[
                        c.LedgerPositionRead(listing_id=k, quantity=v)
                        for k, v in sorted(positions[a.account_id].items(), key=lambda p: str(p[0]))
                    ],
                    cash=[
                        c.LedgerCashRead(currency=k, balance=v)
                        for k, v in sorted(cash[a.account_id].items())
                    ],
                )
                for a in ordered_accounts
            ]
            if opening_matches
            else [],
            positions=[
                c.LedgerPositionRead(listing_id=k, quantity=v)
                for k, v in sorted(projected_positions.items(), key=lambda p: str(p[0]))
            ],
            cash=[
                c.LedgerCashRead(currency=k, balance=v) for k, v in sorted(projected_cash.items())
            ],
        )


def preview_portfolio_ledger(
    session: Session, portfolio_id: UUID, value: c.PortfolioLedgerPreviewCreate
) -> c.PortfolioLedgerPreviewRead:
    anchor = portfolio_ledger_anchor(session, portfolio_id)
    ids = {p.listing_id for a in value.accounts for p in a.positions} | {
        a.listing_id for a in value.activity if isinstance(a, c.LedgerTrade)
    }
    return project_ledger(anchor, value, _listing_identities(session, ids))
