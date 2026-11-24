"""Per-event and per-user numbers the recommender reads (docs/recommendations-spec.md).

Run by the worker: event features every 15 minutes, user features nightly (and on demand for
a user who has none yet). Everything takes an `as_of` time and only looks at data from before
it, so the offline evaluation (app/services/rec_eval.py) can rebuild features as they were.

Plain Python over a few bulk queries: fine for tens of thousands of users. Past that, move
the aggregations into SQL (or dbt) behind the same functions.
"""
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, distinct, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, EventFeatures, UserFeatures
from app.models.event import Event, EventAttendee, EventSave
from app.models.organizer import EventReview, OrganizerProfile, TicketOrder, TicketTier
from app.models.social import Follow
from app.models.user import User

LAGOS = timezone(timedelta(hours=1))   # Nigeria has no daylight saving

# Smoothing priors: a new event starts at roughly the platform average instead of 0% or 100%.
PRIOR_N = 20
PRIOR_CTR, PRIOR_SAVE_RATE, PRIOR_ORDER_RATE = 0.05, 0.08, 0.02

# How much each action says about taste, before decay (half-life HALF_LIFE_DAYS).
ACTION_WEIGHTS = {
    "event_clicked": 0.5, "event_viewed": 1.0, "dwell_long": 1.0,  # dwell adds to the view
    "event_shared": 3.0, "ticket_drawer_opened": 2.0,
    "save": 3.0, "interested": 2.0, "going": 4.0, "order": 5.0, "checked_in": 2.0,
}
HALF_LIFE_DAYS = 30
LONG_DWELL_SECONDS = 15


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now(as_of: datetime | None) -> datetime:
    return _utc(as_of) or datetime.now(timezone.utc)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def wilson_lower_bound(successes: float, n: float, z: float = 1.64) -> float:
    """Lower edge of the 90% confidence interval for a rate, so a little evidence counts for
    less: 3 saves out of 3 views (0.53) ranks below 80 out of 100 (0.73)."""
    if n <= 0:
        return 0.0
    p = min(successes / n, 1.0)
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def _tags(raw: str | None) -> list[str]:
    return [t.strip().lower() for t in (raw or "").split(",") if t.strip()]


# ── Event features ──────────────────────────────────────────────────────────────


