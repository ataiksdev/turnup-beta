import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_organizer, get_current_user, get_optional_user
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import (
    EventCoHost, EventReview, EventView, EventWaitlist, TicketOrder, TicketTier,
)
from app.models.social import Notification
from app.models.social import Follow
from app.models.user import User
from app.schemas.event import (
    AttendRequest, CategoryOut, EventCreate, EventDetail, EventOut, EventUpdate,
)
from app.schemas.organizer import (
    AnalyticsOut, CoHostInviteRequest, CoHostOut, CoHostRespondRequest,
    DailyViewOut, PurchaseTicketRequest, ReviewCreate, ReviewOut,
    TicketOrderOut, TicketTierCreate, TicketTierOut, TicketTierUpdate,
    WaitlistEntryOut, WaitlistNotifyRequest, WaitlistStatusOut,
)
from app.schemas.user import UserSummary

router = APIRouter(prefix="/api/events", tags=["events"])


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _load():
    return [selectinload(Event.host), selectinload(Event.category)]


def _serialize(event: Event, is_saved: bool = False,
               attendance_status: str | None = None,
               is_waitlisted: bool = False) -> dict:
    return {
        "id": event.id, "title": event.title, "slug": event.slug,
        "cover_image": event.cover_image, "venue_name": event.venue_name,
        "address": event.address, "city": event.city, "country": event.country,
        "start_date": event.start_date, "end_date": event.end_date,
        "is_free": event.is_free, "price_min": event.price_min,
        "price_max": event.price_max, "currency": event.currency,
        "attendees_count": event.attendees_count, "interested_count": event.interested_count,
        "saves_count": event.saves_count, "waitlist_count": event.waitlist_count,
        "views_count": event.views_count, "waitlist_enabled": event.waitlist_enabled,
        "status": event.status, "is_featured": event.is_featured,
        "is_trending": event.is_trending, "tags": event.tags,
        "host": event.host, "category": event.category,
        "created_at": event.created_at,
        "description": event.description, "gallery": event.gallery,
        "latitude": event.latitude, "longitude": event.longitude,
        "timezone": event.timezone,
        "capacity": event.capacity, "template_id": event.template_id,
        "event_type": event.event_type, "meeting_url": event.meeting_url,
        "is_saved": is_saved, "attendance_status": attendance_status,
        "is_waitlisted": is_waitlisted,
    }


async def _user_state(event_id: str, user: User | None, db: AsyncSession):
    if not user:
        return False, None, False
    sv = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == user.id))).scalar_one_or_none()
    at = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id, EventWaitlist.user_id == user.id,
        EventWaitlist.status.in_(["waiting", "notified"])))).scalar_one_or_none()
    return sv is not None, (at.status if at else None), wl is not None


async def _require_event_access(event_id: str, user: User, db: AsyncSession) -> Event:
    """Returns event if user is host or accepted co-host."""
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id == user.id:
        return event
    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == user.id,
        EventCoHost.status == "accepted",
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(403, "Not authorized for this event")
    return event


# ── Categories ──────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Category).order_by(Category.name))).scalars().all()


# ── Listing ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[EventOut])
async def list_events(
    q: str | None = None,
    tag: str | None = None,
    city: str | None = None,
    category: str | None = None,
    event_type: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    free: bool | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published")
            .order_by(Event.start_date.asc()))

    if q:
        stmt = stmt.where(or_(Event.title.ilike(f"%{q}%"), Event.city.ilike(f"%{q}%"),
                              Event.tags.ilike(f"%{q}%"), Event.venue_name.ilike(f"%{q}%")))
    if tag:
        # match comma-separated tag list exactly or as substring
        stmt = stmt.where(Event.tags.ilike(f"%{tag}%"))
    if city:
        stmt = stmt.where(Event.city.ilike(f"%{city}%"))
    if category:
        cat = (await db.execute(select(Category).where(Category.slug == category))).scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
    if event_type and event_type in ("physical", "virtual", "hybrid"):
        stmt = stmt.where(Event.event_type == event_type)
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if trending is not None:
        stmt = stmt.where(Event.is_trending == trending)
    if free is not None:
        stmt = stmt.where(Event.is_free == free)

    events = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    result = []
    for e in events:
        saved, att, waitlisted = await _user_state(e.id, user, db)
        result.append(_serialize(e, saved, att, waitlisted))
    return result


