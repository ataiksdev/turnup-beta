from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Event, EventAttendee, EventSave
from app.models.organizer import EventReview
from app.models.social import Follow
from app.models.user import User
from app.schemas.event import EventOut
from app.schemas.user import UserPublic

router = APIRouter(prefix="/api/users", tags=["users"])


async def _is_following(db: AsyncSession, follower_id: str, following_id: str) -> bool:
    r = (await db.execute(select(Follow).where(
        Follow.follower_id == follower_id, Follow.following_id == following_id
    ))).scalar_one_or_none()
    return r is not None


def _event_row(event: Event, is_saved: bool = False, attendance_status: str | None = None) -> dict:
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
        "status": event.status,
        "is_featured": event.is_featured, "is_trending": event.is_trending,
        "tags": event.tags, "host": event.host, "category": event.category,
        "created_at": event.created_at,
        "description": event.description, "gallery": event.gallery,
        "latitude": event.latitude, "longitude": event.longitude,
        "timezone": event.timezone,
        "capacity": event.capacity, "event_type": event.event_type,
        "is_saved": is_saved, "attendance_status": attendance_status,
        "review_status": event.review_status, "review_note": event.review_note,
        "created_via": event.created_via,
    }


@router.get("/{username}", response_model=UserPublic)
async def get_profile(
    username: str,
    db: AsyncSession = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    following = False
    if me and me.id != user.id:
        following = await _is_following(db, me.id, user.id)

    # Compute events_hosted dynamically (stored counter may lag on seed data)
    hosted_count = (await db.execute(
        select(func.count(Event.id)).where(
            Event.host_id == user.id, Event.status == "published"
        )
    )).scalar() or 0

    # Compute avg_rating and review_count across all events hosted by this user
    review_agg = (await db.execute(
        select(func.avg(EventReview.rating), func.count(EventReview.id))
        .join(Event, Event.id == EventReview.event_id)
        .where(Event.host_id == user.id)
    )).one()
    avg_rating = round(float(review_agg[0]), 1) if review_agg[0] else None
    review_count = review_agg[1] or 0

    return {
        **user.__dict__,
        "is_following": following,
        "events_hosted": hosted_count,
        "avg_rating": avg_rating,
        "review_count": review_count,
    }


@router.get("/{username}/events", response_model=list[EventOut])
async def get_user_events(
    username: str,
    past: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    now = datetime.now(timezone.utc)
    stmt = (select(Event).options(selectinload(Event.host), selectinload(Event.category))
            .where(Event.host_id == u.id, Event.status == "published"))
    if past:
        stmt = stmt.where(Event.end_date < now).order_by(Event.start_date.desc())
    else:
        stmt = stmt.where(Event.end_date >= now).order_by(Event.start_date.asc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    events = (await db.execute(stmt)).scalars().all()
    return [_event_row(e) for e in events]


@router.get("/{username}/attending", response_model=list[EventOut])
async def get_attending_events(
    username: str,
    past: bool = False,
    status: str | None = None,   # "going" | "interested" | None = both
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u or u.id != me.id:
        raise HTTPException(403, "Access denied")
    now = datetime.now(timezone.utc)
    stmt = (select(Event, EventAttendee.status)
            .options(selectinload(Event.host), selectinload(Event.category))
            .join(EventAttendee, EventAttendee.event_id == Event.id)
            .where(EventAttendee.user_id == u.id))
    if status in ("going", "interested"):
        stmt = stmt.where(EventAttendee.status == status)
    if past:
        stmt = stmt.where(Event.end_date < now).order_by(Event.start_date.desc())
    else:
        stmt = stmt.where(Event.end_date >= now).order_by(Event.start_date.asc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_event_row(row.Event, attendance_status=row.status) for row in rows]


@router.get("/{username}/saved", response_model=list[EventOut])
async def get_saved_events(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u or u.id != me.id:
        raise HTTPException(403, "Access denied")
    stmt = (select(Event).options(selectinload(Event.host), selectinload(Event.category))
            .join(EventSave, EventSave.event_id == Event.id)
            .where(EventSave.user_id == u.id)
            .order_by(EventSave.created_at.desc())
            .offset((page - 1) * limit).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_row(e, is_saved=True) for e in events]


@router.get("/{username}/followers", response_model=list[UserPublic])
async def get_followers(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    stmt = (select(User).join(Follow, Follow.follower_id == User.id)
            .where(Follow.following_id == u.id)
            .offset((page - 1) * limit).limit(limit))
    users = (await db.execute(stmt)).scalars().all()
    return [{**user.__dict__, "is_following": False} for user in users]


@router.get("/{username}/following", response_model=list[UserPublic])
async def get_following(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    stmt = (select(User).join(Follow, Follow.following_id == User.id)
            .where(Follow.follower_id == u.id)
            .offset((page - 1) * limit).limit(limit))
    users = (await db.execute(stmt)).scalars().all()
    return [{**user.__dict__, "is_following": False} for user in users]
