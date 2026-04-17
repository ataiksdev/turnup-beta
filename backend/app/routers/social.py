import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.event import Event, EventAttendee
from app.models.social import Comment, Follow, Notification
from app.models.user import User
from app.schemas.social import CommentCreate, CommentOut, NotificationOut

router = APIRouter(prefix="/api/social", tags=["social"])


# ── Follow ────────────────────────────────────────────────────────────────────

@router.post("/follow/{username}")
async def follow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    target = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == me.id:
        raise HTTPException(400, "Cannot follow yourself")

    existing = (await db.execute(select(Follow).where(
        Follow.follower_id == me.id, Follow.following_id == target.id))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Already following")

    db.add(Follow(id=str(uuid.uuid4()), follower_id=me.id, following_id=target.id))
    db.add(Notification(
        id=str(uuid.uuid4()), user_id=target.id, type="follow",
        title=f"{me.full_name} started following you",
        actor_id=me.id, reference_id=me.id, reference_type="user",
    ))
    await db.flush()
    await db.execute(update(User).where(User.id == me.id).values(following_count=User.following_count + 1))
    await db.execute(update(User).where(User.id == target.id).values(followers_count=User.followers_count + 1))
    return {"following": True}


@router.delete("/follow/{username}")
async def unfollow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    target = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    follow = (await db.execute(select(Follow).where(
        Follow.follower_id == me.id, Follow.following_id == target.id))).scalar_one_or_none()
    if not follow:
        raise HTTPException(404, "Not following")
    await db.delete(follow)
    await db.flush()
    await db.execute(update(User).where(User.id == me.id).values(following_count=User.following_count - 1))
    await db.execute(update(User).where(User.id == target.id).values(followers_count=User.followers_count - 1))
    return {"following": False}


# ── Comments ──────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}/comments", response_model=list[CommentOut])
async def get_comments(
    event_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = (select(Comment).options(selectinload(Comment.user))
            .where(Comment.event_id == event_id, Comment.parent_id == None)
            .order_by(Comment.created_at.asc())
            .offset((page - 1) * limit).limit(limit))
    return (await db.execute(stmt)).scalars().all()


@router.post("/events/{event_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    event_id: str,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    comment = Comment(id=str(uuid.uuid4()), content=payload.content,
                      user_id=me.id, event_id=event_id, parent_id=payload.parent_id)
    db.add(comment)
    await db.flush()
    result = await db.execute(
        select(Comment).options(selectinload(Comment.user)).where(Comment.id == comment.id))
    return result.scalar_one()


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    comment = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.user_id != me.id:
        raise HTTPException(403, "Not the author")
    await db.delete(comment)


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=list[NotificationOut])
async def get_notifications(
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    stmt = (select(Notification).options(selectinload(Notification.actor))
            .where(Notification.user_id == me.id)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * limit).limit(limit))
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    return (await db.execute(stmt)).scalars().all()


@router.post("/notifications/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), me: User = Depends(get_current_user)):
    await db.execute(update(Notification).where(
        Notification.user_id == me.id, Notification.is_read == False).values(is_read=True))
    return {"ok": True}


# ── Activity feed ─────────────────────────────────────────────────────────────

@router.get("/feed")
async def activity_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    following_ids_q = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == me.id))
    following_ids = [r[0] for r in following_ids_q.fetchall()] + [me.id]

    stmt = (select(EventAttendee)
            .options(selectinload(EventAttendee.user),
                     selectinload(EventAttendee.event).selectinload(Event.host))
            .where(EventAttendee.user_id.in_(following_ids))
            .order_by(EventAttendee.created_at.desc())
            .offset((page - 1) * limit).limit(limit))
    rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "type": "attendance",
            "actor": {
                "id": r.user.id, "username": r.user.username,
                "full_name": r.user.full_name, "avatar_url": r.user.avatar_url,
                "is_verified": r.user.is_verified, "followers_count": r.user.followers_count,
            },
            "status": r.status,
            "event": {
                "id": r.event.id, "title": r.event.title,
                "slug": r.event.slug, "cover_image": r.event.cover_image,
                "city": r.event.city, "start_date": r.event.start_date,
            },
            "created_at": r.created_at,
        }
        for r in rows
    ]
