"""The /for-you ranker (docs/recommendations-spec.md).

    candidates  ->  hydrate features  ->  score  ->  re-rank (diversity)  ->  log

1. Candidates: upcoming published events from several sources (soonest, highest demand, the
   person's categories, their city, organizers they follow or keep going back to, events
   people they follow are going to), minus what they've already committed to.
2. Hydrate: user_features and event_features rows (app/services/rec_features.py), plus
   what this session has been looking at in the last hour and what was shown but ignored.
3. Score: a weighted sum of named parts (WEIGHTS). The biggest part becomes the reason
   shown on the card ("Because you like Music", "3 people you follow are going").
4. Re-rank: no more than a couple of events from one category or organizer near the top.
5. Log: one `recs_served` row per response (ranker version, events in order), which is what
   the feed's click-through by position is measured from.
"""
import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity import Activity, EventFeatures, UserFeatures
from app.models.discovery import HiddenItem
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import TicketOrder
from app.models.social import Follow
from app.models.user import User
from app.services.activity import new_request_id, record
from app.services.rec_features import (
    LAGOS, PRIOR_CTR, PRIOR_SAVE_RATE, compute_user_features, haversine_km,
)

RANKER_VERSION = "v2.0"
MAX_CANDIDATES = 600

WEIGHTS = {
    "taste": 3.0, "picked": 1.0, "session": 1.5, "tags": 1.5,
    "place": 2.0, "city": 1.5, "online": 0.3,
    "timing": 1.0, "tonight": 0.8, "soon": 0.3, "day": 0.8,
    "price": 1.5, "format": 1.5,
    "friends": 2.0, "organizer": 1.5, "crew": 1.0,
    "quality": 1.0, "organizer_quality": 0.7, "popular": 1.2, "surge": 0.6,
    "scarce": 0.4, "sold_out": -3.0, "ignored": -0.3, "featured": 0.3,
}
# Without a history (signed out, new, or personalisation off) place, time and popularity
# carry the feed.
COLD_START_BOOST = {"popular": 2.0, "tonight": 1.5, "place": 1.3}

BUDGETS = {"free": 0, "budget": 5000, "mid": 20000, "any": None}
DIVERSITY_CATEGORY_PENALTY = 0.7
DIVERSITY_HOST_PENALTY = 0.9


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Viewer:
    user: User | None
    anonymous_id: str | None
    now: datetime
    lat: float | None = None
    lon: float | None = None
    city: str | None = None
    personal: bool = False
    feats: UserFeatures | None = None
    picked_categories: set[str] = field(default_factory=set)
    session_categories: set[str] = field(default_factory=set)
    social_ids: set[str] = field(default_factory=set)
    friends_going: Counter = field(default_factory=Counter)
    crew_going: Counter = field(default_factory=Counter)
    ignored: Counter = field(default_factory=Counter)

    @property
    def local_hour(self) -> int:
        return self.now.astimezone(LAGOS).hour


@dataclass
class Scored:
    event: Event
    score: float
    parts: dict
    distance_km: float | None = None
    reason: str | None = None


@dataclass
class RecResult:
    events: list[Event]
    reasons: dict[str, str]
    request_id: str


# ── Entry point ─────────────────────────────────────────────────────────────────


