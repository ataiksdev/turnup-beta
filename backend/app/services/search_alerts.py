""""Notify me" for searches that found nothing: new events that match are sent as notifications.

The worker runs send_search_alerts() hourly. Each alert looks only at events created since it
was last checked, so nobody hears about the same event twice, and it expires after
ALERT_DAYS.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import SearchAlert
from app.models.event import Category, Event
from app.models.user import User
from app.services.hidden import exclude_hidden, hidden_for
from app.services.search import text_search
from app.services.venue_access import notify

ALERT_DAYS = 60
MAX_ACTIVE_PER_USER = 20


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def new_matches(db: AsyncSession, alert: SearchAlert, now: datetime, limit: int = 5) -> list[Event]:
    match, _ = await text_search(db, alert.query)
    if match is None:
        return []
    stmt = (select(Event).where(
        match,
        Event.status == "published", Event.review_status == "approved",
        Event.start_date > now,
        # (checked_at, now]: the next check starts exactly where this one stopped.
        Event.created_at > alert.checked_at, Event.created_at <= now,
    ).order_by(Event.created_at.desc()).limit(limit))
    if alert.city:
        stmt = stmt.where(Event.city.ilike(f"%{alert.city}%"))
    if alert.category:
        stmt = stmt.join(Category, Category.id == Event.category_id).where(Category.slug == alert.category)
    stmt = exclude_hidden(stmt, await hidden_for(db, alert.user_id))
    return list((await db.execute(stmt)).scalars().all())


async def send_search_alerts(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    alerts = (await db.execute(
        select(SearchAlert).join(User, User.id == SearchAlert.user_id)
        .where(SearchAlert.is_active == True, User.is_active == True, User.is_deleted == False)  # noqa: E712
    )).scalars().all()
    sent = expired = 0
    for alert in alerts:
        if _utc(alert.expires_at) <= now:
            alert.is_active = False
            expired += 1
            continue
        events = await new_matches(db, alert, now)
        alert.checked_at = now
        if not events:
            continue
        first, more = events[0], len(events) - 1
        body = first.title + (f" and {more} more" if more else "")
        notify(db, alert.user_id, "search_alert", f'New on Turnup for "{alert.query}"'[:200], body,
               reference_id=first.id, reference_type="event")
        alert.notified_count += 1
        alert.last_notified_at = now
        sent += 1
    await db.commit()
    return {"checked": len(alerts) - expired, "notified": sent, "expired": expired}


def new_alert(user_id: str, query: str, city: str | None, category: str | None) -> SearchAlert:
    now = datetime.now(timezone.utc)
    return SearchAlert(user_id=user_id, query=query, city=city, category=category,
                       created_at=now, checked_at=now, expires_at=now + timedelta(days=ALERT_DAYS))
