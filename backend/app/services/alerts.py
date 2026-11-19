"""Follower alerts with the Turnup+ head start (docs/venues-spec.md 4.6, 4.8 perk 3).

When an event goes live, followers of its host venue / linked venue / organizer are told.
Turnup+ members are notified straight away; everyone else gets a ScheduledAlert sent by the
worker after plus_early_alert_hours.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.social import Follow
from app.models.user import User
from app.models.venue import ScheduledAlert, Venue, VenueFollow
from app.services.plus import is_plus
from app.services.settings import get_platform_settings
from app.services.venue_access import notify


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _followers(db: AsyncSession, event: Event) -> tuple[dict[str, str], str]:
    """{user_id: source} and a display name for who posted it."""
    out: dict[str, str] = {}
    source = ""
    venue_id = event.host_venue_id or event.venue_id
    if venue_id:
        venue = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
        if venue:
            source = venue.name
            for uid in (await db.execute(select(VenueFollow.user_id).where(VenueFollow.venue_id == venue.id))).scalars().all():
                out[uid] = "venue"
    if not event.host_venue_id:
        host = (await db.execute(select(User).where(User.id == event.host_id))).scalar_one_or_none()
        source = (host.display_name or host.username) if host else source
        for uid in (await db.execute(select(Follow.follower_id).where(Follow.following_id == event.host_id))).scalars().all():
            out.setdefault(uid, "organizer")
    out.pop(event.host_id, None)
    return out, source


async def announce_event(db: AsyncSession, event: Event) -> dict:
    followers, source = await _followers(db, event)
    if not followers:
        return {"now": 0, "later": 0}
    ps = await get_platform_settings(db)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(list(followers))))).scalars().all()}
    title = f"New from {source}: {event.title}"
    now_n = later_n = 0
    for uid in followers:
        u = users.get(uid)
        if not u or not u.is_active:
            continue
        if is_plus(u) or ps.plus_early_alert_hours <= 0:
            notify(db, uid, "followed_new_event", title, "Turnup+ early alert" if is_plus(u) else None,
                   reference_id=event.id, reference_type="event")
            now_n += 1
        else:
            db.add(ScheduledAlert(user_id=uid, type="followed_new_event", title=title, reference_id=event.id,
                                  reference_type="event",
                                  send_at=utcnow() + timedelta(hours=ps.plus_early_alert_hours)))
            later_n += 1
    await db.flush()
    return {"now": now_n, "later": later_n}


async def notify_presale(db: AsyncSession, event: Event, tier_name: str) -> int:
    """Members who follow the host hear when a members' presale opens."""
    followers, source = await _followers(db, event)
    users = (await db.execute(select(User).where(User.id.in_(list(followers))))).scalars().all() if followers else []
    n = 0
    for u in users:
        if is_plus(u):
            notify(db, u.id, "plus_presale", f"Members' presale: {event.title}",
                   f"{tier_name} from {source} is on sale to Turnup+ members first.",
                   reference_id=event.id, reference_type="event")
            n += 1
    await db.flush()
    return n


async def send_due_alerts(db: AsyncSession) -> int:
    rows = (await db.execute(select(ScheduledAlert).where(
        ScheduledAlert.sent_at.is_(None), ScheduledAlert.send_at <= utcnow()).limit(2000))).scalars().all()
    for a in rows:
        notify(db, a.user_id, a.type, a.title, a.body, a.reference_id, a.reference_type)
        a.sent_at = utcnow()
    await db.commit()
    return len(rows)
