"""Weekend picks for Turnup+ members (docs/venues-spec.md 4.8 perk 8): upcoming Friday-Sunday
events in the member's city, ranked by what they follow and like, then popularity."""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventAttendee
from app.models.social import Follow
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


async def weekend_picks(db: AsyncSession, user: User, limit: int = 12) -> dict:
    start, end = weekend_window()
    q = select(Event).where(Event.status == "published", Event.review_status == "approved",
                            Event.start_date < end, Event.end_date >= max(start, datetime.now(timezone.utc)))
    if user.city:
        q = q.where(or_(Event.city.ilike(f"%{user.city}%"), Event.event_type != "physical"))
    events = (await db.execute(q.limit(400))).scalars().all()
    followed_people = set((await db.execute(select(Follow.following_id).where(Follow.follower_id == user.id))).scalars().all())
    followed_venues = set((await db.execute(select(VenueFollow.venue_id).where(VenueFollow.user_id == user.id))).scalars().all())
    going = set((await db.execute(select(EventAttendee.event_id).where(EventAttendee.user_id == user.id))).scalars().all())
    likes = {c.strip() for c in (user.category_preferences or "").split(",") if c.strip()}

    def score(e: Event) -> float:
        s = 0.0
        if e.host_id in followed_people:
            s += 5
        if (e.host_venue_id and e.host_venue_id in followed_venues) or (e.venue_id and e.venue_id in followed_venues):
            s += 5
        if e.category_id and e.category_id in likes:
            s += 3
        if e.is_featured:
            s += 1
        s += min(e.attendees_count, 500) / 100 + min(e.saves_count, 200) / 100
        return s

    ranked = sorted((e for e in events if e.id not in going), key=score, reverse=True)[:limit]
    return {"weekend_start": start, "weekend_end": end, "city": user.city,
            "events": [{"id": e.id, "slug": e.slug, "title": e.title, "cover_image": e.cover_image,
                        "start_date": e.start_date, "venue_name": e.venue_name, "city": e.city,
                        "is_free": e.is_free, "price_min": e.price_min, "members_only": e.members_only,
                        "because": ("You follow the host" if e.host_id in followed_people else
                                    "You follow the venue" if (e.host_venue_id in followed_venues or e.venue_id in followed_venues) else
                                    "Matches your interests" if e.category_id in likes else "Popular this weekend")}
                       for e in ranked]}


async def send_weekend_picks(db: AsyncSession) -> int:
    """Thursday job: tell each member their picks are ready (push/email ride on notifications)."""
    members = (await db.execute(select(User).where(User.plus_until > datetime.now(timezone.utc),
                                                   User.is_active == True))).scalars().all()  # noqa: E712
    n = 0
    for u in members:
        if not is_plus(u):
            continue
        picks = await weekend_picks(db, u, limit=3)
        if not picks["events"]:
            continue
        titles = ", ".join(e["title"] for e in picks["events"])
        notify(db, u.id, "weekend_picks", "Your weekend picks are ready", titles[:200], reference_type="weekend_picks")
        n += 1
    await db.commit()
    return n
