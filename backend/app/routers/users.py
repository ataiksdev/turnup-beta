from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Event, EventSave
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


def _event_row(event: Event, is_saved: bool = False) -> dict:
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
        "is_saved": is_saved, "attendance_status": None,
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
    return {**user.__dict__, "is_following": following}


@router.get("/{username}/events", response_model=list[EventOut])
async def get_user_events(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    stmt = (select(Event).options(selectinload(Event.host), selectinload(Event.category))
            .where(Event.host_id == u.id, Event.status == "published")
            .order_by(Event.start_date.desc())
            .offset((page - 1) * limit).limit(limit))
    events = (await db.execute(stmt)).scalars().all()
    return [_event_row(e) for e in events]


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