@router.get("/trending", response_model=list[EventOut])
async def trending_events(
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published", Event.is_trending == True)
            .order_by(Event.attendees_count.desc()).limit(limit))
    return [_serialize(e) for e in (await db.execute(stmt)).scalars().all()]


@router.get("/featured", response_model=list[EventOut])
async def featured_events(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published", Event.is_featured == True)
            .order_by(Event.start_date.asc()).limit(limit))
    return [_serialize(e) for e in (await db.execute(stmt)).scalars().all()]


@router.get("/for-you", response_model=list[EventOut])
async def for_you_events(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """
    Personalised recommendation feed. Scores every upcoming published event
    against six signals: category taste, location, budget history, social
    graph activity, tag overlap, and platform flags (trending/featured).
    Anonymous callers receive a trending-weighted fallback.
    """
    now = datetime.now(timezone.utc)

    # Candidate pool: upcoming published events (capped for scoring performance)
    candidates = (await db.execute(
        select(Event).options(*_load())
        .where(Event.status == "published", Event.start_date > now)
        .order_by(Event.start_date.asc())
        .limit(300)
    )).scalars().all()

    if not user:
        candidates.sort(key=lambda e: (e.is_trending, e.is_featured, e.attendees_count), reverse=True)
        return [_serialize(e) for e in candidates[:limit]]

    # ── Gather user signals ────────────────────────────────────────────────────

    # 1. Category preferences → category IDs
    raw_prefs = [p.strip() for p in (user.category_preferences or "").split(",") if p.strip()]
    pref_category_ids: set[str] = set()
    if raw_prefs:
        cats = (await db.execute(select(Category).where(Category.slug.in_(raw_prefs)))).scalars().all()
        pref_category_ids = {c.id for c in cats}

    # 2. User city from profile location field (first token before comma)
    user_city = (user.location or "").split(",")[0].strip().lower()

    # 3. Events user already saved or attending → exclude from results
    attended_ids = {
        r[0] for r in (await db.execute(
            select(EventAttendee.event_id).where(EventAttendee.user_id == user.id)
        )).all()
    }
    saved_ids = {
        r[0] for r in (await db.execute(
            select(EventSave.event_id).where(EventSave.user_id == user.id)
        )).all()
    }
    excluded_ids = attended_ids | saved_ids

    # 4. Taste tag profile: tags from events the user has attended
    history_tags_rows = (await db.execute(
        select(Event.tags).where(Event.id.in_(attended_ids), Event.tags.isnot(None))
    )).scalars().all()
    user_tags: set[str] = set()
    for row in history_tags_rows:
        user_tags.update(t.strip().lower() for t in row.split(",") if t.strip())

    # 5. Social signal: event IDs attended by people the user follows
    followed_ids = {
        r[0] for r in (await db.execute(
            select(Follow.following_id).where(Follow.follower_id == user.id)
        )).all()
    }
    social_event_ids: set[str] = set()
    if followed_ids:
        social_event_ids = {
            r[0] for r in (await db.execute(
                select(EventAttendee.event_id).where(
                    EventAttendee.user_id.in_(followed_ids),
                    EventAttendee.status == "going",
                )
            )).all()
        }

    # 6. Budget signal: infer max comfortable spend from confirmed orders
    paid_prices = (await db.execute(
        select(TicketOrder.unit_price).where(
            TicketOrder.user_id == user.id,
            TicketOrder.status == "confirmed",
            TicketOrder.unit_price > 0,
        )
    )).scalars().all()
    max_spend = max(paid_prices, default=0.0)
    prefers_free = max_spend == 0 and user.events_attended < 3

    # ── Score candidates ───────────────────────────────────────────────────────

    scored: list[tuple[float, Event]] = []
    for e in candidates:
        if e.id in excluded_ids:
            continue
        score = 0.0

        # Category preference match (strongest signal)
        if e.category_id and e.category_id in pref_category_ids:
            score += 3.0

        # Location proximity
        if user_city and e.city.lower().startswith(user_city):
            score += 2.0

        # Budget fit
        if e.is_free:
            score += 1.5 if prefers_free else 0.5
        elif max_spend > 0 and e.price_min is not None and e.price_min <= max_spend * 1.3:
            score += 1.5

        # Social proof from followed accounts
        if e.id in social_event_ids:
            score += 2.0

        # Tag taste overlap (each matching tag = 0.8)
        if e.tags and user_tags:
            e_tags = {t.strip().lower() for t in e.tags.split(",") if t.strip()}
            score += len(e_tags & user_tags) * 0.8

        # Platform quality signals
        if e.is_trending:
            score += 0.8
        if e.is_featured:
            score += 0.5

        # Popularity (soft cap at 1.0)
        score += min(e.attendees_count / 50.0, 1.0)

        # Freshness: events within the next 7 days get a boost
        days_away = max((e.start_date.replace(tzinfo=timezone.utc) - now).days, 0)
        if days_away <= 7:
            score += 0.5

        # Add a tiny noise term so equal-scored events vary between users
        score += (hash(f"{user.id}:{e.id}") % 100) / 1000.0

        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Resolve user-state for top N and build response
    result = []
    for _, e in scored[:limit]:
        sv, at, wl = await _user_state(e.id, user, db)
        result.append(_serialize(e, sv, at, wl))

    # Pad with trending events if personalised pool is thin
    if len(result) < limit:
        seen = {r["id"] for r in result} | excluded_ids
        fallback = [e for e in candidates if e.id not in seen]
        fallback.sort(key=lambda e: (e.is_trending, e.attendees_count), reverse=True)
        for e in fallback[: limit - len(result)]:
            sv, at, wl = await _user_state(e.id, user, db)
            result.append(_serialize(e, sv, at, wl))

    return result


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = select(Event).options(*_load()).where(
        or_(Event.id == event_id, Event.slug == event_id))
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    # Only show drafts to their host
    if event.status == "draft":
        if not user or event.host_id != user.id:
            raise HTTPException(404, "Event not found")
    saved, att, waitlisted = await _user_state(event.id, user, db)
    return _serialize(event, saved, att, waitlisted)


# ── Create / Update ─────────────────────────────────────────────────────────────

@router.post("", response_model=EventDetail, status_code=201)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_organizer),
):
    data = payload.model_dump()
    template_id = data.pop("template_id", None)

    # If creating from template, merge template defaults (payload fields take precedence)
    if template_id:
        from app.models.organizer import EventTemplate
        tmpl = (await db.execute(select(EventTemplate).where(
            EventTemplate.id == template_id,
            EventTemplate.organizer_id == user.id,
        ))).scalar_one_or_none()
        if tmpl:
            defaults = json.loads(tmpl.template_data)
            for k, v in defaults.items():
                if k in data and data[k] is None:
                    data[k] = v

    eid = str(uuid.uuid4())
    event = Event(id=eid, slug=_slugify(payload.title, eid),
                  host_id=user.id, template_id=template_id, **data)
    db.add(event)
    await db.flush()
    if event.status == "published":
        await db.execute(update(User).where(User.id == user.id).values(
            events_hosted=User.events_hosted + 1))
    stmt = select(Event).options(*_load()).where(Event.id == eid)
    return _serialize((await db.execute(stmt)).scalar_one())


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)
    was_draft = event.status == "draft"
    old_status = event.status
    old_start = event.start_date

    changes = payload.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(event, k, v)

    # Increment events_hosted counter when publishing for the first time
    if was_draft and event.status == "published":
        await db.execute(update(User).where(User.id == user.id).values(
            events_hosted=User.events_hosted + 1))

    # Notify attendees on cancellation or reschedule
    new_status = changes.get("status")
    new_start  = changes.get("start_date")
    notify_type = None
    notify_title = None
    notify_body  = None

    if new_status == "cancelled" and old_status != "cancelled":
        notify_type  = "event_update"
        notify_title = f"Event cancelled: {event.title}"
        notify_body  = f'"{event.title}" has been cancelled by the organizer.'
    elif new_start and old_start and str(new_start) != str(old_start):
        notify_type  = "event_update"
        notify_title = f"Event rescheduled: {event.title}"
        notify_body  = f'"{event.title}" has been moved to a new date. Check the event page for details.'

    if notify_type:
        attendee_rows = (await db.execute(
            select(EventAttendee.user_id)
            .where(EventAttendee.event_id == event_id,
                   EventAttendee.user_id != user.id)
        )).scalars().all()
        for attendee_id in attendee_rows:
            db.add(Notification(
                id=str(uuid.uuid4()),
                user_id=attendee_id,
                type=notify_type,
                title=notify_title,
                body=notify_body,
                reference_id=event_id,
                reference_type="event",
                actor_id=user.id,
            ))

    await db.flush()
    stmt = select(Event).options(*_load()).where(Event.id == event_id)
    return _serialize((await db.execute(stmt)).scalar_one())


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        raise HTTPException(403, "Only the host can delete this event")
    await db.delete(event)


