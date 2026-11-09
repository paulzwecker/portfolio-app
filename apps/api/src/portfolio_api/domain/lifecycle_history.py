"""Point-in-time lifecycle selection from the canonical append-only event stream."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from portfolio_api.domain.models import Company, LifecycleEvent


def lifecycle_events_at(session: Session, cutoff: datetime) -> list[tuple[Company, LifecycleEvent]]:
    """Select the latest known sequence before filtering to active lifecycle states."""
    ranked = (
        select(
            LifecycleEvent.id.label("event_id"),
            func.row_number()
            .over(
                partition_by=LifecycleEvent.company_id,
                order_by=LifecycleEvent.sequence.desc(),
            )
            .label("position"),
        )
        .where(LifecycleEvent.effective_at <= cutoff, LifecycleEvent.recorded_at <= cutoff)
        .subquery()
    )
    rows = session.execute(
        select(Company, LifecycleEvent)
        .join(LifecycleEvent, LifecycleEvent.company_id == Company.id)
        .join(ranked, ranked.c.event_id == LifecycleEvent.id)
        .where(ranked.c.position == 1, Company.created_at <= cutoff)
        .order_by(Company.name, Company.id)
    )
    return [(company, event) for company, event in rows]