async def compute_event_features(db: AsyncSession, as_of: datetime | None = None, commit: bool = True) -> dict:
    """For every event that hasn't ended (as of `as_of`). commit=False leaves the rows in the
    caller's transaction (the offline evaluation rolls them back)."""
    now = _now(as_of)
    events = (await db.execute(select(Event).where(
        Event.status == "published", Event.end_date > now, Event.created_at <= now,
    ))).scalars().all()
    if not events:
        return {"events": 0}
    ids = [e.id for e in events]
    week_ago, day_ago, hour_ago = now - timedelta(days=7), now - timedelta(days=1), now - timedelta(hours=1)

    # Distinct people (signed in or not) per event and action over 7 days, leaving out the
    # host's own activity, so neither refreshing nor an organizer clicking their own event
    # moves the numbers.
    viewer = func.coalesce(Activity.user_id, Activity.anonymous_id)
    rows = (await db.execute(
        select(Activity.event_id, Activity.name, func.count(distinct(viewer)))
        .join(Event, Event.id == Activity.event_id)
        .where(Activity.event_id.in_(ids),
               Activity.name.in_(("feed_impression", "event_clicked", "event_viewed")),
               Activity.occurred_at >= week_ago, Activity.occurred_at < now,
               or_(Activity.user_id.is_(None), Activity.user_id != Event.host_id))
        .group_by(Activity.event_id, Activity.name)
    )).all()
    seen: dict[str, Counter] = defaultdict(Counter)
    for eid, name, n in rows:
        seen[eid][name] = n

    # Commitments (saves, going, orders) from the tables themselves, the source of truth.
    commits: dict[str, list[datetime]] = defaultdict(list)
    saves_7d: Counter = Counter()
    orders_7d: Counter = Counter()
    host_of = {e.id: e.host_id for e in events}
    since = now - timedelta(days=8)
    for eid, uid, at in (await db.execute(select(EventSave.event_id, EventSave.user_id, EventSave.created_at)
                                          .where(EventSave.event_id.in_(ids), EventSave.created_at >= since,
                                                 EventSave.created_at < now))).all():
        if uid == host_of[eid]:
            continue
        commits[eid].append(_utc(at))
        if _utc(at) >= week_ago:
            saves_7d[eid] += 1
    for eid, uid, at in (await db.execute(select(EventAttendee.event_id, EventAttendee.user_id,
                                                 EventAttendee.created_at)
                                          .where(EventAttendee.event_id.in_(ids), EventAttendee.status == "going",
                                                 EventAttendee.created_at >= since,
                                                 EventAttendee.created_at < now))).all():
        if uid != host_of[eid]:
            commits[eid].append(_utc(at))
    for eid, at in (await db.execute(select(TicketOrder.event_id, TicketOrder.created_at)
                                     .where(TicketOrder.event_id.in_(ids), TicketOrder.status == "confirmed",
                                            TicketOrder.created_at >= since, TicketOrder.created_at < now))).all():
        commits[eid].append(_utc(at))
        if _utc(at) >= week_ago:
            orders_7d[eid] += 1

    # Inventory.
    tiers: dict[str, list[TicketTier]] = defaultdict(list)
    for t in (await db.execute(select(TicketTier).where(TicketTier.event_id.in_(ids),
                                                         TicketTier.is_active == True))).scalars().all():  # noqa: E712
        tiers[t.event_id].append(t)

    organizer = await _organizer_scores(db, {e.host_id for e in events}, now)

    out: list[EventFeatures] = []
    for e in events:
        s = seen[e.id]
        impressions, clicks, views = s["feed_impression"], s["event_clicked"], s["event_viewed"]
        times = commits[e.id]
        v1 = sum(1 for t in times if t >= hour_ago)
        v24 = sum(1 for t in times if t >= day_ago)
        prior_daily = sum(1 for t in times if t < day_ago) / 7
        surge = v24 / max(prior_daily, 0.5)

        sell_through = remaining = None
        ts = tiers.get(e.id, [])
        if ts:
            if all(t.quantity is not None for t in ts):
                total = sum(t.quantity for t in ts)
                sold = sum(t.quantity_sold for t in ts)
                remaining = max(total - sold, 0)
                sell_through = sold / total if total else None
        elif e.capacity:
            sell_through = min(e.attendees_count / e.capacity, 1.0)
            remaining = max(e.capacity - e.attendees_count, 0)

        engaged = saves_7d[e.id] + orders_7d[e.id] + sum(1 for t in times if t >= week_ago)
        rate_part = wilson_lower_bound(engaged, max(views, engaged))
        velocity_part = min(math.log1p(v24) / math.log1p(50), 1.0)
        # Before anyone has tracked views (a brand-new install, old data), fall back on counts.
        lifetime = min(math.log1p(e.attendees_count + e.interested_count + e.saves_count) / math.log1p(500), 1.0)
        demand = max(0.6 * rate_part + 0.4 * velocity_part, 0.5 * lifetime)

        quality, reliability = organizer.get(e.host_id, (0.5, None))
        out.append(EventFeatures(
            event_id=e.id, computed_at=now,
            impressions_7d=impressions, clicks_7d=clicks, views_7d=views,
            saves_7d=saves_7d[e.id], orders_7d=orders_7d[e.id],
            ctr_7d=(clicks + PRIOR_N * PRIOR_CTR) / (impressions + PRIOR_N),
            save_rate_7d=(saves_7d[e.id] + PRIOR_N * PRIOR_SAVE_RATE) / (views + PRIOR_N),
            view_to_order_rate_7d=(orders_7d[e.id] + PRIOR_N * PRIOR_ORDER_RATE) / (views + PRIOR_N),
            velocity_1h=v1, velocity_24h=v24, interest_surge=round(surge, 3),
            sell_through_pct=sell_through, remaining_tickets=remaining,
            organizer_quality=quality, attendance_reliability=reliability,
            demand_score=round(demand, 4),
        ))

    await db.execute(delete(EventFeatures).where(EventFeatures.event_id.in_(ids)))
    db.add_all(out)
    # Rows for events that have ended aren't needed any more.
    await db.execute(delete(EventFeatures).where(EventFeatures.event_id.notin_(ids)))
    await (db.commit() if commit else db.flush())
    return {"events": len(out)}


