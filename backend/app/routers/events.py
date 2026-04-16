import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.user import User
from app.schemas.event import (
    CategoryPublic,
    EventAttendeeCreate,
    EventCreate,
    EventDetail,
    EventPublic,
    EventUpdate,
)

router = APIRouter(prefix="/api/events", tags=["events"])


def slugify(text: str, uid: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return f"{slug}-{uid[:8]}"


def _event_load_options():
    return [
        selectinload(Event.host),
        selectinload(Event.category),
    ]


async def _enrich(event: Event, db: AsyncSession, user: User | None) -> dict:
    data = {
        "id": event.id,
        "title": event.title,
        "slug": event.slug,
        "cover_image": event.cover_image,
        "venue_name": event.venue_name,
        "address": event.address,
        "city": event.city,
        "country": event.country,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "is_free": event.is_free,
        "price_min": event.price_min,
        "price_max": event.price_max,
        "currency": event.currency,
        "attendees_count": event.attendees_count,
        "interested_count": event.interested_count,
        "saves_count": event.saves_count,
        "status": event.status,
        "is_featured": event.is_featured,
        "is_trending": event.is_trending,
        "tags": event.tags,
        "host": event.host,
        "category": event.category,
        "created_at": event.created_at,
        "is_saved": False,
        "attendance_status": None,
    }

    if user:
        save_q = await db.execute(
            select(EventSave).where(
                EventSave.event_id == event.id, EventSave.user_id == user.id
            )
        )
        data["is_saved"] = save_q.scalar_one_or_none() is not None

        att_q = await db.execute(
            select(EventAttendee).where(
                EventAttendee.event_id == event.id, EventAttendee.user_id == user.id
            )
        )
        att = att_q.scalar_one_or_none()
        data["attendance_status"] = att.status if att else None

    return data


# ── Categories ─────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryPublic])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


# ── Events CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[EventPublic])
async def list_events(
    q: str | None = Query(None, description="Search query"),
    city: str | None = Query(None),
    category: str | None = Query(None, description="Category slug"),
    featured: bool | None = Query(None),
    trending: bool | None = Query(None),
    free: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (
        select(Event)
        .options(*_event_load_options())
        .where(Event.status == "published")
        .order_by(Event.start_date.asc())
    )

    if q:
        stmt = stmt.where(
            or_(
                Event.title.ilike(f"%{q}%"),
                Event.description.ilike(f"%{q}%"),
                Event.city.ilike(f"%{q}%"),
                Event.venue_name.ilike(f"%{q}%"),
                Event.tags.ilike(f"%{q}%"),
            )
        )
    if city:
        stmt = stmt.where(Event.city.ilike(f"%{city}%"))
    if category:
        cat_q = await db.execute(select(Category).where(Category.slug == category))
        cat = cat_q.scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if trending is not None:
        stmt = stmt.where(Event.is_trending == trending)
    if free is not None:
        stmt = stmt.where(Event.is_free == free)

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [await _enrich(e, db, user) for e in events]


@router.post("", response_model=EventDetail, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    eid = str(uuid.uuid4())
    event = Event(
        id=eid,
        slug=slugify(payload.title, eid),
        host_id=user.id,
        **payload.model_dump(exclude_none=False),
    )
    db.add(event)
    await db.flush()

    # Increment host's events_hosted
    await db.execute(
        update(User).where(User.id == user.id).values(events_hosted=User.events_hosted + 1)
    )

    # Reload with relations
    result = await db.execute(
        select(Event).options(*_event_load_options()).where(Event.id == eid)
    )
    event = result.scalar_one()
    enriched = await _enrich(event, db, user)
    enriched["description"] = event.description
    enriched["gallery"] = event.gallery
    enriched["latitude"] = event.latitude
    enriched["longitude"] = event.longitude
    enriched["timezone"] = event.timezone
    enriched["ticket_url"] = event.ticket_url
    enriched["capacity"] = event.capacity
    return enriched


@router.get("/trending", response_model=list[EventPublic])
async def get_trending(
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (
        select(Event)
        .options(*_event_load_options())
        .where(Event.status == "published", Event.is_trending == True)
        .order_by(Event.attendees_count.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [await _enrich(e, db, user) for e in events]


@router.get("/featured", response_model=list[EventPublic])
async def get_featured(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (
        select(Event)
        .options(*_event_load_options())
        .where(Event.status == "published", Event.is_featured == True)
        .order_by(Event.start_date.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [await _enrich(e, db, user) for e in events]


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # Support lookup by id or slug
    stmt = select(Event).options(*_event_load_options()).where(
        or_(Event.id == event_id, Event.slug == event_id)
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    enriched = await _enrich(event, db, user)
    enriched["description"] = event.description
    enriched["gallery"] = event.gallery
    enriched["latitude"] = event.latitude
    enriched["longitude"] = event.longitude
    enriched["timezone"] = event.timezone
    enriched["ticket_url"] = event.ticket_url
    enriched["capacity"] = event.capacity
    return enriched


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.host_id != user.id:
        raise HTTPException(status_code=403, detail="Not the event host")

    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(event, field, val)

    await db.flush()

    result = await db.execute(
        select(Event).options(*_event_load_options()).where(Event.id == event_id)
    )
    event = result.scalar_one()
    enriched = await _enrich(event, db, user)
    enriched.update(
        description=event.description, gallery=event.gallery,
        latitude=event.latitude, longitude=event.longitude,
        timezone=event.timezone, ticket_url=event.ticket_url, capacity=event.capacity,
    )
    return enriched


# ── RSVP ───────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/attend", status_code=status.HTTP_200_OK)
async def attend_event(
    event_id: str,
    payload: EventAttendeeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    att_q = await db.execute(
        select(EventAttendee).where(
            EventAttendee.event_id == event_id, EventAttendee.user_id == user.id
        )
    )
    existing = att_q.scalar_one_or_none()

    if existing:
        old_status = existing.status
        existing.status = payload.status
        # Update counts
        if old_status == "going":
            event.attendees_count = max(0, event.attendees_count - 1)
        elif old_status == "interested":
            event.interested_count = max(0, event.interested_count - 1)
    else:
        att = EventAttendee(
            id=str(uuid.uuid4()),
            user_id=user.id,
            event_id=event_id,
            status=payload.status,
        )
        db.add(att)
        await db.execute(
            update(User).where(User.id == user.id).values(
                events_attended=User.events_attended + 1
            )
        )

    if payload.status == "going":
        event.attendees_count += 1
    elif payload.status == "interested":
        event.interested_count += 1

    return {"status": payload.status, "attendees_count": event.attendees_count}


@router.delete("/{event_id}/attend", status_code=status.HTTP_200_OK)
async def remove_attendance(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att_q = await db.execute(
        select(EventAttendee).where(
            EventAttendee.event_id == event_id, EventAttendee.user_id == user.id
        )
    )
    att = att_q.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="No attendance found")

    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one()

    if att.status == "going":
        event.attendees_count = max(0, event.attendees_count - 1)
        await db.execute(
            update(User).where(User.id == user.id).values(
                events_attended=max(0, User.events_attended - 1)
            )
        )
    elif att.status == "interested":
        event.interested_count = max(0, event.interested_count - 1)

    await db.delete(att)
    return {"status": None, "attendees_count": event.attendees_count}


# ── Saves ───────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/save", status_code=status.HTTP_200_OK)
async def toggle_save(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    save_q = await db.execute(
        select(EventSave).where(
            EventSave.event_id == event_id, EventSave.user_id == user.id
        )
    )
    existing = save_q.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        event.saves_count = max(0, event.saves_count - 1)
        return {"saved": False, "saves_count": event.saves_count}
    else:
        save = EventSave(id=str(uuid.uuid4()), user_id=user.id, event_id=event_id)
        db.add(save)
        event.saves_count += 1
        return {"saved": True, "saves_count": event.saves_count}


# ── Attendees list ─────────────────────────────────────────────────────────────

@router.get("/{event_id}/attendees")
async def get_attendees(
    event_id: str,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(EventAttendee)
        .options(selectinload(EventAttendee.user))
        .where(EventAttendee.event_id == event_id)
    )
    if status_filter:
        stmt = stmt.where(EventAttendee.status == status_filter)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    attendees = result.scalars().all()
    return [
        {
            "user": {
                "id": a.user.id,
                "username": a.user.username,
                "full_name": a.user.full_name,
                "avatar_url": a.user.avatar_url,
                "is_verified": a.user.is_verified,
                "followers_count": a.user.followers_count,
            },
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in attendees
    ]
