import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.event import Category, Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.user import User
from app.schemas.admin import (
    AdminCategoryCreate, AdminCategoryOut, AdminCategoryUpdate,
    AdminEventOut, AdminEventUpdate,
    AdminOrderOut,
    AdminUserOut, AdminUserUpdate,
    PlatformStats,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=PlatformStats)
async def platform_stats(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_users = (await db.execute(select(func.count(User.id)).where(User.is_deleted == False))).scalar_one()
    total_organizers = (await db.execute(select(func.count(User.id)).where(User.role == "organizer", User.is_deleted == False))).scalar_one()
    total_events = (await db.execute(select(func.count(Event.id)))).scalar_one()
    published_events = (await db.execute(select(func.count(Event.id)).where(Event.status == "published"))).scalar_one()
    total_orders = (await db.execute(select(func.count(TicketOrder.id)))).scalar_one()
    confirmed_revenue_row = (await db.execute(
        select(func.coalesce(func.sum(TicketOrder.total_price), 0.0)).where(TicketOrder.status == "confirmed")
    )).scalar_one()
    total_attendees = (await db.execute(select(func.sum(Event.attendees_count)))).scalar_one() or 0
    new_users = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= week_ago, User.is_deleted == False)
    )).scalar_one()
    new_events = (await db.execute(
        select(func.count(Event.id)).where(Event.created_at >= week_ago)
    )).scalar_one()

    return PlatformStats(
        total_users=total_users,
        total_organizers=total_organizers,
        total_events=total_events,
        published_events=published_events,
        total_orders=total_orders,
        confirmed_revenue=float(confirmed_revenue_row),
        total_attendees=total_attendees,
        new_users_this_week=new_users,
        new_events_this_week=new_events,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    q: str | None = Query(None),
    role: str | None = Query(None),
    active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.is_deleted == False)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like), User.full_name.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active == active)
    stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted == False))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "Cannot modify your own account via admin panel")
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_verified is not None:
        user.is_verified = body.is_verified
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/events", response_model=list[AdminEventOut])
async def list_all_events(
    q: str | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    stmt = select(Event).options(selectinload(Event.host))
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Event.status == status)
    stmt = stmt.order_by(Event.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()
    out = []
    for ev in events:
        out.append(AdminEventOut(
            id=ev.id,
            title=ev.title,
            slug=ev.slug,
            status=ev.status,
            is_featured=ev.is_featured,
            is_trending=ev.is_trending,
            event_type=ev.event_type,
            city=ev.city,
            country=ev.country,
            start_date=ev.start_date,
            attendees_count=ev.attendees_count,
            views_count=ev.views_count,
            host_username=ev.host.username,
            host_id=ev.host_id,
            created_at=ev.created_at,
        ))
    return out


@router.patch("/events/{event_id}", response_model=AdminEventOut)
async def update_event(
    event_id: str,
    body: AdminEventUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(Event).options(selectinload(Event.host)).where(Event.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event not found")
    if body.is_featured is not None:
        ev.is_featured = body.is_featured
    if body.is_trending is not None:
        ev.is_trending = body.is_trending
    if body.status is not None:
        ev.status = body.status
    await db.flush()
    await db.refresh(ev)
    return AdminEventOut(
        id=ev.id, title=ev.title, slug=ev.slug, status=ev.status,
        is_featured=ev.is_featured, is_trending=ev.is_trending,
        event_type=ev.event_type, city=ev.city, country=ev.country,
        start_date=ev.start_date, attendees_count=ev.attendees_count,
        views_count=ev.views_count, host_username=ev.host.username,
        host_id=ev.host_id, created_at=ev.created_at,
    )


@router.get("/categories", response_model=list[AdminCategoryOut])
async def list_categories(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


@router.post("/categories", response_model=AdminCategoryOut, status_code=201)
async def create_category(
    body: AdminCategoryCreate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = Category(
        id=str(uuid.uuid4()),
        name=body.name,
        slug=body.slug,
        icon=body.icon,
        color=body.color,
        description=body.description,
    )
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return cat


@router.patch("/categories/{cat_id}", response_model=AdminCategoryOut)
async def update_category(
    cat_id: str,
    body: AdminCategoryUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(cat, field, val)
    await db.flush()
    await db.refresh(cat)
    return cat


@router.delete("/categories/{cat_id}", status_code=204)
async def delete_category(
    cat_id: str,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")
    await db.delete(cat)


@router.get("/orders", response_model=list[AdminOrderOut])
async def list_all_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    stmt = (
        select(TicketOrder)
        .options(
            selectinload(TicketOrder.user),
            selectinload(TicketOrder.event),
            selectinload(TicketOrder.tier),
        )
        .order_by(TicketOrder.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    orders = result.scalars().all()
    out = []
    for o in orders:
        out.append(AdminOrderOut(
            id=o.id,
            event_id=o.event_id,
            event_title=o.event.title if o.event else "—",
            tier_name=o.tier.name if o.tier else "—",
            buyer_username=o.user.username if o.user else "—",
            buyer_email=o.user.email if o.user else None,
            quantity=o.quantity,
            unit_price=o.unit_price,
            total_price=o.total_price,
            currency=o.tier.currency if o.tier else "NGN",
            status=o.status,
            created_at=o.created_at,
        ))
    return out
