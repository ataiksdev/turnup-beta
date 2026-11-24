"""Weekend picks for Turnup+ members (docs/venues-spec.md 4.8 perk 8): upcoming Friday-Sunday
events in the member's city or online, ranked by the For You ranker (hidden events and
organizers already left out there)."""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.user import User
from app.models.venue import VenueFollow
from app.services.plus import is_plus
from app.services.venue_access import notify

LAGOS = timezone(timedelta(hours=1))


def weekend_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The coming Friday 00:00 to Monday 00:00, Lagos time (this weekend if already in it)."""
    now = (now or datetime.now(timezone.utc)).astimezone(LAGOS)
    days_to_friday = (4 - now.weekday()) % 7
    if now.weekday() in (5, 6):  # Sat/Sun: this weekend
        days_to_friday = -(now.weekday() - 4)
    friday = datetime.combine((now + timedelta(days=days_to_friday)).date(), time(0), tzinfo=LAGOS)
    return friday, friday + timedelta(days=3)


async def weekend_picks(db: AsyncSession, user: User, limit: int = 12, log: bool = True) -> dict:
    """The For You ranker (app/services/recommender.py) over this weekend's events, in the
    member's city or online, with events at venues they follow moved up."""
    from app.services.recommender import recommend
    start, end = weekend_window()
    result = await recommend(db, user=user, limit=max(limit * 3, 30), window=(start, end),
                             surface="weekend_picks", log=log)
    events = [e for e in result.events if e.review_status == "approved"]
    if user.city:
        city = user.city.strip().lower()
        events = [e for e in events if e.event_type != "physical" or city in (e.city or "").lower()]
    followed_venues = set((await db.execute(select(VenueFollow.venue_id).where(VenueFollow.user_id == user.id))).scalars().all())

    def at_followed_venue(e: Event) -> bool:
        return bool({e.host_venue_id, e.venue_id} & followed_venues - {None})

    events.sort(key=lambda e: not at_followed_venue(e))  # stable: ranker order otherwise
    events = events[:limit]
    return {"weekend_start": start, "weekend_end": end, "city": user.city,
            "rec_request_id": result.request_id if log else None,
            "events": [{"id": e.id, "slug": e.slug, "title": e.title, "cover_image": e.cover_image,
                        "start_date": e.start_date, "venue_name": e.venue_name, "city": e.city,
                        "is_free": e.is_free, "price_min": e.price_min, "members_only": e.members_only,
                        "because": ("You follow the venue" if at_followed_venue(e)
                                    else result.reasons.get(e.id) or "Popular this weekend")}
                       for e in events]}


async def send_weekend_picks(db: AsyncSession) -> int:
    """Thursday job: tell each member their picks are ready (push/email ride on notifications)."""
    members = (await db.execute(select(User).where(User.plus_until > datetime.now(timezone.utc),
                                                   User.is_active == True))).scalars().all()  # noqa: E712
    n = 0
    for u in members:
        if not is_plus(u):
            continue
        picks = await weekend_picks(db, u, limit=3, log=False)
        if not picks["events"]:
            continue
        titles = ", ".join(e["title"] for e in picks["events"])
        notify(db, u.id, "weekend_picks", "Your weekend picks are ready", titles[:200], reference_type="weekend_picks")
        n += 1
    await db.commit()
    return n
