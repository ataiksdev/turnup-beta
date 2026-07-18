import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.community import Community, CommunityEvent, CommunityMember
from app.models.event import Event
from app.models.social import Notification
from app.models.user import User
from app.schemas.community import (
    CommunityCreate, CommunityOut, CommunityUpdate, ShareEventRequest,
)

router = APIRouter(prefix="/api/communities", tags=["communities"])


def _slugify(name: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _load_community():
    return [
        selectinload(Community.creator),
        selectinload(Community.category),
        selectinload(Community.members).selectinload(CommunityMember.user),
    ]


def _serialize(
    community: Community,
    me: User | None = None,
    my_membership: CommunityMember | None = None,
) -> dict:
    links = community.social_links_dict
    is_admin = my_membership and my_membership.role == "admin"
    return {
        "id": community.id,
        "name": community.name,
        "slug": community.slug,
        "description": community.description,
        "cover_image": community.cover_image,
        "icon": community.icon,
        "city": community.city,
        "is_private": community.is_private,
        "social_links": links,
        "member_count": community.member_count,
        "event_count": community.event_count,
        "creator": community.creator,
        "category": community.category,
        "created_at": community.created_at,
        "is_member": my_membership is not None,
        "member_role": my_membership.role if my_membership else None,
        "is_verified_community": community.creator.role == "organizer",
        "invite_token": community.invite_token if (community.is_private and is_admin) else None,
    }


async def _get_membership(db: AsyncSession, community_id: str, user_id: str) -> CommunityMember | None:
    return (await db.execute(
        select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
    )).scalar_one_or_none()


async def _require_community(db: AsyncSession, slug: str) -> Community:
    stmt = select(Community).options(*_load_community()).where(Community.slug == slug)
    c = (await db.execute(stmt)).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Community not found")
    return c


async def _notify(db: AsyncSession, user_id: str, actor_id: str, notif_type: str,
                  title: str, body: str | None = None,
                  reference_id: str | None = None, reference_type: str | None = None):
    if user_id == actor_id:
        return
    db.add(Notification(
        id=str(uuid.uuid4()), user_id=user_id, actor_id=actor_id,
        type=notif_type, title=title, body=body,
        reference_id=reference_id, reference_type=reference_type,
    ))


# ── Browse ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CommunityOut])
async def list_communities(
    q: str | None = None,
    category: str | None = None,
    city: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    stmt = select(Community).options(*_load_community()).where(Community.is_private == False)
    if q:
        stmt = stmt.where(Community.name.ilike(f"%{q}%"))
    if city:
        stmt = stmt.where(Community.city.ilike(f"%{city}%"))
    if category:
        from app.models.event import Category
        cat = (await db.execute(
            select(Category).where(Category.slug == category)
        )).scalar_one_or_none()
        if cat:
            stmt = stmt.where(Community.category_id == cat.id)
    stmt = stmt.order_by(Community.member_count.desc()).offset((page - 1) * limit).limit(limit)
    communities = (await db.execute(stmt)).scalars().all()

    result = []
    for c in communities:
        membership = await _get_membership(db, c.id, me.id) if me else None
        result.append(_serialize(c, me, membership))
    return result


@router.get("/my", response_model=list[CommunityOut])
async def my_communities(
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    stmt = (
        select(Community)
        .options(*_load_community())
        .join(CommunityMember, CommunityMember.community_id == Community.id)
        .where(CommunityMember.user_id == me.id)
        .order_by(CommunityMember.joined_at.desc())
    )
    communities = (await db.execute(stmt)).scalars().all()
    result = []
    for c in communities:
        membership = await _get_membership(db, c.id, me.id)
        result.append(_serialize(c, me, membership))
    return result


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=CommunityOut, status_code=201)
async def create_community(
    payload: CommunityCreate,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    cid = str(uuid.uuid4())
    slug = _slugify(payload.name, cid)

    # Generate invite token for private communities
    invite_token = str(uuid.uuid4()) if payload.is_private else None

    community = Community(
        id=cid,
        name=payload.name,
        slug=slug,
        description=payload.description,
        cover_image=payload.cover_image,
        icon=payload.icon,
        category_id=payload.category_id,
        city=payload.city,
        is_private=payload.is_private,
        invite_token=invite_token,
        social_links=json.dumps(payload.social_links.model_dump(exclude_none=True)),
        member_count=1,
        event_count=0,
        creator_id=me.id,
    )
    db.add(community)
    await db.flush()

    # Add creator as admin member
    db.add(CommunityMember(
        community_id=community.id,
        user_id=me.id,
        role="admin",
    ))
    await db.commit()

    # Reload with relationships
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    return _serialize(community, me, membership)


# ── Detail ─────────────────────────────────────────────────────────────────────

@router.get("/{slug}", response_model=CommunityOut)
async def get_community(
    slug: str,
    db: AsyncSession = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id) if me else None
    # Private communities: only members (and the public slug exists but contents hidden)
    if community.is_private and not membership:
        # Return minimal info only
        return {
            **_serialize(community, me, None),
            "description": None,
            "social_links": {},
        }
    return _serialize(community, me, membership)


@router.patch("/{slug}", response_model=CommunityOut)
async def update_community(
    slug: str,
    payload: CommunityUpdate,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership or membership.role != "admin":
        raise HTTPException(403, "Only community admins can edit this community")

    if payload.name is not None:
        community.name = payload.name
    if payload.description is not None:
        community.description = payload.description
    if payload.cover_image is not None:
        community.cover_image = payload.cover_image
    if payload.icon is not None:
        community.icon = payload.icon
    if payload.category_id is not None:
        community.category_id = payload.category_id
    if payload.city is not None:
        community.city = payload.city
    if payload.is_private is not None:
        if payload.is_private and not community.invite_token:
            community.invite_token = str(uuid.uuid4())
        community.is_private = payload.is_private
    if payload.social_links is not None:
        community.social_links = json.dumps(payload.social_links.model_dump(exclude_none=True))

    await db.commit()
    await db.refresh(community)
    community = await _require_community(db, community.slug)
    return _serialize(community, me, membership)


@router.delete("/{slug}", status_code=204)
async def delete_community(
    slug: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership or membership.role != "admin":
        raise HTTPException(403, "Only community admins can delete this community")
    await db.delete(community)
    await db.commit()


# ── Invite token (private communities) ────────────────────────────────────────

@router.post("/{slug}/regenerate-invite", response_model=CommunityOut)
async def regenerate_invite(
    slug: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership or membership.role != "admin":
        raise HTTPException(403, "Only admins can regenerate the invite link")
    if not community.is_private:
        raise HTTPException(400, "Community is not private")
    community.invite_token = str(uuid.uuid4())
    await db.commit()
    community = await _require_community(db, slug)
    return _serialize(community, me, membership)


@router.post("/join-invite/{invite_token}", response_model=CommunityOut)
async def join_via_invite(
    invite_token: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = (await db.execute(
        select(Community).options(*_load_community()).where(Community.invite_token == invite_token)
    )).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Invalid or expired invite link")

    existing = await _get_membership(db, community.id, me.id)
    if existing:
        return _serialize(community, me, existing)

    member = CommunityMember(community_id=community.id, user_id=me.id, role="member")
    db.add(member)
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            member_count=Community.member_count + 1
        )
    )
    await _notify(db, community.creator_id, me.id, "community_join",
                  f"{me.full_name or me.username} joined {community.name}",
                  reference_id=community.id, reference_type="community")
    await db.commit()
    community = await _require_community(db, community.slug)
    membership = await _get_membership(db, community.id, me.id)
    return _serialize(community, me, membership)


# ── Membership ─────────────────────────────────────────────────────────────────

@router.post("/{slug}/join", response_model=CommunityOut)
async def join_community(
    slug: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    if community.is_private:
        raise HTTPException(403, "This community is private. Use an invite link to join.")

    existing = await _get_membership(db, community.id, me.id)
    if existing:
        return _serialize(community, me, existing)

    member = CommunityMember(community_id=community.id, user_id=me.id, role="member")
    db.add(member)
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            member_count=Community.member_count + 1
        )
    )
    await _notify(db, community.creator_id, me.id, "community_join",
                  f"{me.full_name or me.username} joined {community.name}",
                  reference_id=community.id, reference_type="community")
    await db.commit()
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    return _serialize(community, me, membership)


@router.delete("/{slug}/leave", status_code=204)
async def leave_community(
    slug: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership:
        raise HTTPException(400, "You are not a member of this community")
    if membership.role == "admin":
        # Check if there are other admins
        other_admin = (await db.execute(
            select(CommunityMember).where(
                CommunityMember.community_id == community.id,
                CommunityMember.user_id != me.id,
                CommunityMember.role == "admin",
            )
        )).scalar_one_or_none()
        if not other_admin:
            raise HTTPException(400, "Transfer admin role before leaving, or delete the community.")
    await db.delete(membership)
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            member_count=func.greatest(Community.member_count - 1, 0)
        )
    )
    await db.commit()


@router.get("/{slug}/members")
async def list_members(
    slug: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id) if me else None
    if community.is_private and not membership:
        raise HTTPException(403, "Members list is private")

    stmt = (
        select(CommunityMember, User)
        .join(User, User.id == CommunityMember.user_id)
        .where(CommunityMember.community_id == community.id)
        .order_by(CommunityMember.joined_at.asc())
        .offset((page - 1) * limit).limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": row.User.id,
            "username": row.User.username,
            "full_name": row.User.full_name,
            "display_name": row.User.display_name,
            "avatar_url": row.User.avatar_url,
            "is_verified": row.User.is_verified,
            "role": row.CommunityMember.role,
            "joined_at": row.CommunityMember.joined_at,
        }
        for row in rows
    ]


@router.patch("/{slug}/members/{user_id}")
async def update_member_role(
    slug: str,
    user_id: str,
    role: str = Query(pattern="^(member|moderator|admin)$"),
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    my_membership = await _get_membership(db, community.id, me.id)
    if not my_membership or my_membership.role not in ("admin", "moderator"):
        raise HTTPException(403, "Only admins and moderators can change roles")
    target = await _get_membership(db, community.id, user_id)
    if not target:
        raise HTTPException(404, "User is not a member")
    target.role = role
    await db.commit()
    return {"ok": True, "role": role}


@router.delete("/{slug}/members/{user_id}", status_code=204)
async def remove_member(
    slug: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    my_membership = await _get_membership(db, community.id, me.id)
    if not my_membership or my_membership.role not in ("admin", "moderator"):
        raise HTTPException(403, "Only admins and moderators can remove members")
    target = await _get_membership(db, community.id, user_id)
    if not target:
        raise HTTPException(404, "User is not a member")
    await db.delete(target)
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            member_count=func.greatest(Community.member_count - 1, 0)
        )
    )
    await db.commit()


# ── Events ─────────────────────────────────────────────────────────────────────

@router.get("/{slug}/events")
async def list_community_events(
    slug: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id) if me else None
    if community.is_private and not membership:
        raise HTTPException(403, "Events are private")

    from app.models.event import Category
    from sqlalchemy.orm import selectinload as sl
    stmt = (
        select(Event)
        .options(sl(Event.host), sl(Event.category))
        .join(CommunityEvent, CommunityEvent.event_id == Event.id)
        .where(CommunityEvent.community_id == community.id, Event.status == "published")
        .order_by(CommunityEvent.created_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    events = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": e.id, "title": e.title, "slug": e.slug,
            "cover_image": e.cover_image, "city": e.city,
            "start_date": e.start_date, "end_date": e.end_date,
            "is_free": e.is_free, "price_min": e.price_min, "price_max": e.price_max,
            "currency": e.currency, "attendees_count": e.attendees_count,
            "is_trending": e.is_trending, "is_featured": e.is_featured,
            "tags": e.tags, "host": {
                "id": e.host.id, "username": e.host.username, "full_name": e.host.full_name,
                "avatar_url": e.host.avatar_url, "is_verified": e.host.is_verified, "role": e.host.role,
                "followers_count": e.host.followers_count,
            },
            "category": {"id": e.category.id, "name": e.category.name, "slug": e.category.slug,
                         "icon": e.category.icon, "color": e.category.color} if e.category else None,
        }
        for e in events
    ]


@router.post("/{slug}/events", status_code=201)
async def share_event(
    slug: str,
    payload: ShareEventRequest,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership:
        raise HTTPException(403, "Only members can share events in this community")

    event = (await db.execute(
        select(Event).where(Event.id == payload.event_id, Event.status == "published")
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found or not published")

    existing = (await db.execute(
        select(CommunityEvent).where(
            CommunityEvent.community_id == community.id,
            CommunityEvent.event_id == payload.event_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Event already shared in this community")

    db.add(CommunityEvent(
        community_id=community.id,
        event_id=payload.event_id,
        shared_by=me.id,
    ))
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            event_count=Community.event_count + 1
        )
    )

    # Notify all members (cap at 200 to avoid spam)
    member_ids = (await db.execute(
        select(CommunityMember.user_id)
        .where(CommunityMember.community_id == community.id, CommunityMember.user_id != me.id)
        .limit(200)
    )).scalars().all()
    for uid in member_ids:
        await _notify(db, uid, me.id, "community_event",
                      f"New event in {community.name}",
                      body=event.title,
                      reference_id=community.id, reference_type="community")

    await db.commit()
    return {"ok": True}


@router.delete("/{slug}/events/{event_id}", status_code=204)
async def remove_event(
    slug: str,
    event_id: str,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
):
    community = await _require_community(db, slug)
    membership = await _get_membership(db, community.id, me.id)
    if not membership:
        raise HTTPException(403, "Not a member")

    ce = (await db.execute(
        select(CommunityEvent).where(
            CommunityEvent.community_id == community.id,
            CommunityEvent.event_id == event_id,
        )
    )).scalar_one_or_none()
    if not ce:
        raise HTTPException(404, "Event not in this community")

    # Only sharer or admin/moderator can remove
    if ce.shared_by != me.id and membership.role not in ("admin", "moderator"):
        raise HTTPException(403, "Only the person who shared or an admin can remove this event")

    await db.delete(ce)
    await db.execute(
        update(Community).where(Community.id == community.id).values(
            event_count=func.greatest(Community.event_count - 1, 0)
        )
    )
    await db.commit()
