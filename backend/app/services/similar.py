"""Similar events, and "people who went to X also went to Y" (docs/recommendations-spec.md).

Two sources, merged:

1. Co-commitment: people who committed to X (going, saved, or bought a ticket) and also
   committed to another upcoming event. Scored by shared people ÷ √(that event's own
   committed people), so a huge event everyone goes to doesn't win by size alone. An event
   needs at least MIN_SHARED_PEOPLE in common, so no suggestion ever points at what one
   identifiable person did.
2. Content: same category, shared tags, same city, a similar price, weighted by demand.
   Fills the list for new events with little history.

Upcoming, published events only; never X itself, the viewer's own events, events they've
already committed to, or anything they've hidden.
"""
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity import EventFeatures
from app.models.event import Event, EventAttendee, EventSave
from app.models.organizer import TicketOrder
from app.models.user import User
from app.services.hidden import hidden_for

MIN_SHARED_PEOPLE = 2
MAX_CANDIDATES = 300
CO_WEIGHT = 3.0


@dataclass
class Similar:
    event: Event
    score: float
    reason: str


def _committed():
    """(user_id, event_id) for every going RSVP, save and confirmed order."""
    return union_all(
        select(EventAttendee.user_id, EventAttendee.event_id).where(EventAttendee.status == "going"),
        select(EventSave.user_id, EventSave.event_id),
        select(TicketOrder.user_id, TicketOrder.event_id).where(TicketOrder.status == "confirmed"),
    ).subquery()


def _tags(e: Event) -> set[str]:
    return {t.strip().lower() for t in (e.tags or "").split(",") if t.strip()}


def _upcoming(now: datetime):
    return (select(Event).options(selectinload(Event.host).selectinload(User.organizer_profile),
                                  selectinload(Event.category))
            .where(Event.status == "published", Event.review_status == "approved", Event.end_date > now))


async def _viewer_exclusions(db: AsyncSession, viewer: User | None) -> tuple[set[str], set[str]]:
    if viewer is None:
        return set(), set()
    c = _committed()
    mine = set((await db.execute(select(c.c.event_id).where(c.c.user_id == viewer.id))).scalars().all())
    hidden = await hidden_for(db, viewer)
    return mine | hidden.event_ids, hidden.organizer_ids | {viewer.id}


async def similar_events(db: AsyncSession, source: Event, viewer: User | None = None,
                         limit: int = 6, now: datetime | None = None) -> list[Similar]:
    now = now or datetime.now(timezone.utc)
    skip_events, skip_hosts = await _viewer_exclusions(db, viewer)
    skip_events.add(source.id)

    def allowed(e: Event) -> bool:
        return e.id not in skip_events and e.host_id not in skip_hosts

    # 1. Co-commitment
    c = _committed()
    people = select(c.c.user_id).where(c.c.event_id == source.id).distinct()
    rows = (await db.execute(
        select(c.c.event_id, c.c.user_id).where(c.c.user_id.in_(people), c.c.event_id != source.id).distinct()
    )).all()
    shared = Counter(eid for eid, _ in rows)
    shared = Counter({eid: n for eid, n in shared.items() if n >= MIN_SHARED_PEOPLE})

    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    events: dict[str, Event] = {}
    if shared:
        found = (await db.execute(_upcoming(now).where(Event.id.in_(list(shared))))).scalars().all()
        sizes = Counter(eid for eid, in (await db.execute(
            select(c.c.event_id).where(c.c.event_id.in_([e.id for e in found])))).all())
        for e in found:
            if not allowed(e):
                continue
            events[e.id] = e
            scores[e.id] = CO_WEIGHT * shared[e.id] / math.sqrt(max(sizes[e.id], 1))
            reasons[e.id] = "People who went to this also went"

    # 2. Content
    conditions = []
    if source.category_id:
        conditions.append(Event.category_id == source.category_id)
    for tag in list(_tags(source))[:5]:
        conditions.append(Event.tags.ilike(f"%{tag}%"))
    if conditions:
        content = (await db.execute(
            _upcoming(now).where(or_(*conditions), Event.id != source.id)
            .order_by(Event.start_date.asc()).limit(MAX_CANDIDATES)
        )).scalars().all()
        ids = [e.id for e in content]
        demand = dict((await db.execute(select(EventFeatures.event_id, EventFeatures.demand_score)
                                        .where(EventFeatures.event_id.in_(ids)))).all()) if ids else {}
        src_tags = _tags(source)
        src_price = source.price_min if not source.is_free else 0
        for e in content:
            if not allowed(e):
                continue
            s = 0.0
            if source.category_id and e.category_id == source.category_id:
                s += 1.0
            s += 0.4 * min(len(src_tags & _tags(e)), 3)
            if source.city and e.city and source.city.strip().lower() == e.city.strip().lower():
                s += 0.6
            price = e.price_min if not e.is_free else 0
            if src_price is not None and price is not None:
                hi, lo = max(src_price, price), min(src_price, price)
                if hi == 0 or (lo > 0 and hi / lo <= 2):
                    s += 0.3
            s += 0.5 * demand.get(e.id, min(math.log1p(e.attendees_count + e.saves_count) / math.log1p(500), 1.0))
            if s < 1.0:
                continue  # one weak overlap isn't "similar"
            events.setdefault(e.id, e)
            scores[e.id] = scores.get(e.id, 0.0) + s
            reasons.setdefault(e.id, f"More {e.category.name}" if e.category and e.category_id == source.category_id
                               else "Similar to this event")

    ranked = sorted(scores, key=lambda i: (-scores[i], events[i].start_date))
    # At most two from one organizer, so the list isn't one host's calendar.
    per_host: Counter = Counter()
    out: list[Similar] = []
    for eid in ranked:
        e = events[eid]
        if per_host[e.host_id] >= 2:
            continue
        per_host[e.host_id] += 1
        out.append(Similar(event=e, score=scores[eid], reason=reasons[eid]))
        if len(out) >= limit:
            break
    return out
