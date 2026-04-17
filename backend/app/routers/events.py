import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.user import User
from app.schemas.event import (
    AttendRequest, CategoryOut, EventCreate, EventDetail, EventOut, EventUpdate,
)
from app.schemas.user import UserSummary

router = APIRouter(prefix="/api/events", tags=["events"])


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _load():
    return [selectinload(Event.host), selectinload(Event.category)]


def _serialize(event: Event, is_saved: bool = False, attendance_status: str | None = None) -> dict:
    return {
        "id": event.id, "title": event.title, "slug": event.slug,
        "cover_image": event.cover_image, "venue_name": event.venue_name,
        "address": event.address, "city": event.city, "country": event.country,
        "start_date": event.start_date, "end_date": event.end_date,
        "is_free": event.is_free, "price_min": event.price_min,
        "price_max": event.price_max, "currency": event.currency,
        "attendees_count": event.attendees_count, "interested_count": event.interested_count,
        "saves_count": event.saves_count, "status": event.status,
        "is_featured": event.is_featured, "is_trending": event.is_trending,
        "tags": event.tags, "host": event.host, "category": event.category,
        "created_at": event.created_at,
        "description": event.description, "gallery": event.gallery,
        "latitude": event.latitude, "longitude": event.longitude,
        "timezone": event.timezone, "ticket_url": event.ticket_url,
        "capacity": event.capacity,
        "is_saved": is_saved, "attendance_status": attendance_status,
    }


async def _user_state(event_id: str, user: User | None, db: AsyncSession):
    if not user:
        return False, None
    sv = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == user.id))).scalar_one_or_none()
    at = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    return sv is not None, (at.status if at else None)


# ── Categories ──────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Category).order_by(Category.name))).scalars().all()


# ── Listing ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[EventOut])
async def list_events(
    q: str | None = None,
    city: str | None = None,
    category: str | None = None,
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
    if city:
        stmt = stmt.where(Event.city.ilike(f"%{city}%"))
    if category:
        cat = (await db.execute(select(Category).where(Category.slug == category))).scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if trending is not None:
        stmt = stmt.where(Event.is_trending == trending)
    if free is not None:
        stmt = stmt.where(Event.is_free == free)

    events = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    result = []
    for e in events:
        saved, att = await _user_state(e.id, user, db)
        result.append(_serialize(e, saved, att))
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
    saved, att = await _user_state(event.id, user, db)
    return _serialize(event, saved, att)


# ── Create / Update ─────────────────────────────────────────────────────────────

@router.post("", response_model=EventDetail, status_code=201)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eid = str(uuid.uuid4())
    event = Event(id=eid, slug=_slugify(payload.title, eid),
                  host_id=user.id, **payload.model_dump())
    db.add(event)
    await db.flush()
    await db.execute(update(User).where(User.id == user.id).values(events_hosted=User.events_hosted + 1))
    stmt = select(Event).options(*_load()).where(Event.id == eid)
    return _serialize((await db.execute(stmt)).scalar_one())


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        raise HTTPException(403, "Not the event host")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(event, k, v)
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
        raise HTTPException(403, "Not the event host")
    await db.delete(event)


# ── RSVP ────────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/attend")
async def attend(
    event_id: str,
    payload: AttendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    existing = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()

    if existing:
        if existing.status == "going":
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

    return {"status": payload.status, "attendees_count": event.attendees_count}


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
