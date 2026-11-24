"""Alerts about events people saved: "Almost sold out" and "Price dropped".

Runs from the worker in the daytime (app/scheduler.py). Rules:

- Only saved events that haven't started (at least LEAD_HOURS away), published, not
  already bought or RSVP'd "going", not hidden, from people with event_alerts on.
- Almost sold out: event_features.sell_through_pct >= SOLD_OUT_PCT with tickets left.
- Price dropped: the cheapest ticket on sale now is at least DROP_PCT below the price when
  they saved it (event_saves.price_seen), or it became free. price_seen then moves to the
  new price, so a later drop can alert again.
- Limits per person: MAX_PER_DAY and MAX_PER_WEEK across both kinds (counted from their
  notifications), and never the same kind for the same event twice (except a further drop).
  Price drops go first, then the soonest event.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import EventFeatures
from app.models.event import Event, EventAttendee, EventSave
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification
from app.models.user import User
from app.services.hidden import hidden_for
from app.services.venue_access import notify

ALERT_TYPES = ("almost_sold_out", "price_drop")
SOLD_OUT_PCT = 0.85
DROP_PCT = 0.15
LEAD_HOURS = 3
MAX_PER_DAY = 1
MAX_PER_WEEK = 3


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def lowest_prices(db: AsyncSession, events: list[Event], now: datetime | None = None) -> dict[str, float | None]:
    """The cheapest ticket anyone can buy now: active, not members-only, on sale, not sold
    out. Events without ticket types fall back to their listed price (0 when free)."""
    now = now or datetime.now(timezone.utc)
    ids = [e.id for e in events]
    tiers = (await db.execute(select(TicketTier).where(TicketTier.event_id.in_(ids)))).scalars().all() if ids else []
    by_event: dict[str, list[TicketTier]] = defaultdict(list)
    for t in tiers:
        by_event[t.event_id].append(t)
    out: dict[str, float | None] = {}
    for e in events:
        own = by_event.get(e.id)
        if not own:
            out[e.id] = 0.0 if e.is_free else e.price_min
            continue
        on_sale = [t.price for t in own
                   if t.is_active and not t.members_only
                   and (t.quantity is None or t.quantity_sold < t.quantity)
                   and (t.sale_start is None or _utc(t.sale_start) <= now)
                   and (t.sale_end is None or _utc(t.sale_end) > now)]
        out[e.id] = min(on_sale) if on_sale else None
    return out


@dataclass
class _Alert:
    kind: str
    save: EventSave
    event: Event
    price: float | None = None


def _money(n: float) -> str:
    return "free" if n == 0 else f"₦{n:,.0f}"


async def send_event_alerts(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(
        select(EventSave, Event)
        .join(Event, Event.id == EventSave.event_id)
        .join(User, User.id == EventSave.user_id)
        .where(Event.status == "published", Event.start_date > now + timedelta(hours=LEAD_HOURS),
               User.event_alerts == True, User.is_active == True, User.is_deleted == False)  # noqa: E712
    )).all()
    if not rows:
        return {"alerts": 0}
    user_ids = {s.user_id for s, _ in rows}
    event_ids = {e.id for _, e in rows}

    committed = set((await db.execute(select(EventAttendee.user_id, EventAttendee.event_id).where(
        EventAttendee.status == "going", EventAttendee.event_id.in_(event_ids)))).all())
    committed |= set((await db.execute(select(TicketOrder.user_id, TicketOrder.event_id).where(
        TicketOrder.status == "confirmed", TicketOrder.event_id.in_(event_ids)))).all())
    feats = {f.event_id: f for f in (await db.execute(
        select(EventFeatures).where(EventFeatures.event_id.in_(event_ids)))).scalars().all()}
    prices = await lowest_prices(db, list({e.id: e for _, e in rows}.values()), now)

    sent_before = set((await db.execute(select(Notification.user_id, Notification.reference_id, Notification.type).where(
        Notification.user_id.in_(user_ids), Notification.type == "almost_sold_out"))).all())
    recent = (await db.execute(select(Notification.user_id, Notification.created_at).where(
        Notification.user_id.in_(user_ids), Notification.type.in_(ALERT_TYPES),
        Notification.created_at >= now - timedelta(days=7)))).all()
    week, day = defaultdict(int), defaultdict(int)
    for uid, at in recent:
        week[uid] += 1
        if _utc(at) >= now - timedelta(days=1):
            day[uid] += 1

    options: dict[str, list[_Alert]] = defaultdict(list)
    for save, event in rows:
        uid = save.user_id
        if (uid, event.id) in committed:
            continue
        price = prices.get(event.id)
        if save.price_seen is not None and price is not None and save.price_seen > 0 and (
                price == 0 or price <= save.price_seen * (1 - DROP_PCT)):
            options[uid].append(_Alert("price_drop", save, event, price))
        f = feats.get(event.id)
        if (f and f.sell_through_pct is not None and f.sell_through_pct >= SOLD_OUT_PCT
                and (f.remaining_tickets or 0) > 0 and (uid, event.id, "almost_sold_out") not in sent_before):
            options[uid].append(_Alert("almost_sold_out", save, event))

    sent = 0
    for uid, alerts in options.items():
        hidden = await hidden_for(db, uid)
        alerts = [a for a in alerts if not hidden.hides(a.event)]
        alerts.sort(key=lambda a: (a.kind != "price_drop", _utc(a.event.start_date)))
        room = min(MAX_PER_DAY - day[uid], MAX_PER_WEEK - week[uid])
        for a in alerts[:max(room, 0)]:
            if a.kind == "price_drop":
                was = a.save.price_seen
                notify(db, uid, "price_drop", f"Price dropped: {a.event.title}"[:200],
                       f"Tickets now from {_money(a.price)} (was {_money(was)}).",
                       reference_id=a.event.id, reference_type="event")
                a.save.price_seen = a.price
            else:
                left = feats[a.event.id].remaining_tickets
                notify(db, uid, "almost_sold_out", f"Almost sold out: {a.event.title}"[:200],
                       f"Only {left} ticket{'s' if left != 1 else ''} left for an event you saved.",
                       reference_id=a.event.id, reference_type="event")
            sent += 1
    await db.commit()
    return {"alerts": sent, "people": len(options)}


async def record_price_on_save(db: AsyncSession, save: EventSave, event: Event) -> None:
    save.price_seen = (await lowest_prices(db, [event])).get(event.id)
