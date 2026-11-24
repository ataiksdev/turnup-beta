"""Admin data-health page: is tracking arriving, are features fresh, what isn't found, and
how the feed performs by position (docs/recommendations-spec.md)."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, EventFeatures, UserFeatures
from app.services.insights import unmet_searches

DELAY_SAMPLE = 5000
MAX_POSITION = 20


def _utc(dt: datetime | None) -> datetime | None:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(int(len(xs) * q), len(xs) - 1)], 1)


async def data_health(db: AsyncSession, days: int = 14, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # Events per day, by source. Grouped in Python so it works the same on SQLite and Postgres.
    per_day: dict[str, Counter] = defaultdict(Counter)
    for at, source, n in (await db.execute(
            select(func.date(Activity.occurred_at), Activity.source, func.count())
            .where(Activity.occurred_at >= since, Activity.occurred_at <= now)
            .group_by(func.date(Activity.occurred_at), Activity.source))).all():
        per_day[str(at)][source] = n
    daily = []
    for i in range(days, -1, -1):
        d = (now - timedelta(days=i)).date().isoformat()
        daily.append({"date": d, "client": per_day[d]["client"], "server": per_day[d]["server"]})

    day_ago = now - timedelta(days=1)
    top_names = [{"name": n, "count": c} for n, c in (await db.execute(
        select(Activity.name, func.count()).where(Activity.occurred_at >= day_ago)
        .group_by(Activity.name).order_by(func.count().desc()).limit(15))).all()]

    # How late client events arrive (queued offline, batched on mobile data).
    pairs = (await db.execute(select(Activity.occurred_at, Activity.received_at).where(
        Activity.source == "client", Activity.received_at >= day_ago)
        .order_by(Activity.received_at.desc()).limit(DELAY_SAMPLE))).all()
    delays = [max((_utc(r) - _utc(o)).total_seconds(), 0.0) for o, r in pairs]
    ingestion = {"sample": len(delays), "p50_seconds": _pct(delays, 0.5), "p95_seconds": _pct(delays, 0.95),
                 "max_seconds": round(max(delays), 1) if delays else None,
                 "last_received_at": _utc((await db.execute(select(func.max(Activity.received_at)))).scalar())}

    features = {
        "event_features": {"rows": (await db.execute(select(func.count()).select_from(EventFeatures))).scalar_one(),
                           "computed_at": _utc((await db.execute(select(func.max(EventFeatures.computed_at)))).scalar())},
        "user_features": {"rows": (await db.execute(select(func.count()).select_from(UserFeatures))).scalar_one(),
                          "computed_at": _utc((await db.execute(select(func.max(UserFeatures.computed_at)))).scalar())},
    }

    # Clicks by position, last 7 days: distinct impressions and clicks per (feed load, event).
    week = now - timedelta(days=7)
    rows = (await db.execute(select(Activity.name, Activity.surface, Activity.position,
                                    Activity.rec_request_id, Activity.event_id, Activity.anonymous_id, Activity.user_id)
                             .where(Activity.name.in_(("feed_impression", "event_clicked")),
                                    Activity.occurred_at >= week, Activity.position.isnot(None),
                                    Activity.position < MAX_POSITION))).all()
    seen: dict[str, set] = {"feed_impression": set(), "event_clicked": set()}
    by_pos: dict[tuple[str, int], Counter] = defaultdict(Counter)
    unique = []
    for name, surface, pos, req, eid, anon, uid in rows:
        key = (req or anon or uid, surface, eid, pos)
        if key in seen[name]:
            continue
        seen[name].add(key)
        unique.append((name, req, eid))
        by_pos[(surface or "unknown", pos)][name] += 1
        by_pos[("all", pos)][name] += 1
    positions = defaultdict(list)
    for (surface, pos), c in sorted(by_pos.items(), key=lambda x: (x[0][0], x[0][1])):
        imp, clk = c["feed_impression"], c["event_clicked"]
        positions[surface].append({"position": pos, "impressions": imp, "clicks": clk,
                                   "ctr": round(clk / imp, 4) if imp else None})

    # Discovery slots: click-through of events placed there vs the feed's other cards.
    served = (await db.execute(select(Activity.rec_request_id, Activity.props).where(
        Activity.name == "recs_served", Activity.occurred_at >= week))).all()
    discovery = {req: set((props or {}).get("discovery_ids") or []) for req, props in served}
    slot = Counter()
    for name, req, eid in unique:
        if req in discovery:
            slot[(name, eid in discovery[req])] += 1
    def ctr(flag):
        imp = slot[("feed_impression", flag)]
        return {"impressions": imp, "clicks": slot[("event_clicked", flag)],
                "ctr": round(slot[("event_clicked", flag)] / imp, 4) if imp else None}

    return {
        "days": days, "generated_at": now,
        "events_per_day": daily, "top_events_24h": top_names, "ingestion": ingestion, "features": features,
        "recs_served_7d": len(served),
        "clicks_by_position": dict(positions),
        "discovery_slots": {"discovery": ctr(True), "other": ctr(False)},
        "zero_result_searches": await unmet_searches(db, days=7, limit=20, min_people=1, now=now),
    }