async def recommend(db: AsyncSession, *, user: User | None, anonymous_id: str | None = None,
                    lat: float | None = None, lon: float | None = None, city: str | None = None,
                    limit: int = 20, now: datetime | None = None,
                    log: bool = True, surface: str = "for_you", persist: bool = True) -> RecResult:
    """persist=False (offline evaluation) never commits: a missing user_features row is worked
    out inside the caller's transaction."""
    now = _utc(now) if now else datetime.now(timezone.utc)
    viewer = Viewer(user=user, anonymous_id=anonymous_id, now=now, lat=lat, lon=lon,
                    city=(city or (user.city if user else None) or
                          ((user.location or "").split(",")[0] if user else None) or None))
    viewer.personal = bool(user and user.personalized_recs)

    excluded = await _exclusions(db, user, now)
    if viewer.personal:
        await _load_profile(db, viewer, persist)
    candidates = await _candidates(db, viewer, excluded)
    hidden_hosts = await _hidden_organizers(db, user, now)
    if hidden_hosts:
        candidates = [e for e in candidates if e.host_id not in hidden_hosts]
    feats = await _event_features(db, [e.id for e in candidates])
    await _load_context(db, viewer, [e.id for e in candidates])
    scored = [score_event(viewer, e, feats.get(e.id)) for e in candidates]
    picked = rerank(scored, limit)
    result = RecResult(events=[s.event for s in picked],
                       reasons={s.event.id: s.reason for s in picked if s.reason},
                       request_id=new_request_id())
    if log:
        record(db, "recs_served", user_id=user.id if user else None, surface=surface,
               anonymous_id=anonymous_id, rec_request_id=result.request_id, props={
                   "ranker": RANKER_VERSION,
                   "event_ids": [e.id for e in result.events],
                   "personal": viewer.personal, "has_location": lat is not None,
               })
    return result


# ── 1. Candidates ───────────────────────────────────────────────────────────────


async def _exclusions(db: AsyncSession, user: User | None, now: datetime) -> set[str]:
    """Events they'd already committed to (going, saved, bought) or said "Not interested" to,
    by `now`."""
    if not user:
        return set()
    excluded = set((await db.execute(select(EventAttendee.event_id).where(
        EventAttendee.user_id == user.id, EventAttendee.status == "going",
        EventAttendee.created_at <= now))).scalars().all())
    excluded |= set((await db.execute(select(EventSave.event_id).where(
        EventSave.user_id == user.id, EventSave.created_at <= now))).scalars().all())
    excluded |= set((await db.execute(select(TicketOrder.event_id).where(
        TicketOrder.user_id == user.id, TicketOrder.status == "confirmed",
        TicketOrder.created_at <= now))).scalars().all())
    excluded |= set((await db.execute(select(HiddenItem.target_id).where(
        HiddenItem.user_id == user.id, HiddenItem.kind == "event",
        HiddenItem.created_at <= now))).scalars().all())
    return excluded


async def _hidden_organizers(db: AsyncSession, user: User | None, now: datetime) -> set[str]:
    """Organizers they chose "Hide this organizer" for by `now` (app/services/hidden.py)."""
    if not user:
        return set()
    return set((await db.execute(select(HiddenItem.target_id).where(
        HiddenItem.user_id == user.id, HiddenItem.kind == "organizer",
        HiddenItem.created_at <= now))).scalars().all())


def _base(now: datetime):
    return (select(Event).options(selectinload(Event.host).selectinload(User.organizer_profile),
                                  selectinload(Event.category))
            .where(Event.status == "published", Event.end_date > now,
                   Event.start_date > now - timedelta(hours=2), Event.created_at <= now))


async def _candidates(db: AsyncSession, v: Viewer, excluded: set[str]) -> list[Event]:
    now = v.now
    queries = [
        _base(now).order_by(Event.start_date.asc()).limit(200),
        _base(now).join(EventFeatures, EventFeatures.event_id == Event.id)
        .order_by(EventFeatures.demand_score.desc()).limit(150),
    ]
    categories = set(v.picked_categories)
    if v.feats and v.feats.category_affinity:
        categories |= {c for c, w in sorted(v.feats.category_affinity.items(), key=lambda x: -x[1])[:5] if w > 0}
    if categories:
        queries.append(_base(now).where(Event.category_id.in_(categories)).order_by(Event.start_date.asc()).limit(150))
    if v.city:
        queries.append(_base(now).where(Event.city.ilike(f"%{v.city.strip()}%"))
                       .order_by(Event.start_date.asc()).limit(150))
    if v.social_ids:
        queries.append(_base(now).where(Event.host_id.in_(v.social_ids)).limit(150))
    if v.user:
        following = select(Follow.following_id).where(Follow.follower_id == v.user.id)
        friends_events = select(EventAttendee.event_id).where(
            EventAttendee.user_id.in_(following), EventAttendee.status == "going",
            EventAttendee.created_at <= now)
        queries.append(_base(now).where(Event.id.in_(friends_events)).limit(150))

    seen: dict[str, Event] = {}
    for q in queries:
        for e in (await db.execute(q)).scalars().unique().all():
            # Never their own events.
            if e.id in excluded or (v.user and e.host_id == v.user.id) or e.id in seen:
                continue
            seen[e.id] = e
            if len(seen) >= MAX_CANDIDATES:
                return list(seen.values())
    return list(seen.values())