# ── RSVP (attendees) ────────────────────────────────────────────────────────────

@router.post("/{event_id}/attend")
async def attend(
    event_id: str,
    payload: AttendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event or event.status != "published":
        raise HTTPException(404, "Event not found")

    existing = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()

    # Capacity check for "going" RSVPs
    if payload.status == "going" and not existing:
        if event.capacity and event.attendees_count >= event.capacity:
            if event.waitlist_enabled:
                return await _join_waitlist_internal(event, user, db)
            raise HTTPException(409, "Event is at capacity")

    if existing:
        old_status = existing.status
        if old_status == "going":
            event.attendees_count = max(0, event.attendees_count - 1)
        else:
            event.interested_count = max(0, event.interested_count - 1)
        existing.status = payload.status
    else:
        db.add(EventAttendee(id=str(uuid.uuid4()), user_id=user.id,
                             event_id=event_id, status=payload.status))
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=User.events_attended + 1))

    if payload.status == "going":
        event.attendees_count += 1
    else:
        event.interested_count += 1

    # Notify host when someone RSVPs going (skip if user is the host)
    if payload.status == "going" and event.host_id != user.id:
        db.add(Notification(
            id=str(uuid.uuid4()), user_id=event.host_id, type="going",
            title=f"{user.full_name} is going to your event",
            body=event.title,
            reference_id=event_id, reference_type="event", actor_id=user.id,
        ))

    return {"status": payload.status, "attendees_count": event.attendees_count,
            "interested_count": event.interested_count}