async def _organizer_scores(db: AsyncSession, host_ids: set[str], now: datetime) -> dict:
    """host_id -> (quality 0..1, attendance reliability 0..1 or None)."""
    if not host_ids:
        return {}
    ratings = defaultdict(list)
    for host, rating in (await db.execute(
        select(Event.host_id, EventReview.rating).join(Event, Event.id == EventReview.event_id)
        .where(Event.host_id.in_(host_ids), EventReview.created_at < now)
    )).all():
        ratings[host].append(rating)
    sold, admitted = Counter(), Counter()
    for host, qty, adm, checked in (await db.execute(
        select(Event.host_id, TicketOrder.quantity, TicketOrder.admitted_count, TicketOrder.checked_in_at)
        .join(Event, Event.id == TicketOrder.event_id)
        .where(Event.host_id.in_(host_ids), Event.end_date < now, TicketOrder.status == "confirmed")
    )).all():
        sold[host] += qty
        admitted[host] += adm or (qty if checked else 0)
    verified = set((await db.execute(select(OrganizerProfile.user_id).where(
        OrganizerProfile.user_id.in_(host_ids), OrganizerProfile.is_verified_organizer == True,  # noqa: E712
    ))).scalars().all())

    out = {}
    for host in host_ids:
        rs = ratings.get(host, [])
        bayes = (sum(rs) + 3.5 * 5) / (len(rs) + 5)          # 5 imaginary 3.5-star reviews
        quality = (bayes - 1) / 4 + (0.1 if host in verified else 0.0)
        reliability = admitted[host] / sold[host] if sold[host] >= 5 else None
        if reliability is not None and reliability < 0.5:
            quality -= 0.15                                   # lots of no-shows: oversold or misleading
        out[host] = (round(min(max(quality, 0.0), 1.0), 4),
                     round(reliability, 4) if reliability is not None else None)
    return out


# ── User features ───────────────────────────────────────────────────────────────


async def compute_user_features(db: AsyncSession, as_of: datetime | None = None,
                                user_ids: list[str] | None = None, commit: bool = True) -> dict:
    """For `user_ids`, or everyone active in the last 180 days."""
    now = _now(as_of)
    lookback = now - timedelta(days=180)
    act_since = now - timedelta(days=90)

    q = select(User).where(User.is_deleted == False, User.created_at <= now)  # noqa: E712
    if user_ids is not None:
        if not user_ids:
            return {"users": 0}
        q = q.where(User.id.in_(user_ids))
    users = {u.id: u for u in (await db.execute(q)).scalars().all()}
    if not users:
        return {"users": 0}
    uid_filter = list(users) if user_ids is not None else None

    def scoped(stmt, col):
        return stmt.where(col.in_(uid_filter)) if uid_filter is not None else stmt

    saves = (await db.execute(scoped(select(EventSave.user_id, EventSave.event_id, EventSave.created_at)
                                     .where(EventSave.created_at < now, EventSave.created_at >= lookback),
                                     EventSave.user_id))).all()
    rsvps = (await db.execute(scoped(select(EventAttendee.user_id, EventAttendee.event_id, EventAttendee.status,
                                            EventAttendee.created_at)
                                     .where(EventAttendee.created_at < now, EventAttendee.created_at >= lookback),
                                     EventAttendee.user_id))).all()
    orders = (await db.execute(scoped(select(TicketOrder.user_id, TicketOrder.event_id, TicketOrder.unit_price,
                                             TicketOrder.created_at, TicketOrder.checked_in_at)
                                      .where(TicketOrder.status == "confirmed", TicketOrder.created_at < now,
                                             TicketOrder.created_at >= lookback),
                                      TicketOrder.user_id))).all()
    acts = (await db.execute(scoped(select(Activity.user_id, Activity.name, Activity.event_id,
                                           Activity.occurred_at, Activity.props)
                                    .where(Activity.user_id.isnot(None), Activity.occurred_at < now,
                                           Activity.occurred_at >= act_since,
                                           Activity.name.in_(("event_viewed", "event_dwell_ended", "event_clicked",
                                                              "event_shared", "ticket_drawer_opened",
                                                              "checkout_abandoned", "session_started"))),
                                    Activity.user_id))).all()
    follows = (await db.execute(scoped(select(Follow.follower_id, Follow.following_id), Follow.follower_id))).all()

    event_ids = {r[1] for r in saves} | {r[1] for r in rsvps} | {r[1] for r in orders} | \
                {r[2] for r in acts if r[2]}
    ev = {}
    if event_ids:
        for e in (await db.execute(select(Event.id, Event.category_id, Event.tags, Event.start_date, Event.is_free,
                                          Event.price_min, Event.latitude, Event.longitude, Event.host_id)
                                   .where(Event.id.in_(event_ids)))).all():
            ev[e.id] = e

    per: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for uid, eid, at in saves:
        per[uid]["save"].append((eid, _utc(at)))
    for uid, eid, status, at in rsvps:
        per[uid][status].append((eid, _utc(at)))
    for uid, eid, price, at, checked in orders:
        per[uid]["order"].append((eid, _utc(at), price))
        if checked:
            per[uid]["checked_in"].append((eid, _utc(checked)))
    for uid, name, eid, at, props in acts:
        per[uid][name].append((eid, _utc(at), props or {}))
    following = defaultdict(set)
    for a, b in follows:
        following[a].add(b)

    from app.models.event import Category
    slugs = {c.id: c.slug for c in (await db.execute(select(Category))).scalars().all()}
    consenting = {u.id for u in users.values() if u.profiling_consent}
    co_attendees = await _co_attendees(db, consenting, now) if consenting else {}
    tastemakers = await _tastemaker_scores(db, consenting, now) if consenting else {}

    out = []
    for uid, user in users.items():
        out.append(_user_row(user, per.get(uid, {}), ev, following.get(uid, set()), now,
                             co_attendees.get(uid), tastemakers.get(uid), slugs))

    await db.execute(delete(UserFeatures).where(UserFeatures.user_id.in_(list(users))))
    db.add_all(out)
    await (db.commit() if commit else db.flush())
    return {"users": len(out)}


