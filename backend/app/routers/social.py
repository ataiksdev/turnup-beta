import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.social import Comment, Follow, Notification
from app.models.user import User
from app.schemas.social import CommentCreate, CommentPublic, NotificationPublic

router = APIRouter(prefix="/api/social", tags=["social"])


# ── Follow / Unfollow ──────────────────────────────────────────────────────────

@router.post("/follow/{username}", status_code=status.HTTP_200_OK)
async def follow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.username == username))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id, Follow.following_id == target.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already following")

    follow = Follow(id=str(uuid.uuid4()), follower_id=current_user.id, following_id=target.id)
    db.add(follow)

    # Update counts
    await db.execute(
        update(User).where(User.id == current_user.id).values(
            following_count=User.following_count + 1
        )
    )
    await db.execute(
        update(User).where(User.id == target.id).values(
            followers_count=User.followers_count + 1
        )
    )

    # Create notification
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=target.id,
        type="follow",
        title=f"{current_user.full_name} started following you",
        actor_id=current_user.id,
        reference_id=current_user.id,
        reference_type="user",
    )
    db.add(notif)

    return {"following": True, "followers_count": target.followers_count + 1}


@router.delete("/follow/{username}", status_code=status.HTTP_200_OK)
async def unfollow_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.username == username))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    follow_q = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id, Follow.following_id == target.id
        )
    )
    follow = follow_q.scalar_one_or_none()
    if not follow:
        raise HTTPException(status_code=404, detail="Not following")

    await db.delete(follow)
    await db.execute(
        update(User).where(User.id == current_user.id).values(
            following_count=User.following_count - 1
        )
    )
    await db.execute(
        update(User).where(User.id == target.id).values(
            followers_count=User.followers_count - 1
        )
    )

    return {"following": False, "followers_count": max(0, target.followers_count - 1)}


# ── Comments ───────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}/comments", response_model=list[CommentPublic])
async def get_comments(
    event_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Comment)
        .options(selectinload(Comment.user))
        .where(Comment.event_id == event_id, Comment.parent_id == None)
        .order_by(Comment.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/events/{event_id}/comments", response_model=CommentPublic, status_code=201)
async def add_comment(
    event_id: str,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = Comment(
        id=str(uuid.uuid4()),
        content=payload.content,
        user_id=current_user.id,
        event_id=event_id,
        parent_id=payload.parent_id,
    )
    db.add(comment)
    await db.flush()

    result = await db.execute(
        select(Comment).options(selectinload(Comment.user)).where(Comment.id == comment.id)
    )
    return result.scalar_one()


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not the comment author")
    await db.delete(comment)


# ── Notifications ──────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=list[NotificationPublic])
async def get_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/notifications/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    return {"message": "All notifications marked as read"}


# ── Activity feed ──────────────────────────────────────────────────────────────

@router.get("/feed")
async def get_activity_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Shows recent activity from people the current user follows."""
    from app.models.event import Event, EventAttendee
    from sqlalchemy.orm import selectinload as sl

    # Get IDs of users being followed
    follows_q = await db.execute(
        select(Follow.following_id).where(Follow.follower_id == current_user.id)
    )
    following_ids = [row[0] for row in follows_q.fetchall()]
    following_ids.append(current_user.id)  # include self

    # Get recent attendances from followed users
    stmt = (
        select(EventAttendee)
        .options(sl(EventAttendee.user), sl(EventAttendee.event).selectinload(Event.host))
        .where(EventAttendee.user_id.in_(following_ids))
        .order_by(EventAttendee.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    attendances = result.scalars().all()

    feed = []
    for a in attendances:
        feed.append({
            "type": "attendance",
            "actor": {
                "id": a.user.id,
                "username": a.user.username,
                "full_name": a.user.full_name,
                "avatar_url": a.user.avatar_url,
                "is_verified": a.user.is_verified,
                "followers_count": a.user.followers_count,
            },
            "status": a.status,
            "event": {
                "id": a.event.id,
                "title": a.event.title,
                "slug": a.event.slug,
                "cover_image": a.event.cover_image,
                "city": a.event.city,
                "start_date": a.event.start_date,
            },
            "created_at": a.created_at,
        })

    return feed