# ── 2. Hydrate ──────────────────────────────────────────────────────────────────


async def _load_profile(db: AsyncSession, v: Viewer, persist: bool = True) -> None:
    user = v.user
    feats = (await db.execute(select(UserFeatures).where(UserFeatures.user_id == user.id))).scalar_one_or_none()
    if feats is None:
        # New since last night's run: work theirs out now (a handful of queries, once).
        await compute_user_features(db, as_of=v.now, user_ids=[user.id], commit=persist)
        feats = (await db.execute(select(UserFeatures).where(UserFeatures.user_id == user.id))).scalar_one_or_none()
    v.feats = feats
    slugs = [p.strip() for p in (user.category_preferences or "").split(",") if p.strip()]
    if slugs:
        v.picked_categories = set((await db.execute(select(Category.id).where(Category.slug.in_(slugs)))).scalars().all())
    if feats and feats.social_affinity_ids:
        v.social_ids = set(feats.social_affinity_ids)
    if user.role == "organizer" and not slugs:
        # Organizers skip the taste questions: start from what they host.
        hosted = (await db.execute(select(Event.category_id).where(
            Event.host_id == user.id, Event.category_id.isnot(None)))).scalars().all()
        v.picked_categories = set(hosted)


async def _event_features(db: AsyncSession, ids: list[str]) -> dict[str, EventFeatures]:
    if not ids:
        return {}
    return {f.event_id: f for f in (await db.execute(
        select(EventFeatures).where(EventFeatures.event_id.in_(ids)))).scalars().all()}


async def _load_context(db: AsyncSession, v: Viewer, ids: list[str]) -> None:
    """Live signals: this session's interests, friends going, and what was shown but skipped."""
    who = []
    if v.user:
        who.append(Activity.user_id == v.user.id)
    if v.anonymous_id:
        who.append(Activity.anonymous_id == v.anonymous_id)
    if who and (v.personal or not v.user):
        hour_ago = v.now - timedelta(hours=1)
        looked = (await db.execute(
            select(Event.category_id).join(Activity, Activity.event_id == Event.id)
            .where(or_(*who), Activity.name.in_(("event_viewed", "event_clicked", "ticket_drawer_opened")),
                   Activity.occurred_at >= hour_ago, Activity.occurred_at <= v.now)
        )).scalars().all()
        v.session_categories = {c for c in looked if c}

        three_days = v.now - timedelta(days=3)
        rows = (await db.execute(
            select(Activity.event_id, Activity.name, func.count())
            .where(or_(*who), Activity.event_id.in_(ids),
                   Activity.name.in_(("feed_impression", "event_clicked")),
                   Activity.occurred_at >= three_days, Activity.occurred_at <= v.now)
            .group_by(Activity.event_id, Activity.name)
        )).all()
        clicked = {eid for eid, name, _ in rows if name == "event_clicked"}
        for eid, name, n in rows:
            if name == "feed_impression" and eid not in clicked:
                v.ignored[eid] = n

    if v.user and ids:
        following = select(Follow.following_id).where(Follow.follower_id == v.user.id)
        for eid, n in (await db.execute(
            select(EventAttendee.event_id, func.count()).where(
                EventAttendee.event_id.in_(ids), EventAttendee.status == "going",
                EventAttendee.user_id.in_(following), EventAttendee.created_at <= v.now)
            .group_by(EventAttendee.event_id))).all():
            v.friends_going[eid] = n
        crew = (v.feats.co_attendee_ids if v.feats and v.user.profiling_consent else None) or []
        if crew:
            for eid, n in (await db.execute(
                select(EventAttendee.event_id, func.count()).where(
                    EventAttendee.event_id.in_(ids), EventAttendee.status == "going",
                    EventAttendee.user_id.in_(crew))
                .group_by(EventAttendee.event_id))).all():
                v.crew_going[eid] = n