def _user_row(user: User, acts: dict, ev: dict, following: set, now: datetime,
              co_attendees: list | None, tastemaker: float | None, slugs: dict) -> UserFeatures:
    def decay(at: datetime) -> float:
        return 0.5 ** (max((now - at).total_seconds(), 0) / 86400 / HALF_LIFE_DAYS)

    cat, tag = Counter(), Counter()

    def credit(eid: str | None, weight: float, at: datetime):
        e = ev.get(eid) if eid else None
        if not e:
            return
        w = weight * decay(at)
        if e.category_id:
            cat[e.category_id] += w
        for t in _tags(e.tags):
            tag[t] += w * 0.6

    for kind in ("save", "interested", "going", "checked_in"):
        for eid, at in acts.get(kind, []):
            credit(eid, ACTION_WEIGHTS[kind], at)
    for eid, at, _price in acts.get("order", []):
        credit(eid, ACTION_WEIGHTS["order"], at)
    for name in ("event_clicked", "event_viewed", "event_shared", "ticket_drawer_opened"):
        for eid, at, _p in acts.get(name, []):
            credit(eid, ACTION_WEIGHTS[name], at)
    for eid, at, props in acts.get("event_dwell_ended", []):
        if (props.get("dwell_seconds") or 0) >= LONG_DWELL_SECONDS:
            credit(eid, ACTION_WEIGHTS["dwell_long"], at)

    def normalise(c: Counter, top: int | None = None) -> dict | None:
        if not c:
            return None
        peak = max((v for v in c.values() if v > 0), default=0) or 1.0
        items = c.most_common(top) if top else c.items()
        return {k: round(max(min(v / peak, 1.0), -1.0), 4) for k, v in items if abs(v) > 1e-6}

    # Commitments: when they decide, what they pay, where they go.
    committed = [(eid, at) for eid, at in acts.get("going", [])] + \
                [(eid, at) for eid, at, _ in acts.get("order", [])]
    leads = []
    for eid, at in committed:
        e = ev.get(eid)
        if e and e.start_date:
            leads.append(max((_utc(e.start_date) - at).total_seconds() / 3600, 0))
    engaged_ids = {eid for eid, _ in committed} | {eid for eid, _ in acts.get("save", [])}
    engaged = [ev[e] for e in engaged_ids if e in ev]
    weekend = [e for e in engaged if e.start_date and _utc(e.start_date).astimezone(LAGOS).weekday() >= 4]

    paid = [(eid, price) for eid, _at, price in acts.get("order", []) if price and price > 0]
    vip = [1 for eid, price in paid if ev.get(eid) and ev[eid].price_min and price > ev[eid].price_min * 1.01]

    places = [(ev[e].latitude, ev[e].longitude) for e in {eid for eid, _ in committed}
              | {eid for eid, _ in acts.get("checked_in", [])} if e in ev and ev[e].latitude is not None]
    if not places:
        places = [(e.latitude, e.longitude) for e in engaged if e.latitude is not None]
    home_lat = home_lon = radius = None
    if places:
        home_lat = sum(p[0] for p in places) / len(places)
        home_lon = sum(p[1] for p in places) / len(places)
        dists = sorted(haversine_km(home_lat, home_lon, la, lo) for la, lo in places)
        radius = min(max(dists[int(0.8 * (len(dists) - 1))] * 1.5, 5.0), 60.0)

    # Organizers they keep going back to, plus people they follow.
    host_counts = Counter(ev[e].host_id for e in engaged_ids if e in ev)
    social = list(following)[:40] + [h for h, n in host_counts.most_common(10) if n >= 2 and h not in following]

    month_ago = now - timedelta(days=30)
    views_30d = sum(1 for _e, at, _p in acts.get("event_viewed", []) if at >= month_ago)
    clicks_30d = sum(1 for _e, at, _p in acts.get("event_clicked", []) if at >= month_ago)
    saves_30d = sum(1 for _e, at in acts.get("save", []) if at >= month_ago)
    drawers = acts.get("ticket_drawer_opened", [])
    drawers_30d = sum(1 for _e, at, _p in drawers if at >= month_ago)
    orders_30d = sum(1 for _e, at, _p in acts.get("order", []) if at >= month_ago)
    shares = len(acts.get("event_shared", []))
    views = len(acts.get("event_viewed", []))

    times = [at for k, v in acts.items() for item in v for at in [item[1]] if at]
    last_active = max(times) if times else None
    created = _utc(user.created_at)
    if created and (now - created).days < 14 and len(times) < 10:
        lifecycle = "new"
    elif last_active and (now - last_active).days <= 7:
        lifecycle = "active"
    elif last_active and (now - last_active).days <= 30:
        lifecycle = "cooling"
    else:
        lifecycle = "dormant"
    intent = saves_30d * 2 + drawers_30d * 3 + views_30d * 0.5 + clicks_30d * 0.3
    propensity = (1 - math.exp(-intent / 10)) * (0.6 if orders_30d else 1.0)

    row = UserFeatures(
        user_id=user.id, computed_at=now,
        category_affinity=normalise(cat), tag_affinity=normalise(tag, 30),
        avg_lead_time_hours=round(statistics.fmean(leads), 1) if leads else None,
        spontaneity_ratio=round(sum(1 for h in leads if h < 48) / len(leads), 3) if leads else None,
        weekend_share=round(len(weekend) / len(engaged), 3) if engaged else None,
        median_ticket_spend=statistics.median(p for _e, p in paid) if paid else None,
        max_ticket_spend=max(p for _e, p in paid) if paid else None,
        free_event_share=round(sum(1 for e in engaged if e.is_free) / len(engaged), 3) if engaged else None,
        vip_share=round(len(vip) / len(paid), 3) if paid else None,
        checkout_abandon_rate=round(len(acts.get("checkout_abandoned", [])) / len(drawers), 3) if drawers else None,
        home_lat=home_lat, home_lon=home_lon, preferred_radius_km=radius,
        social_affinity_ids=social or None,
        share_rate=round(shares / views, 3) if views else None,
        last_active_at=last_active, lifecycle=lifecycle,
        conversion_propensity=round(propensity, 3),
        views_30d=views_30d, saves_30d=saves_30d, orders_total=len(acts.get("order", [])),
    )
    if user.profiling_consent:
        hours = Counter(at.astimezone(LAGOS).hour for _e, at, _p in acts.get("session_started", []))
        row.peak_hours = [h for h, _ in hours.most_common(3)] or None
        row.co_attendee_ids = co_attendees or None
        row.tastemaker_score = tastemaker
        row.segments = _segments(user, row, cat, slugs, now) or None
    return row