async def _join_waitlist_internal(event: Event, user: User, db: AsyncSession) -> dict:
    existing_wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event.id,
        EventWaitlist.user_id == user.id,
        EventWaitlist.status.in_(["waiting", "notified"]),
    ))).scalar_one_or_none()
    if existing_wl:
        return {"status": "waitlisted", "position": existing_wl.position,
                "waitlist_count": event.waitlist_count}
    position = event.waitlist_count + 1
    db.add(EventWaitlist(
        id=str(uuid.uuid4()),
        event_id=event.id,
        user_id=user.id,
        position=position,
    ))
    event.waitlist_count += 1
    return {"status": "waitlisted", "position": position,
            "waitlist_count": event.waitlist_count}


@router.delete("/{event_id}/attend")
async def remove_attendance(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Not attending")
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    if att.status == "going":
        event.attendees_count = max(0, event.attendees_count - 1)
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=max(0, User.events_attended - 1)))
    else:
        event.interested_count = max(0, event.interested_count - 1)
    await db.delete(att)
    return {"status": None}


# ── Save ─────────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/save")
async def toggle_save(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    existing = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == user.id))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        event.saves_count = max(0, event.saves_count - 1)
        return {"saved": False}
    db.add(EventSave(id=str(uuid.uuid4()), user_id=user.id, event_id=event_id))
    event.saves_count += 1
    return {"saved": True}


