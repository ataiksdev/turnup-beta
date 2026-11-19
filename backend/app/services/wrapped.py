"""Turnup Wrapped (docs/venues-spec.md 4.8 perk 10): a yearly summary made to share.

Free users get the short version (counts); Turnup+ members get the full one (top venues,
organizers, cities, busiest month, and the friends they went out with most: only mutual
follows where both have Wrapped sharing on). Built from attended events: a checked-in ticket,
or a "going" RSVP to an event that has ended.
"""
import io
import json
from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventAttendee
from app.models.organizer import TicketOrder
from app.models.social import Follow
from app.models.user import User
from app.models.venue import WrappedReport
from app.services.plus import is_plus

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def available(year: int, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return year < now.year or (year == now.year and now.month == 12)


async def _attended(db: AsyncSession, user_id: str, start: datetime, end: datetime) -> list[Event]:
    now = datetime.now(timezone.utc)
    ticketed = select(TicketOrder.event_id).where(TicketOrder.user_id == user_id, TicketOrder.checked_in_at.is_not(None))
    going = select(EventAttendee.event_id).where(EventAttendee.user_id == user_id, EventAttendee.status == "going")
    return list((await db.execute(select(Event).where(
        or_(Event.id.in_(ticketed), Event.id.in_(going)),
        Event.start_date >= start, Event.start_date < end, Event.end_date < now,
        Event.status != "cancelled"))).scalars().all())


async def compute(db: AsyncSession, user: User, year: int) -> dict:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    events = await _attended(db, user.id, start, end)
    hosts = Counter(e.host_id for e in events if not e.host_venue_id)
    venues = Counter(e.venue_name for e in events if e.event_type != "virtual")
    cities = Counter(e.city for e in events if e.city)
    months = Counter(e.start_date.month for e in events)
    data = {"year": year, "events_attended": len(events), "cities_count": len(cities),
            "venues_count": len(venues), "full": False}
    if is_plus(user) and events:
        host_users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(list(hosts))))).scalars().all()}
        data.update(
            full=True,
            top_venues=[{"name": n, "visits": c} for n, c in venues.most_common(3)],
            top_organizers=[{"name": (host_users[h].display_name or host_users[h].username) if h in host_users else "",
                             "events": c} for h, c in hosts.most_common(3)],
            top_cities=[{"name": n, "events": c} for n, c in cities.most_common(3)],
            busiest_month=MONTHS[months.most_common(1)[0][0] - 1] if months else None,
            went_with=await _went_with(db, user, events),
        )
    return data


async def _went_with(db: AsyncSession, user: User, events: list[Event]) -> list[dict]:
    if not user.wrapped_opt_in or not events:
        return []
    following = set((await db.execute(select(Follow.following_id).where(Follow.follower_id == user.id))).scalars().all())
    followers = set((await db.execute(select(Follow.follower_id).where(Follow.following_id == user.id))).scalars().all())
    mutual = following & followers
    if not mutual:
        return []
    ids = [e.id for e in events]
    rows = (await db.execute(select(EventAttendee.user_id).where(
        EventAttendee.event_id.in_(ids), EventAttendee.user_id.in_(list(mutual)),
        EventAttendee.status == "going"))).scalars().all()
    counts = Counter(rows)
    friends = {u.id: u for u in (await db.execute(select(User).where(
        User.id.in_(list(counts)), User.wrapped_opt_in == True))).scalars().all()}  # noqa: E712
    return [{"username": friends[uid].username, "name": friends[uid].display_name or friends[uid].username,
             "events": c} for uid, c in counts.most_common() if uid in friends][:3]


async def get_wrapped(db: AsyncSession, user: User, year: int) -> dict:
    if not available(year):
        raise HTTPException(404, f"Wrapped for {year} opens in December.")
    row = (await db.execute(select(WrappedReport).where(
        WrappedReport.user_id == user.id, WrappedReport.year == year))).scalar_one_or_none()
    fresh = row and json.loads(row.data).get("full") == is_plus(user)
    if row and fresh and year < datetime.now(timezone.utc).year:
        return json.loads(row.data)
    data = await compute(db, user, year)
    if row:
        row.data = json.dumps(data)
        row.generated_at = datetime.now(timezone.utc)
    else:
        db.add(WrappedReport(user_id=user.id, year=year, data=json.dumps(data)))
    await db.flush()
    return data


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_png(data: dict) -> bytes:
    """A 1080x1920 story card for Instagram / WhatsApp status."""
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h), (24, 9, 33))
    d = ImageDraw.Draw(img)
    for y in range(h):  # simple vertical gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(24 + 200 * t), int(9 + 50 * t), int(33 + 40 * (1 - t))))
    d.text((80, 140), "TURNUP WRAPPED", font=_font(56), fill=(255, 200, 120))
    d.text((80, 220), str(data["year"]), font=_font(140), fill=(255, 255, 255))
    y = 470
    d.text((80, y), f"{data['events_attended']}", font=_font(200), fill=(255, 255, 255))
    d.text((80, y + 220), "events attended", font=_font(54), fill=(255, 230, 210))
    y += 360
    d.text((80, y), f"{data['venues_count']} venues  ·  {data['cities_count']} cities", font=_font(48), fill=(255, 255, 255))
    y += 110
    if data.get("full"):
        if data.get("busiest_month"):
            d.text((80, y), f"Busiest month: {data['busiest_month']}", font=_font(46), fill=(255, 255, 255))
            y += 90
        for title, key, unit in (("Top venues", "top_venues", "visits"), ("Went out most with", "went_with", "events")):
            items = data.get(key) or []
            if not items:
                continue
            d.text((80, y), title, font=_font(44), fill=(255, 200, 120))
            y += 70
            for it in items:
                d.text((110, y), f"{it['name'][:28]}  ({it[unit]})", font=_font(42), fill=(255, 255, 255))
                y += 62
            y += 30
    else:
        d.text((80, y), "Get the full story with Turnup+", font=_font(42), fill=(255, 230, 210))
    d.text((80, h - 140), "turnup", font=_font(64), fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


async def announce_wrapped(db: AsyncSession, year: int) -> int:
    """December job: tell people with at least one event that their Wrapped is ready."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    ids = set((await db.execute(select(EventAttendee.user_id).join(Event, Event.id == EventAttendee.event_id).where(
        EventAttendee.status == "going", Event.start_date >= start))).scalars().all())
    from app.models.social import Notification
    already = set((await db.execute(select(Notification.user_id).where(
        Notification.type == "wrapped_ready", Notification.reference_id == str(year)))).scalars().all())
    from app.services.venue_access import notify
    n = 0
    for uid in ids - already:
        notify(db, uid, "wrapped_ready", f"Your Turnup Wrapped {year} is ready", reference_id=str(year),
               reference_type="wrapped")
        n += 1
    await db.commit()
    return n
