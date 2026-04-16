import re
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_optional_user_id, get_user_id
from app.config import settings
from app.database import get_db
from app.models import Category, Event, EventAttendee, EventSave
from app.schemas import (
    AttendRequest, CategoryOut, EventCreate, EventDetail, EventOut, EventUpdate, HostSummary,
)

router = APIRouter()


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return f"{s}-{uid[:8]}"


async def _fetch_user(user_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}", timeout=5)
        if r.status_code != 200:
            raise HTTPException(404, "User not found")
        return r.json()


def _host_summary(event: Event) -> HostSummary:
    return HostSummary(
        id=event.host_id,
        username=event.host_username,
        full_name=event.host_full_name,
        avatar_url=event.host_avatar_url,
        is_verified=event.host_is_verified,
    )


def _event_out(event: Event, is_saved: bool = False, attendance_status: str | None = None) -> dict:
    return {
        **{c.name: getattr(event, c.name) for c in event.__table__.columns},
        "host": _host_summary(event),
        "category": event.category,
        "is_saved": is_saved,
        "attendance_status": attendance_status,
    }


async def _per_user_state(event_id: str, user_id: str | None, db: AsyncSession):
    if not user_id:
        return False, None
    s = await db.execute(select(EventSave).where(EventSave.event_id == event_id, EventSave.user_id == user_id))
    a = await db.execute(select(EventAttendee).where(EventAttendee.event_id == event_id, EventAttendee.user_id == user_id))
    att = a.scalar_one_or_none()
    return s.scalar_one_or_none() is not None, (att.status if att else None)


# ── Categories ──────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Category).order_by(Category.name))
    return r.scalars().all()


# ── Event listing ───────────────────────────────────────────────────────────────

@router.get("/events", response_model=list[EventOut])
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
    uid: str | None = Depends(get_optional_user_id),
):
    stmt = (select(Event).options(selectinload(Event.category))
            .where(Event.status == "published").order_by(Event.start_date.asc()))

    if q:
        stmt = stmt.where(or_(Event.title.ilike(f"%{q}%"), Event.city.ilike(f"%{q}%"),
                              Event.tags.ilike(f"%{q}%"), Event.venue_name.ilike(f"%{q}%")))
    if city:
        stmt = stmt.where(Event.city.ilike(f"%{city}%"))
    if category:
        cat_r = await db.execute(select(Category).where(Category.slug == category))
        cat = cat_r.scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if trending is not None:
        stmt = stmt.where(Event.is_trending == trending)
    if free is not None:
        stmt = stmt.where(Event.is_free == free)

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    events = (await db.execute(stmt)).scalars().all()

    result = []
    for e in events:
        saved, att = await _per_user_state(e.id, uid, db)
        result.append(_event_out(e, saved, att))
    return result


@router.get("/events/trending", response_model=list[EventOut])
async def trending_events(limit: int = Query(10, ge=1, le=30), db: AsyncSession = Depends(get_db),
                           uid: str | None = Depends(get_optional_user_id)):
    stmt = (select(Event).options(selectinload(Event.category))
            .where(Event.status == "published", Event.is_trending == True)
            .order_by(Event.attendees_count.desc()).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_out(e) for e in events]


@router.get("/events/featured", response_model=list[EventOut])
async def featured_events(limit: int = Query(6, ge=1, le=20), db: AsyncSession = Depends(get_db),
                           uid: str | None = Depends(get_optional_user_id)):
    stmt = (select(Event).options(selectinload(Event.category))
            .where(Event.status == "published", Event.is_featured == True)
            .order_by(Event.start_date.asc()).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_out(e) for e in events]


@router.get("/events/{event_id}", response_model=EventDetail)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db),
                    uid: str | None = Depends(get_optional_user_id)):
    stmt = select(Event).options(selectinload(Event.category)).where(
        or_(Event.id == event_id, Event.slug == event_id))
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    saved, att = await _per_user_state(event.id, uid, db)
    return _event_out(event, saved, att)


# ── Create / Update ─────────────────────────────────────────────────────────────