# ── Attendees list ────────────────────────────────────────────────────────────────

@router.get("/{event_id}/attendees")
async def get_attendees(
    event_id: str,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (select(EventAttendee).options(selectinload(EventAttendee.user))
            .where(EventAttendee.event_id == event_id))
    if status:
        stmt = stmt.where(EventAttendee.status == status)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [{"user": UserSummary.model_validate(r.user), "status": r.status,
             "created_at": r.created_at} for r in rows]


# ── Views / Analytics ─────────────────────────────────────────────────────────────

@router.post("/{event_id}/views", status_code=204)
async def record_view(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        return
    ip = request.client.host if request.client else None
    db.add(EventView(
        id=str(uuid.uuid4()),
        event_id=event_id,
        user_id=user.id if user else None,
        ip_address=ip,
    ))
    event.views_count += 1


@router.get("/{event_id}/analytics", response_model=AnalyticsOut)
async def get_analytics(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)

    # Daily views — last 14 days
    since = datetime.now(timezone.utc) - timedelta(days=14)
    views_result = await db.execute(
        select(
            func.date(EventView.viewed_at).label("date"),
            func.count(EventView.id).label("views"),
        )
        .where(EventView.event_id == event_id, EventView.viewed_at >= since)
        .group_by(func.date(EventView.viewed_at))
        .order_by(func.date(EventView.viewed_at))
    )
    daily_views = [DailyViewOut(date=str(r.date), views=r.views) for r in views_result]

    unique_views = (await db.execute(
        select(func.count(func.distinct(EventView.ip_address)))
        .where(EventView.event_id == event_id)
    )).scalar() or 0

    rsvp_going = (await db.execute(
        select(func.count(EventAttendee.id))
        .where(EventAttendee.event_id == event_id, EventAttendee.status == "going")
    )).scalar() or 0

    rsvp_interested = (await db.execute(
        select(func.count(EventAttendee.id))
        .where(EventAttendee.event_id == event_id, EventAttendee.status == "interested")
    )).scalar() or 0

    orders_result = await db.execute(
        select(func.count(TicketOrder.id), func.sum(TicketOrder.total_price))
        .where(TicketOrder.event_id == event_id, TicketOrder.status == "confirmed")
    )
    orders_row = orders_result.one()
    orders_count = orders_row[0] or 0
    revenue = float(orders_row[1] or 0)

    waitlist_count = (await db.execute(
        select(func.count(EventWaitlist.id))
        .where(EventWaitlist.event_id == event_id,
               EventWaitlist.status.in_(["waiting", "notified"]))
    )).scalar() or 0

    return AnalyticsOut(
        event_id=event_id,
        total_views=event.views_count,
        unique_views=unique_views,
        rsvp_going=rsvp_going,
        rsvp_interested=rsvp_interested,
        saves_count=event.saves_count,
        waitlist_count=waitlist_count,
        ticket_orders_count=orders_count,
        estimated_revenue=revenue,
        daily_views=daily_views,
    )


# ── Ticket tiers ──────────────────────────────────────────────────────────────────

@router.get("/{event_id}/tickets", response_model=list[TicketTierOut])
async def list_ticket_tiers(event_id: str, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TicketTier)
        .where(TicketTier.event_id == event_id, TicketTier.is_active == True)
        .order_by(TicketTier.price.asc())
    )
    tiers = result.scalars().all()
    return [_tier_out(t) for t in tiers]


@router.post("/{event_id}/tickets", response_model=TicketTierOut, status_code=201)
async def create_ticket_tier(
    event_id: str,
    payload: TicketTierCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = TicketTier(id=str(uuid.uuid4()), event_id=event_id, **payload.model_dump())
    db.add(t)
    await db.flush()
    return _tier_out(t)


@router.patch("/{event_id}/tickets/{tier_id}", response_model=TicketTierOut)
async def update_ticket_tier(
    event_id: str,
    tier_id: str,
    payload: TicketTierUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = await _get_tier(tier_id, event_id, db)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    await db.flush()
    return _tier_out(t)


@router.delete("/{event_id}/tickets/{tier_id}", status_code=204)
async def delete_ticket_tier(
    event_id: str,
    tier_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = await _get_tier(tier_id, event_id, db)
    if t.quantity_sold > 0:
        raise HTTPException(409, "Cannot delete a tier with existing orders")
    await db.delete(t)


@router.post("/{event_id}/tickets/{tier_id}/purchase", response_model=TicketOrderOut)
async def purchase_tickets(
    event_id: str,
    tier_id: str,
    payload: PurchaseTicketRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    t = await _get_tier(tier_id, event_id, db)
    if not t.is_active:
        raise HTTPException(400, "This ticket tier is not available")

    now = datetime.now(timezone.utc)
    if t.sale_start and now < t.sale_start:
        raise HTTPException(400, "Ticket sales have not started yet")
    if t.sale_end and now > t.sale_end:
        raise HTTPException(400, "Ticket sales have ended")
    if t.quantity is not None and (t.quantity - t.quantity_sold) < payload.quantity:
        raise HTTPException(409, f"Only {t.quantity - t.quantity_sold} tickets remaining")
    if payload.quantity > t.max_per_order:
        raise HTTPException(400, f"Maximum {t.max_per_order} tickets per order")

    total = t.price * payload.quantity
    order = TicketOrder(
        id=str(uuid.uuid4()),
        user_id=user.id,
        event_id=event_id,
        tier_id=tier_id,
        quantity=payload.quantity,
        unit_price=t.price,
        total_price=total,
        status="confirmed",
    )
    db.add(order)
    if t.quantity is not None:
        t.quantity_sold += payload.quantity
    # Auto RSVP as "going" after purchase
    existing_rsvp = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    if not existing_rsvp:
        db.add(EventAttendee(id=str(uuid.uuid4()), user_id=user.id,
                             event_id=event_id, status="going"))
        event.attendees_count += 1

    await db.flush()
    return TicketOrderOut(
        id=order.id, event_id=event_id, tier_id=tier_id, tier_name=t.name,
        quantity=payload.quantity, unit_price=t.price, total_price=total,
        status="confirmed", created_at=order.created_at,
    )


def _tier_out(t: TicketTier) -> TicketTierOut:
    available = (t.quantity - t.quantity_sold) if t.quantity is not None else None
    return TicketTierOut(
        id=t.id, event_id=t.event_id, name=t.name, description=t.description,
        price=t.price, currency=t.currency, quantity=t.quantity,
        quantity_sold=t.quantity_sold, available=available,
        max_per_order=t.max_per_order, is_active=t.is_active,
        sale_start=t.sale_start, sale_end=t.sale_end, created_at=t.created_at,
    )


async def _get_tier(tier_id: str, event_id: str, db: AsyncSession) -> TicketTier:
    t = (await db.execute(select(TicketTier).where(
        TicketTier.id == tier_id, TicketTier.event_id == event_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Ticket tier not found")
    return t


# ── Co-hosts ──────────────────────────────────────────────────────────────────────

@router.get("/{event_id}/cohosts", response_model=list[CoHostOut])
async def list_cohosts(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EventCoHost)
        .options(selectinload(EventCoHost.user))
        .where(EventCoHost.event_id == event_id)
    )
    return [_cohost_out(ch) for ch in result.scalars().all()]


@router.post("/{event_id}/cohosts", response_model=CoHostOut, status_code=201)
async def invite_cohost(
    event_id: str,
    payload: CoHostInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        raise HTTPException(403, "Only the host can invite co-hosts")

    invitee = (await db.execute(select(User).where(
        User.username == payload.username.lower()))).scalar_one_or_none()
    if not invitee:
        raise HTTPException(404, f"User @{payload.username} not found")
    if invitee.id == user.id:
        raise HTTPException(400, "Cannot invite yourself as co-host")

    existing = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == invitee.id,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"@{payload.username} already has a co-host entry for this event")

    ch = EventCoHost(
        id=str(uuid.uuid4()),
        event_id=event_id,
        user_id=invitee.id,
    )
    db.add(ch)

    # In-app notification
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=invitee.id,
        type="event_invite",
        title=f"Co-host invitation: {event.title}",
        body=f"@{user.username} invited you to co-host \"{event.title}\"",
        reference_id=event_id,
        reference_type="event",
        actor_id=user.id,
    ))
    await db.flush()
    await db.refresh(ch)
    ch.user = invitee
    return _cohost_out(ch)


@router.delete("/{event_id}/cohosts/{cohost_user_id}", status_code=204)
async def remove_cohost(
    event_id: str,
    cohost_user_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id and user.id != cohost_user_id:
        raise HTTPException(403, "Not authorized")

    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == cohost_user_id,
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "Co-host entry not found")
    await db.delete(ch)


@router.post("/{event_id}/cohosts/respond", status_code=200)
async def respond_to_cohost(
    event_id: str,
    payload: CoHostRespondRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == user.id,
        EventCoHost.status == "invited",
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "No pending co-host invitation for this event")

    ch.status = "accepted" if payload.accept else "declined"
    ch.responded_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": ch.status}


def _cohost_out(ch: EventCoHost) -> CoHostOut:
    return CoHostOut(
        id=ch.id,
        user_id=ch.user_id,
        username=ch.user.username,
        full_name=ch.user.full_name,
        avatar_url=ch.user.avatar_url,
        status=ch.status,
        invited_at=ch.invited_at,
        responded_at=ch.responded_at,
    )


# ── Waitlist ──────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/waitlist")
async def join_waitlist(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.waitlist_enabled:
        raise HTTPException(400, "This event does not have a waitlist")
    return await _join_waitlist_internal(event, user, db)


@router.delete("/{event_id}/waitlist", status_code=204)
async def leave_waitlist(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id,
        EventWaitlist.user_id == user.id,
    ))).scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Not on the waitlist")
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    await db.delete(wl)
    event.waitlist_count = max(0, event.waitlist_count - 1)


@router.get("/{event_id}/waitlist/status", response_model=WaitlistStatusOut)
async def waitlist_status(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id, EventWaitlist.user_id == user.id))).scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Not on the waitlist")
    ahead = (await db.execute(
        select(func.count(EventWaitlist.id))
        .where(EventWaitlist.event_id == event_id,
               EventWaitlist.status == "waiting",
               EventWaitlist.position < wl.position)
    )).scalar() or 0
    return WaitlistStatusOut(position=wl.position, status=wl.status, total_ahead=ahead)


@router.get("/{event_id}/waitlist", response_model=list[WaitlistEntryOut])
async def list_waitlist(
    event_id: str,
    status: str | None = "waiting",
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    stmt = (
        select(EventWaitlist)
        .options(selectinload(EventWaitlist.user))
        .where(EventWaitlist.event_id == event_id)
        .order_by(EventWaitlist.position.asc())
    )
    if status:
        stmt = stmt.where(EventWaitlist.status == status)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [
        WaitlistEntryOut(
            id=w.id, user_id=w.user_id,
            username=w.user.username, full_name=w.user.full_name,
            avatar_url=w.user.avatar_url, position=w.position,
            status=w.status, created_at=w.created_at, notified_at=w.notified_at,
        )
        for w in rows
    ]


@router.post("/{event_id}/waitlist/notify")
async def notify_waitlist(
    event_id: str,
    payload: WaitlistNotifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EventWaitlist)
        .options(selectinload(EventWaitlist.user))
        .where(EventWaitlist.event_id == event_id, EventWaitlist.status == "waiting")
        .order_by(EventWaitlist.position.asc())
        .limit(payload.count)
    )
    entries = result.scalars().all()
    notified = []
    for entry in entries:
        entry.status = "notified"
        entry.notified_at = now
        # In-app notification
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=entry.user_id,
            type="event_invite",
            title=f"You're off the waitlist! {event.title}",
            body=f"A spot opened up for \"{event.title}\". Register now before it's taken!",
            reference_id=event_id,
            reference_type="event",
            actor_id=user.id,
        ))
        notified.append(entry.user.username)
    await db.flush()
    return {"notified": notified, "count": len(notified)}


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/{event_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EventReview)
        .options(selectinload(EventReview.user))
        .where(EventReview.event_id == event_id)
        .order_by(EventReview.created_at.desc())
    )
    reviews = result.scalars().all()
    return [
        ReviewOut(
            id=r.id, event_id=r.event_id, user_id=r.user_id,
            username=r.user.username, full_name=r.user.full_name,
            avatar_url=r.user.avatar_url, rating=r.rating,
            body=r.body, created_at=r.created_at,
        )
        for r in reviews
    ]


