"""The activity log: what the app sends (POST /api/track), what the server records itself,
linking a device's anonymous browsing to an account, and forgetting it again.

See docs/recommendations-spec.md for the full list of events and what each one carries.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.activity import Activity, UserFeatures
from app.models.user import User

# What the app may send. Anything else in a batch is dropped.
CLIENT_EVENTS = frozenset({
    "session_started",
    "feed_impression", "event_clicked", "search_executed",
    "event_viewed", "event_dwell_ended", "event_shared",
    "ticket_drawer_opened", "ticket_tier_selected", "checkout_abandoned",
    "notification_interacted",
})

# Written only by the server, where the thing actually happens, so a modified app can't fake
# a purchase or a check-in. The app can't send these names.
SERVER_EVENTS = frozenset({
    "user_registered", "onboarding_completed", "profile_updated",
    "event_saved", "event_unsaved", "rsvp_changed",
    "checkout_started", "order_completed", "order_refunded", "ticket_transferred",
    "event_checked_in", "event_reviewed",
    "recs_served",
})

MAX_PROPS_BYTES = 2048          # from the app
MAX_SERVER_PROPS_BYTES = 16384  # server rows, e.g. recs_served listing up to 50 event ids
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_EVENT_AGE = timedelta(days=7)   # a phone offline for a week still delivers its queue


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_props(props: dict | None, limit: int = MAX_PROPS_BYTES) -> dict | None:
    if not props:
        return None
    try:
        encoded = json.dumps(props, default=str)
    except (TypeError, ValueError):
        return None
    return json.loads(encoded) if len(encoded.encode()) <= limit else None


def _occurred_at(ts: datetime | None, received: datetime) -> datetime:
    """The app's timestamp, unless the phone's clock is clearly wrong."""
    if ts is None:
        return received
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if ts > received + MAX_CLOCK_SKEW or ts < received - MAX_EVENT_AGE:
        return received
    return ts


def record(db: AsyncSession, name: str, *, user_id: str | None = None, event_id: str | None = None,
           props: dict | None = None, surface: str | None = None,
           rec_request_id: str | None = None, anonymous_id: str | None = None) -> None:
    """Write a server event. It's added to the caller's transaction, so it's only kept if
    what it describes (the order, the RSVP...) is committed too."""
    assert name in SERVER_EVENTS, name
    now = _now()
    db.add(Activity(
        name=name, source="server", occurred_at=now, received_at=now,
        user_id=user_id, anonymous_id=anonymous_id, event_id=event_id, surface=surface,
        rec_request_id=rec_request_id, props=_clean_props(props, MAX_SERVER_PROPS_BYTES),
    ))


async def ingest(db: AsyncSession, batch, user: User | None) -> int:
    """Store a batch from the app. Returns how many events were kept (unknown names,
    duplicates and oversized details are dropped quietly: the app never needs to retry them)."""
    received = _now()
    keep_coords = bool(user and user.profiling_consent and batch.geo
                       and batch.geo.lat is not None and batch.geo.lon is not None)
    geo_city = (batch.geo.city if batch.geo and batch.geo.city else None) or (user.city if user else None)

    if user:
        # Anything this device logged signed out (e.g. a feed served before the app had loaded
        # the saved sign-in) belongs to the account too. Cheap: indexed, usually zero rows.
        await link_anonymous(db, user, batch.anonymous_id)

    events = [e for e in batch.events if e.name in CLIENT_EVENTS]
    ids = {e.id for e in events if e.id}
    seen: set[str] = set()
    if ids:
        seen = set((await db.execute(
            select(Activity.client_id).where(Activity.client_id.in_(ids)))).scalars().all())

    rows: list[Activity] = []
    for e in events:
        if e.id:
            if e.id in seen:
                continue
            seen.add(e.id)
        props = _clean_props(e.props)
        if e.props and props is None:
            continue  # details too large or not JSON: drop the event rather than store junk
        rows.append(Activity(
            client_id=e.id, name=e.name, source="client",
            occurred_at=_occurred_at(e.ts, received), received_at=received,
            user_id=user.id if user else None, anonymous_id=batch.anonymous_id,
            session_id=batch.session_id, platform=batch.platform, app_version=batch.app_version,
            event_id=e.event_id, surface=e.surface, position=e.position,
            rec_request_id=e.rec_request_id, is_promoted=bool(e.is_promoted),
            geo_city=geo_city,
            geo_lat=round(batch.geo.lat, 5) if keep_coords else None,
            geo_lon=round(batch.geo.lon, 5) if keep_coords else None,
            referrer=batch.referrer, utm_campaign=batch.utm_campaign, props=props,
        ))
    if not rows:
        return 0
    try:
        async with db.begin_nested():
            db.add_all(rows)
    except IntegrityError:
        # The same batch arrived twice at once (a retry racing the original): keep what's new.
        kept = 0
        for row in rows:
            try:
                async with db.begin_nested():
                    db.add(Activity(**{c.key: getattr(row, c.key)
                                       for c in Activity.__table__.columns if c.key != "id"}))
                kept += 1
            except IntegrityError:
                pass
        return kept
    return len(rows)


async def link_anonymous(db: AsyncSession, user: User, anonymous_id: str) -> int:
    """Signing in on a device claims what it browsed while signed out (recent rows only), so
    recommendations start from what the person already looked at."""
    since = _now() - timedelta(days=settings.anonymous_stitch_days)
    result = await db.execute(
        update(Activity)
        .where(Activity.anonymous_id == anonymous_id, Activity.user_id.is_(None),
               Activity.occurred_at >= since)
        .values(user_id=user.id)
    )
    return result.rowcount or 0


async def forget_user(db: AsyncSession, user_id: str) -> None:
    """Account deletion: remove their activity (including what their devices did while signed
    out) and everything computed from it."""
    anon_ids = set((await db.execute(
        select(Activity.anonymous_id).where(Activity.user_id == user_id,
                                            Activity.anonymous_id.isnot(None)).distinct()
    )).scalars().all())
    cond = Activity.user_id == user_id
    if anon_ids:
        cond = or_(cond, Activity.anonymous_id.in_(anon_ids))
    await db.execute(delete(Activity).where(cond))
    await db.execute(delete(UserFeatures).where(UserFeatures.user_id == user_id))


async def prune_old_activity(db: AsyncSession) -> dict:
    cutoff = _now() - timedelta(days=settings.activity_retention_days)
    result = await db.execute(delete(Activity).where(Activity.occurred_at < cutoff))
    await db.commit()
    return {"deleted": result.rowcount or 0, "older_than_days": settings.activity_retention_days}


def new_request_id() -> str:
    return str(uuid.uuid4())