@router.post("/events", response_model=EventDetail, status_code=201)
async def create_event(payload: EventCreate, db: AsyncSession = Depends(get_db),
                       uid: str = Depends(get_user_id)):
    user = await _fetch_user(uid)
    eid = str(uuid.uuid4())
    event = Event(
        id=eid, slug=_slugify(payload.title, eid),
        host_id=uid, host_username=user["username"],
        host_full_name=user["full_name"], host_avatar_url=user.get("avatar_url"),
        host_is_verified=user.get("is_verified", False),
        **payload.model_dump(),
    )
    db.add(event)
    await db.flush()
    stmt = select(Event).options(selectinload(Event.category)).where(Event.id == eid)
    event = (await db.execute(stmt)).scalar_one()
    return _event_out(event)


@router.patch("/events/{event_id}", response_model=EventDetail)
async def update_event(event_id: str, payload: EventUpdate, db: AsyncSession = Depends(get_db),
                       uid: str = Depends(get_user_id)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != uid:
        raise HTTPException(403, "Not the event host")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(event, k, v)
    await db.flush()
    stmt = select(Event).options(selectinload(Event.category)).where(Event.id == event_id)
    event = (await db.execute(stmt)).scalar_one()
    return _event_out(event)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: str, db: AsyncSession = Depends(get_db), uid: str = Depends(get_user_id)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != uid:
        raise HTTPException(403, "Not the event host")
    await db.delete(event)


# ── RSVP ────────────────────────────────────────────────────────────────────────

@router.post("/events/{event_id}/attend")
async def attend(event_id: str, payload: AttendRequest, db: AsyncSession = Depends(get_db),
                 uid: str = Depends(get_user_id)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    existing = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == uid))).scalar_one_or_none()

    if existing:
        if existing.status == "going":
            event.attendees_count = max(0, event.attendees_count - 1)
        else:
            event.interested_count = max(0, event.interested_count - 1)
        existing.status = payload.status
    else:
        db.add(EventAttendee(id=str(uuid.uuid4()), user_id=uid, event_id=event_id, status=payload.status))

    if payload.status == "going":
        event.attendees_count += 1
    else:
        event.interested_count += 1

    return {"status": payload.status, "attendees_count": event.attendees_count}


@router.delete("/events/{event_id}/attend")
async def remove_attendance(event_id: str, db: AsyncSession = Depends(get_db), uid: str = Depends(get_user_id)):
    att = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == uid))).scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Not attending")
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    if att.status == "going":
        event.attendees_count = max(0, event.attendees_count - 1)
    else:
        event.interested_count = max(0, event.interested_count - 1)
    await db.delete(att)
    return {"status": None}


# ── Save / Unsave ────────────────────────────────────────────────────────────────

@router.post("/events/{event_id}/save")
async def toggle_save(event_id: str, db: AsyncSession = Depends(get_db), uid: str = Depends(get_user_id)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    existing = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == uid))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        event.saves_count = max(0, event.saves_count - 1)
        return {"saved": False}
    db.add(EventSave(id=str(uuid.uuid4()), user_id=uid, event_id=event_id))
    event.saves_count += 1
    return {"saved": True}


# ── Attendees list ───────────────────────────────────────────────────────────────

@router.get("/events/{event_id}/attendees")
async def get_attendees(event_id: str, status: str | None = None,
                        limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    stmt = select(EventAttendee).where(EventAttendee.event_id == event_id)
    if status:
        stmt = stmt.where(EventAttendee.status == status)
    stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"user_id": r.user_id, "status": r.status, "created_at": r.created_at} for r in rows]


# ── Internal endpoint (for users-service / social-service) ──────────────────────

@router.get("/internal/events/by-host/{host_id}", response_model=list[EventOut])
async def events_by_host(host_id: str, page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = (select(Event).options(selectinload(Event.category))
            .where(Event.host_id == host_id, Event.status == "published")
            .order_by(Event.start_date.desc()).offset((page-1)*limit).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_out(e) for e in events]


@router.get("/internal/events/saved-by/{user_id}", response_model=list[EventOut])
async def events_saved_by(user_id: str, page: int = 1, limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = (select(Event).options(selectinload(Event.category))
            .join(EventSave, EventSave.event_id == Event.id)
            .where(EventSave.user_id == user_id)
            .order_by(EventSave.created_at.desc()).offset((page-1)*limit).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_out(e, is_saved=True) for e in events]