async def _co_attendees(db: AsyncSession, consenting: set[str], now: datetime) -> dict[str, list[str]]:
    """Consenting users who went to at least 2 of the same events as each other (both must
    have opted in). Events with very large crowds say nothing about who goes with whom."""
    rows = (await db.execute(select(EventAttendee.event_id, EventAttendee.user_id).where(
        EventAttendee.status == "going", EventAttendee.user_id.in_(consenting),
        EventAttendee.created_at < now, EventAttendee.created_at >= now - timedelta(days=365),
    ))).all()
    by_event = defaultdict(list)
    for eid, uid in rows:
        by_event[eid].append(uid)
    pairs: Counter = Counter()
    for members in by_event.values():
        if 2 <= len(members) <= 300:
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    pairs[(a, b)] += 1
    out = defaultdict(list)
    for (a, b), n in pairs.most_common():
        if n < 2:
            break
        if len(out[a]) < 20:
            out[a].append(b)
        if len(out[b]) < 20:
            out[b].append(a)
    return out


async def _tastemaker_scores(db: AsyncSession, consenting: set[str], now: datetime) -> dict[str, float]:
    """How often a person's followers commit to an event within 7 days after they did, over the
    last 90 days, on a 0..1 log scale."""
    since = now - timedelta(days=90)
    going = (await db.execute(select(EventAttendee.user_id, EventAttendee.event_id, EventAttendee.created_at).where(
        EventAttendee.status == "going", EventAttendee.created_at >= since, EventAttendee.created_at < now,
    ))).all()
    first: dict[tuple[str, str], datetime] = {}
    for uid, eid, at in going:
        first[(uid, eid)] = _utc(at)
    followers = defaultdict(set)
    for follower, followed in (await db.execute(select(Follow.follower_id, Follow.following_id).where(
            Follow.following_id.in_(consenting)))).all():
        followers[followed].add(follower)
    by_event = defaultdict(list)
    by_user = defaultdict(list)
    for (uid, eid), at in first.items():
        by_event[eid].append((uid, at))
        by_user[uid].append((eid, at))
    scores = {}
    for uid in consenting:
        n = sum(1 for eid, at in by_user[uid] for other, other_at in by_event[eid]
                if other in followers[uid] and at < other_at <= at + timedelta(days=7))
        scores[uid] = round(min(math.log1p(n) / math.log1p(50), 1.0), 4)
    return scores