# ── 3. Score ────────────────────────────────────────────────────────────────────


def score_event(v: Viewer, e: Event, f: EventFeatures | None) -> Scored:
    feats = v.feats if v.personal else None
    cold = not feats or not (feats.category_affinity or v.picked_categories)
    w = dict(WEIGHTS)
    if cold:
        for k, mult in COLD_START_BOOST.items():
            w[k] *= mult
    parts: dict[str, float] = {}
    user = v.user if v.personal else None

    # Taste
    if e.category_id:
        if feats and feats.category_affinity:
            aff = feats.category_affinity.get(e.category_id, 0.0)
            if aff:
                parts["taste"] = w["taste"] * aff
        if e.category_id in v.picked_categories:
            parts["picked"] = w["picked"]
        if e.category_id in v.session_categories:
            parts["session"] = w["session"]
    if feats and feats.tag_affinity and e.tags:
        overlap = sum(feats.tag_affinity.get(t.strip().lower(), 0.0) for t in e.tags.split(","))
        if overlap:
            parts["tags"] = w["tags"] * max(min(overlap, 1.0), -1.0)

    # Place
    distance = None
    if e.event_type == "virtual":
        parts["online"] = w["online"]
    else:
        origin = (v.lat, v.lon) if v.lat is not None and v.lon is not None else \
            ((feats.home_lat, feats.home_lon) if feats and feats.home_lat is not None else None)
        if origin and e.latitude is not None and e.longitude is not None:
            distance = haversine_km(origin[0], origin[1], e.latitude, e.longitude)
            radius = (feats.preferred_radius_km if feats and feats.preferred_radius_km else 15.0)
            parts["place"] = w["place"] * math.exp(-distance / radius)
        elif v.city:
            ec, uc = (e.city or "").lower(), v.city.strip().lower()
            if uc and (uc in ec or ec in uc):
                parts["city"] = w["city"]

    # Time
    hours = (_utc(e.start_date) - v.now).total_seconds() / 3600
    if feats and feats.avg_lead_time_hours is not None and hours > 0:
        gap = abs(math.log((hours + 1) / (feats.avg_lead_time_hours + 1)))
        parts["timing"] = w["timing"] * (1 - min(gap / 3, 1.0))
    if -2 <= hours <= 8 and v.local_hour >= 15:
        spont = feats.spontaneity_ratio if feats and feats.spontaneity_ratio is not None else 0.5
        parts["tonight"] = w["tonight"] * spont * 2
    elif 0 < hours <= 7 * 24:
        parts["soon"] = w["soon"]
    when = user.goes_out_when if user else None
    if when and when != "any":
        weekend = _utc(e.start_date).astimezone(LAGOS).weekday() >= 4
        if (when == "weekends") == weekend:
            parts["day"] = w["day"]

    # Money
    sensitivity = user.price_sensitivity if user else None
    if e.is_free:
        if feats and feats.free_event_share is not None:
            parts["price"] = w["price"] * 0.8 * feats.free_event_share
        else:
            parts["price"] = w["price"] * (1.0 if sensitivity == "free" else 0.3)
    else:
        budget = feats.median_ticket_spend if feats and feats.median_ticket_spend else BUDGETS.get(sensitivity or "")
        if sensitivity == "any":
            parts["price"] = w["price"] * 0.6
        elif budget == 0:
            parts["price"] = -w["price"] * 0.5
        elif budget and e.price_min is not None:
            ratio = e.price_min / budget
            fit = 1.0 if ratio <= 1.2 else max(0.0, 1 - (ratio - 1.2) / 1.5)
            parts["price"] = w["price"] * fit - (0.5 if ratio > 3 else 0.0)

    fmt = user.event_format_pref if user else None
    if fmt and fmt != "both":
        if e.event_type == fmt:
            parts["format"] = w["format"]
        elif e.event_type != "hybrid":
            parts["format"] = -0.5

    # People
    if v.friends_going.get(e.id):
        parts["friends"] = w["friends"] * min(v.friends_going[e.id], 3) / 3
    if e.host_id in v.social_ids:
        parts["organizer"] = w["organizer"]
    if v.crew_going.get(e.id):
        parts["crew"] = w["crew"]

    # The event itself
    if f:
        q = 0.5 * min(f.ctr_7d / PRIOR_CTR, 3) / 3 + 0.5 * min(f.save_rate_7d / PRIOR_SAVE_RATE, 3) / 3
        parts["quality"] = w["quality"] * q
        parts["organizer_quality"] = w["organizer_quality"] * (f.organizer_quality - 0.5) * 2
        parts["popular"] = w["popular"] * f.demand_score
        if f.interest_surge >= 2 and f.velocity_24h >= 3:
            parts["surge"] = w["surge"]
        if f.remaining_tickets == 0 and not e.waitlist_enabled:
            parts["sold_out"] = w["sold_out"]
        elif f.sell_through_pct is not None and f.sell_through_pct >= 0.8:
            parts["scarce"] = w["scarce"]
    else:
        parts["popular"] = w["popular"] * min(math.log1p(e.attendees_count + e.saves_count) / math.log1p(500), 1.0)
    if v.ignored.get(e.id, 0) >= 3:
        parts["ignored"] = max(w["ignored"] * (v.ignored[e.id] - 2), -1.5)
    if e.is_featured or e.is_trending:
        parts["featured"] = w["featured"]

    key = f"{v.user.id if v.user else v.anonymous_id}:{e.id}:{v.now.date()}"
    jitter = int(hashlib.md5(key.encode()).hexdigest()[:4], 16) / 65535 * 0.1
    s = Scored(event=e, score=sum(parts.values()) + jitter, parts=parts, distance_km=distance)
    s.reason = _reason(v, s)
    return s