@router.get("/{event_id}/reviews/me", response_model=ReviewOut | None)
async def my_review(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EventReview)
        .options(selectinload(EventReview.user))
        .where(EventReview.event_id == event_id, EventReview.user_id == user.id)
    )
    r = result.scalar_one_or_none()
    if not r:
        return None
    return ReviewOut(
        id=r.id, event_id=r.event_id, user_id=r.user_id,
        username=r.user.username, full_name=r.user.full_name,
        avatar_url=r.user.avatar_url, rating=r.rating,
        body=r.body, created_at=r.created_at,
    )


@router.post("/{event_id}/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    event_id: str,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(
        select(Event).where(Event.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    attended = (await db.execute(
        select(EventAttendee).where(
            EventAttendee.event_id == event_id,
            EventAttendee.user_id == user.id,
            EventAttendee.status == "going",
        )
    )).scalar_one_or_none()
    if not attended:
        raise HTTPException(403, "You can only review events you attended")

    existing = (await db.execute(
        select(EventReview).where(
            EventReview.event_id == event_id, EventReview.user_id == user.id
        )
    )).scalar_one_or_none()
    if existing:
        existing.rating = payload.rating
        existing.body = payload.body
        await db.flush()
        r = existing
    else:
        r = EventReview(
            id=str(uuid.uuid4()),
            event_id=event_id,
            user_id=user.id,
            rating=payload.rating,
            body=payload.body,
        )
        db.add(r)
        await db.flush()

    return ReviewOut(
        id=r.id, event_id=r.event_id, user_id=r.user_id,
        username=user.username, full_name=user.full_name,
        avatar_url=user.avatar_url, rating=r.rating,
        body=r.body, created_at=r.created_at,
    )


@router.delete("/{event_id}/reviews/me", status_code=204)
async def delete_review(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EventReview).where(
            EventReview.event_id == event_id, EventReview.user_id == user.id
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Review not found")
    await db.delete(r)
    await db.flush()