SEGMENT_CATEGORY_SLUGS = {
    "nightlife": "nightlife_regular", "music": "live_music_fan", "tech": "tech_professional",
    "food": "foodie", "arts": "arts_and_culture", "comedy": "comedy_fan",
    "wellness": "wellness", "sports": "sports_fan",
}


def _segments(user: User, row: UserFeatures, cat: Counter, slugs: dict, now: datetime) -> list[str]:
    """Audience labels for sponsor and partner targeting (only with profiling consent)."""
    out = []
    if row.weekend_share is not None and row.weekend_share >= 0.7:
        out.append("weekend_warrior")
    if row.spontaneity_ratio is not None:
        out.append("spontaneous" if row.spontaneity_ratio >= 0.5 else "planner")
    if row.max_ticket_spend and row.max_ticket_spend >= 30000:
        out.append("big_spender")
    if row.free_event_share is not None and row.free_event_share >= 0.7:
        out.append("free_event_hunter")
    if row.vip_share and row.vip_share >= 0.5:
        out.append("vip_buyer")
    if row.tastemaker_score and row.tastemaker_score >= 0.3:
        out.append("tastemaker")
    if row.lifecycle in ("cooling", "dormant"):
        out.append(f"lapsing_{row.lifecycle}")
    if user.birth_year:
        age = now.year - user.birth_year
        band = "18-24" if age < 25 else "25-34" if age < 35 else "35-44" if age < 45 else "45+"
        out.append(f"age_{band}")
    if user.gender and user.gender != "prefer_not_to_say":
        out.append(f"gender_{user.gender}")
    # Category labels only for real favourites: at least half as strong as their top one.
    peak = max(cat.values(), default=0)
    for cid, w in cat.most_common(3):
        label = SEGMENT_CATEGORY_SLUGS.get(slugs.get(cid, ""))
        if peak > 0 and w >= 0.5 * peak and label:
            out.append(label)
    return out


async def clear_profiling(db: AsyncSession, user_id: str) -> None:
    """Profiling consent withdrawn: drop what only consent allowed, now rather than tonight."""
    await db.execute(update(UserFeatures).where(UserFeatures.user_id == user_id).values(
        peak_hours=None, co_attendee_ids=None, tastemaker_score=None, segments=None))
    await db.execute(update(Activity).where(Activity.user_id == user_id, Activity.geo_lat.isnot(None))
                     .values(geo_lat=None, geo_lon=None))


# ── Worker entry points ─────────────────────────────────────────────────────────


async def run_event_features(db: AsyncSession) -> dict:
    return await compute_event_features(db)


async def run_user_features(db: AsyncSession) -> dict:
    return await compute_user_features(db)