def _reason(v: Viewer, s: Scored) -> str | None:
    e, parts = s.event, s.parts
    friends = v.friends_going.get(e.id, 0)
    candidates = {
        "friends": f"{friends} {'person' if friends == 1 else 'people'} you follow {'is' if friends == 1 else 'are'} going",
        "organizer": f"From {e.host.display_name or e.host.full_name or e.host.username}" if e.host else None,
        "crew": "Your crew is going",
        "taste": f"Because you like {e.category.name}" if e.category else None,
        "picked": f"Because you like {e.category.name}" if e.category else None,
        "session": "Like what you've been looking at",
        "tags": "Matches what you're into",
        "tonight": "Happening tonight",
        "surge": "Selling fast",
        "scarce": "Almost sold out",
        "place": (f"{s.distance_km:.0f} km away" if s.distance_km is not None and s.distance_km >= 1
                  else "Right around you"),
        "city": f"In {e.city}",
        "popular": "Popular right now",
    }
    best = sorted(((k, val) for k, val in parts.items() if val > 0.4 and candidates.get(k)), key=lambda x: -x[1])
    return candidates[best[0][0]] if best else None


# ── 4. Re-rank ──────────────────────────────────────────────────────────────────


def rerank(scored: list[Scored], limit: int) -> list[Scored]:
    """Greedy: each slot takes the best remaining event after a penalty for every event from
    the same category or organizer already above it."""
    pool = sorted(scored, key=lambda s: -s.score)
    picked: list[Scored] = []
    cats, hosts = Counter(), Counter()
    while pool and len(picked) < limit:
        choice = max(pool, key=lambda s: s.score
                     - DIVERSITY_CATEGORY_PENALTY * cats[s.event.category_id or "-"]
                     - DIVERSITY_HOST_PENALTY * hosts[s.event.host_id])
        pool.remove(choice)
        picked.append(choice)
        cats[choice.event.category_id or "-"] += 1
        hosts[choice.event.host_id] += 1
    return picked
