from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Event, EventAttendee, EventSave
from app.models.social import Follow
from app.models.user import User
from app.schemas.event import EventPublic
from app.schemas.user import UserMe, UserPublic, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


async def _is_following(db: AsyncSession, follower_id: str, following_id: str) -> bool:
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == follower_id, Follow.following_id == following_id
        )
    )
    return result.scalar_one_or_none() is not None


@router.get("/{username}", response_model=UserPublic)
async def get_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_following = False
    if current_user and current_user.id != user.id:
        is_following = await _is_following(db, current_user.id, user.id)

    return {**user.__dict__, "is_following": is_following}


@router.patch("/me/profile", response_model=UserMe)
async def update_profile(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(user, field, val)
    await db.flush()
    return user


@router.get("/{username}/events", response_model=list[EventPublic])
async def get_user_events(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    u = await db.execute(select(User).where(User.username == username))
    user = u.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        select(Event)
        .options(
            selectinload(Event.host),
            selectinload(Event.category),
        )
        .where(Event.host_id == user.id, Event.status == "published")
        .order_by(Event.start_date.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    out = []
    for event in events:
        out.append({
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
            "created_at": event.created_at, "is_saved": False, "attendance_status": None,
        })
    return out


@router.get("/{username}/saved", response_model=list[EventPublic])
async def get_saved_events(
    username: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    u = await db.execute(select(User).where(User.username == username))
    user = u.scalar_one_or_none()
    if not user or user.id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    stmt = (
        select(Event)
        .join(EventSave, EventSave.event_id == Event.id)
        .options(selectinload(Event.host), selectinload(Event.category))
        .where(EventSave.user_id == user.id)
        .order_by(EventSave.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    out = []
    for event in events:
        out.append({
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
            "created_at": event.created_at, "is_saved": True, "attendance_status": None,
        })
    return out
