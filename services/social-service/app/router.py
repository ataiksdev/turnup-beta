import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Comment, Follow, Notification

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _get_uid(token: str | None = Depends(oauth2)) -> str:
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])["sub"]
    except (JWTError, KeyError):
        raise HTTPException(401, "Invalid token")


def _get_optional_uid(token: str | None = Depends(oauth2)) -> str | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm]).get("sub")
    except JWTError:
        return None


async def _get_user(user_id: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.auth_service_url}/internal/users/{user_id}", timeout=5)
        if r.status_code != 200:
            raise HTTPException(404, "User not found")
        return r.json()


async def _get_user_by_username(username: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{settings.auth_service_url}/internal/users/by-username/{username}", timeout=5)
        if r.status_code != 200:
            raise HTTPException(404, "User not found")
        return r.json()


async def _inc_user(user_id: str, field: str, amount: int = 1):
    async with httpx.AsyncClient() as c:
        await c.post(f"{settings.auth_service_url}/internal/users/{user_id}/increment",
                     params={"field": field, "amount": amount}, timeout=5)


# ── Follow ───────────────────────────────────────────────────────────────────────

@router.post("/social/follow/{username}")
async def follow_user(username: str, db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    target = await _get_user_by_username(username)
    if target["id"] == uid:
        raise HTTPException(400, "Cannot follow yourself")

    existing = (await db.execute(select(Follow).where(
        Follow.follower_id == uid, Follow.following_id == target["id"]))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Already following")

    db.add(Follow(id=str(uuid.uuid4()), follower_id=uid, following_id=target["id"]))

    me = await _get_user(uid)
    db.add(Notification(
        id=str(uuid.uuid4()), user_id=target["id"], type="follow",
        title=f"{me['full_name']} started following you",
        actor_id=uid, actor_username=me["username"], actor_avatar_url=me.get("avatar_url"),
        reference_id=uid, reference_type="user",
    ))

    await db.flush()
    await _inc_user(uid, "following_count", 1)
    await _inc_user(target["id"], "followers_count", 1)
    return {"following": True}


@router.delete("/social/follow/{username}")
async def unfollow_user(username: str, db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    target = await _get_user_by_username(username)
    follow = (await db.execute(select(Follow).where(
        Follow.follower_id == uid, Follow.following_id == target["id"]))).scalar_one_or_none()
    if not follow:
        raise HTTPException(404, "Not following")
    await db.delete(follow)
    await db.flush()
    await _inc_user(uid, "following_count", -1)
    await _inc_user(target["id"], "followers_count", -1)
    return {"following": False}


# ── Comments ──────────────────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: str | None = None


@router.get("/social/events/{event_id}/comments")
async def get_comments(event_id: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                        db: AsyncSession = Depends(get_db)):
    stmt = (select(Comment).where(Comment.event_id == event_id, Comment.parent_id == None)
            .order_by(Comment.created_at.asc()).offset((page-1)*limit).limit(limit))
    comments = (await db.execute(stmt)).scalars().all()
    return [
        {"id": c.id, "content": c.content, "event_id": c.event_id, "parent_id": c.parent_id,
         "created_at": c.created_at, "updated_at": c.updated_at,
         "user": {"id": c.user_id, "username": c.user_username, "full_name": c.user_full_name,
                  "avatar_url": c.user_avatar_url, "is_verified": c.user_is_verified, "followers_count": 0}}
        for c in comments
    ]


@router.post("/social/events/{event_id}/comments", status_code=201)
async def add_comment(event_id: str, payload: CommentCreate,
                       db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    me = await _get_user(uid)
    c = Comment(
        id=str(uuid.uuid4()), content=payload.content,
        user_id=uid, user_username=me["username"], user_full_name=me["full_name"],
        user_avatar_url=me.get("avatar_url"), user_is_verified=me.get("is_verified", False),
        event_id=event_id, parent_id=payload.parent_id,
    )
    db.add(c)
    await db.flush()
    return {"id": c.id, "content": c.content, "event_id": c.event_id, "parent_id": c.parent_id,
            "created_at": c.created_at, "updated_at": c.updated_at,
            "user": {"id": uid, "username": me["username"], "full_name": me["full_name"],
                     "avatar_url": me.get("avatar_url"), "is_verified": me.get("is_verified", False), "followers_count": 0}}


@router.delete("/social/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    c = (await db.execute(select(Comment).where(Comment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.user_id != uid:
        raise HTTPException(403, "Not the author")
    await db.delete(c)


# ── Notifications ─────────────────────────────────────────────────────────────────

@router.get("/social/notifications")
async def get_notifications(unread_only: bool = False, page: int = Query(1, ge=1),
                             limit: int = Query(30, ge=1, le=50), db: AsyncSession = Depends(get_db),
                             uid: str = Depends(_get_uid)):
    stmt = (select(Notification).where(Notification.user_id == uid)
            .order_by(Notification.created_at.desc()).offset((page-1)*limit).limit(limit))
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": n.id, "type": n.type, "title": n.title, "body": n.body,
         "reference_id": n.reference_id, "reference_type": n.reference_type,
         "is_read": n.is_read, "created_at": n.created_at,
         "actor": {"id": n.actor_id, "username": n.actor_username,
                   "avatar_url": n.actor_avatar_url} if n.actor_id else None}
        for n in rows
    ]


@router.post("/social/notifications/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    await db.execute(update(Notification).where(
        Notification.user_id == uid, Notification.is_read == False).values(is_read=True))
    return {"ok": True}


# ── Activity feed ─────────────────────────────────────────────────────────────────

@router.get("/social/feed")
async def activity_feed(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                         db: AsyncSession = Depends(get_db), uid: str = Depends(_get_uid)):
    follows_q = await db.execute(select(Follow.following_id).where(Follow.follower_id == uid))
    following_ids = [r[0] for r in follows_q.fetchall()] + [uid]

    # Recent follows from people you follow
    stmt = (select(Follow).where(Follow.follower_id.in_(following_ids))
            .order_by(Follow.created_at.desc()).offset((page-1)*limit).limit(limit))
    follows = (await db.execute(stmt)).scalars().all()

    feed = []
    for f in follows:
        actor = await _get_user(f.follower_id)
        target = await _get_user(f.following_id)
        feed.append({
            "type": "follow",
            "actor": {"id": actor["id"], "username": actor["username"],
                      "full_name": actor["full_name"], "avatar_url": actor.get("avatar_url"),
                      "is_verified": actor.get("is_verified", False), "followers_count": actor.get("followers_count", 0)},
            "target_user": {"id": target["id"], "username": target["username"],
                            "full_name": target["full_name"], "avatar_url": target.get("avatar_url"),
                            "is_verified": target.get("is_verified", False), "followers_count": target.get("followers_count", 0)},
            "created_at": f.created_at,
        })

    return sorted(feed, key=lambda x: x["created_at"], reverse=True)


# ── Internal endpoints (used by users-service) ────────────────────────────────────

@router.get("/internal/follows/{follower_id}/{following_id}")
async def check_follow(follower_id: str, following_id: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(Follow).where(
        Follow.follower_id == follower_id, Follow.following_id == following_id))).scalar_one_or_none()
    return {"is_following": r is not None}


@router.get("/internal/followers/{user_id}")
async def get_followers_internal(user_id: str, page: int = 1, limit: int = 20,
                                  db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Follow.follower_id).where(Follow.following_id == user_id)
                             .offset((page-1)*limit).limit(limit))).fetchall()
    users = []
    for (fid,) in rows:
        try:
            users.append(await _get_user(fid))
        except Exception:
            pass
    return users


@router.get("/internal/following/{user_id}")
async def get_following_internal(user_id: str, page: int = 1, limit: int = 20,
                                  db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Follow.following_id).where(Follow.follower_id == user_id)
                             .offset((page-1)*limit).limit(limit))).fetchall()
    users = []
    for (fid,) in rows:
        try:
            users.append(await _get_user(fid))
        except Exception:
            pass
    return users
