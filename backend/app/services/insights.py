"""Organizer insights: what people searched for and didn't find, when events like theirs do
best, how their price compares, and how their bookings are pacing.

Everything here is aggregated across many people or events, with minimums (MIN_SEARCHERS,
MIN_EVENTS_PER_BUCKET, MIN_COMPARABLES) so no figure describes one identifiable person or
one other organizer's event.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.event import Category, Event, EventAttendee
from app.models.organizer import TicketOrder, TicketTier
from app.services.rec_features import LAGOS

MIN_SEARCHERS = 3
MIN_EVENTS_PER_BUCKET = 3
MIN_COMPARABLES = 5
CURVE_DAYS = (30, 21, 14, 7, 3, 1, 0)
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def part_of_day(hour: int) -> str:
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "late"


# ── Searches nobody could satisfy ───────────────────────────────────────────────


async def unmet_searches(db: AsyncSession, city: str | None = None, days: int = 30, limit: int = 10,
                         now: datetime | None = None) -> list[dict]:
    """Searches that found nothing, by how many different people made them (at least
    MIN_SEARCHERS). With `city`, only searches filtered to or made from that city."""
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(select(Activity.props, Activity.user_id, Activity.anonymous_id, Activity.geo_city).where(
        Activity.name == "search_executed", Activity.occurred_at >= now - timedelta(days=days),
        Activity.occurred_at <= now))).all()
    people: dict[str, set] = defaultdict(set)
    for props, uid, anon, geo_city in rows:
        props = props or {}
        if props.get("results_count") != 0:
            continue
        q = (props.get("query") or (f"#{props['tag']}" if props.get("tag") else "") or "").strip().lower()
        if not q:
            continue
        if city:
            where = ((props.get("filters") or {}).get("city") or geo_city or "").lower()
            if city.strip().lower() not in where:
                continue
        people[" ".join(q.split())[:80]].add(uid or anon)
    ranked = sorted(((q, len(who)) for q, who in people.items() if len(who) >= MIN_SEARCHERS),
                    key=lambda x: (-x[1], x[0]))
    return [{"query": q, "people": n} for q, n in ranked[:limit]]


# ── Turnout per event ───────────────────────────────────────────────────────────


async def _turnout(db: AsyncSession, ids: list[str]) -> Counter:
    """People going (RSVPs) plus tickets sold, per event."""
    if not ids:
        return Counter()
    out = Counter(dict((await db.execute(select(EventAttendee.event_id, func.count()).where(
        EventAttendee.event_id.in_(ids), EventAttendee.status == "going")
        .group_by(EventAttendee.event_id))).all()))
    out.update(dict((await db.execute(select(TicketOrder.event_id, func.sum(TicketOrder.quantity)).where(
        TicketOrder.event_id.in_(ids), TicketOrder.status == "confirmed")
        .group_by(TicketOrder.event_id))).all()))
    return out


async def _comparables(db: AsyncSession, event: Event, now: datetime, *, past_only: bool, same_city: bool) -> list[Event]:
    q = select(Event).where(Event.status.in_(("published", "completed")), Event.id != event.id,
                            Event.host_id != event.host_id,
                            Event.start_date >= now - timedelta(days=365))
    if event.category_id:
        q = q.where(Event.category_id == event.category_id)
    if same_city and event.city:
        q = q.where(func.lower(Event.city) == event.city.strip().lower())
    q = q.where(Event.end_date < now) if past_only else q.where(Event.start_date <= now + timedelta(days=120))
    return list((await db.execute(q.limit(2000))).scalars().all())


# ── Best day and time ───────────────────────────────────────────────────────────


async def best_times(db: AsyncSession, event: Event, now: datetime) -> dict | None:
    scope = "city"
    past = await _comparables(db, event, now, past_only=True, same_city=True)
    if len(past) < MIN_EVENTS_PER_BUCKET * 4:
        scope, past = "everywhere", await _comparables(db, event, now, past_only=True, same_city=False)
    turnout = await _turnout(db, [e.id for e in past])
    buckets: dict[tuple[int, str], list[int]] = defaultdict(list)
    for e in past:
        local = _utc(e.start_date).astimezone(LAGOS)
        buckets[(local.weekday(), part_of_day(local.hour))].append(turnout[e.id])
    rows = [{"day": DAYS[d], "part": p, "events": len(v), "avg_turnout": round(sum(v) / len(v), 1)}
            for (d, p), v in buckets.items() if len(v) >= MIN_EVENTS_PER_BUCKET]
    if not rows:
        return None
    rows.sort(key=lambda r: -r["avg_turnout"])
    mine = _utc(event.start_date).astimezone(LAGOS)
    yours = {"day": DAYS[mine.weekday()], "part": part_of_day(mine.hour)}
    match = next((r for r in rows if r["day"] == yours["day"] and r["part"] == yours["part"]), None)
    return {"scope": scope, "best": rows[:3], "yours": {**yours, "avg_turnout": match["avg_turnout"] if match else None}}


# ── Price ───────────────────────────────────────────────────────────────────────


async def _cheapest(db: AsyncSession, events: list[Event]) -> dict[str, float | None]:
    ids = [e.id for e in events]
    tiers = dict((await db.execute(select(TicketTier.event_id, func.min(TicketTier.price)).where(
        TicketTier.event_id.in_(ids), TicketTier.is_active == True, TicketTier.members_only == False)  # noqa: E712
        .group_by(TicketTier.event_id))).all()) if ids else {}
    return {e.id: (tiers[e.id] if e.id in tiers else (0.0 if e.is_free else e.price_min)) for e in events}


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


async def price_position(db: AsyncSession, event: Event, now: datetime) -> dict | None:
    comps = await _comparables(db, event, now, past_only=False, same_city=True)
    scope = "city"
    if len(comps) < MIN_COMPARABLES:
        scope, comps = "everywhere", await _comparables(db, event, now, past_only=False, same_city=False)
    prices = await _cheapest(db, comps)
    paid = [p for p in prices.values() if p]
    free_share = round(sum(1 for p in prices.values() if p == 0) / len(prices), 2) if prices else None
    yours = (await _cheapest(db, [event]))[event.id]
    if len(paid) < MIN_COMPARABLES:
        return {"scope": scope, "comparables": len(prices), "free_share": free_share, "yours": yours,
                "p25": None, "median": None, "p75": None, "position": None}
    p25, mid, p75 = _quantile(paid, 0.25), _quantile(paid, 0.5), _quantile(paid, 0.75)
    position = (None if not yours else "low" if yours < p25 else "high" if yours > p75 else "typical")
    return {"scope": scope, "comparables": len(prices), "free_share": free_share, "yours": yours,
            "p25": round(p25), "median": round(mid), "p75": round(p75), "position": position}


# ── Booking curve ───────────────────────────────────────────────────────────────


async def _commit_times(db: AsyncSession, ids: list[str]) -> dict[str, list[tuple[datetime, int]]]:
    out: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
    if not ids:
        return out
    for eid, at in (await db.execute(select(EventAttendee.event_id, EventAttendee.created_at).where(
            EventAttendee.event_id.in_(ids), EventAttendee.status == "going"))).all():
        out[eid].append((_utc(at), 1))
    for eid, at, n in (await db.execute(select(TicketOrder.event_id, TicketOrder.created_at, TicketOrder.quantity).where(
            TicketOrder.event_id.in_(ids), TicketOrder.status == "confirmed"))).all():
        out[eid].append((_utc(at), n or 1))
    return out


def _by_days_before(start: datetime, commits: list[tuple[datetime, int]], days: int) -> int:
    cutoff = start - timedelta(days=days)
    return sum(n for at, n in commits if at <= cutoff)


async def booking_curve(db: AsyncSession, event: Event, now: datetime) -> dict:
    start = _utc(event.start_date)
    mine = (await _commit_times(db, [event.id]))[event.id]
    past = await _comparables(db, event, now, past_only=True, same_city=False)
    commits = await _commit_times(db, [e.id for e in past])
    shares: dict[int, list[float]] = defaultdict(list)
    for e in past:
        total = sum(n for _, n in commits.get(e.id, []))
        if total < 5:
            continue  # too small to have a shape
        for d in CURVE_DAYS:
            shares[d].append(_by_days_before(_utc(e.start_date), commits[e.id], d) / total)
    enough = all(len(shares[d]) >= MIN_COMPARABLES for d in CURVE_DAYS)
    points = []
    for d in CURVE_DAYS:
        reached = start - timedelta(days=d) <= now
        points.append({"days_before": d,
                       "yours": _by_days_before(start, mine, d) if reached else None,
                       "typical_share": round(median(shares[d]), 3) if enough else None})
    so_far = sum(n for _, n in mine)
    days_left = (start - now).total_seconds() / 86400
    projected = None
    if enough and days_left > 0 and so_far:
        # The typical share sold by now: the closest curve point at or beyond today.
        at = min((d for d in CURVE_DAYS if d >= days_left), default=max(CURVE_DAYS))
        share = median(shares[at]) if at in shares else None
        if share and share >= 0.05:
            projected = round(so_far / share)
    return {"so_far": so_far, "comparables": len(shares[0]), "points": points, "projected_total": projected}


async def event_insights(db: AsyncSession, event: Event, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    category = (await db.execute(select(Category.name).where(Category.id == event.category_id))).scalar_one_or_none() \
        if event.category_id else None
    return {
        "category": category, "city": event.city,
        "best_times": await best_times(db, event, now),
        "price": await price_position(db, event, now),
        "booking_curve": await booking_curve(db, event, now),
        "unmet_searches": await unmet_searches(db, city=event.city, now=now),
    }
