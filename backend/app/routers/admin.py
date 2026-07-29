import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_admin, get_current_moderator
from app.models.event import Category, Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.scout import ScoutedItem, ScoutSource
from app.models.social import Notification
from app.models.user import User
from app.schemas.admin import (
    AdminCategoryCreate, AdminCategoryOut, AdminCategoryUpdate,
    AdminEventOut, AdminEventReject, AdminEventUpdate,
    AdminOrderOut,
    AdminUserOut, AdminUserUpdate,
    AIEventDraft,
    PlatformStats,
    ScoutedItemOut, ScoutRunResult, ScoutSourceCreate, ScoutSourceOut, ScoutSourceUpdate,
)
from app.services.ai_agent import AIAgentError, draft_event
from app.services.scout_agent import run_daily_scout

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


def _admin_event_out(ev: Event) -> AdminEventOut:
    return AdminEventOut(
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
        review_status=ev.review_status,
        review_note=ev.review_note,
        created_via=ev.created_via,
        reviewed_by_username=ev.reviewed_by.username if ev.reviewed_by else None,
        reviewed_at=ev.reviewed_at,
    )


@router.get("/events", response_model=list[AdminEventOut])
async def list_all_events(
    q: str | None = Query(None),
    status: str | None = Query(None),
    review_status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    stmt = select(Event).options(selectinload(Event.host), selectinload(Event.reviewed_by))
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Event.status == status)
    if review_status:
        stmt = stmt.where(Event.review_status == review_status)
    stmt = stmt.order_by(Event.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [_admin_event_out(ev) for ev in events]


@router.patch("/events/{event_id}", response_model=AdminEventOut)
async def update_event(
    event_id: str,
    body: AdminEventUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Event).options(selectinload(Event.host), selectinload(Event.reviewed_by))
        .where(Event.id == event_id)
    )
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
    return _admin_event_out(ev)


@router.post("/events/{event_id}/approve", response_model=AdminEventOut)
async def approve_event(
    event_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Event).options(selectinload(Event.host), selectinload(Event.reviewed_by))
        .where(Event.id == event_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.review_status == "approved":
        raise HTTPException(400, "Event is already approved")

    ev.review_status = "approved"
    ev.review_note = None
    ev.reviewed_by_id = admin.id
    ev.reviewed_at = datetime.now(timezone.utc)
    ev.status = "published"

    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=ev.host_id,
        type="event_approved",
        title=f"Event approved: {ev.title}",
        body=f'"{ev.title}" was approved and is now live.',
        reference_id=ev.id,
        reference_type="event",
        actor_id=admin.id,
    ))
    await db.flush()
    await db.refresh(ev)
    await db.execute(update(User).where(User.id == ev.host_id).values(
        events_hosted=User.events_hosted + 1))
    return _admin_event_out(ev)


@router.post("/events/{event_id}/reject", response_model=AdminEventOut)
async def reject_event(
    event_id: str,
    body: AdminEventReject,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Event).options(selectinload(Event.host), selectinload(Event.reviewed_by))
        .where(Event.id == event_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event not found")

    ev.review_status = "rejected"
    ev.review_note = body.note
    ev.reviewed_by_id = admin.id
    ev.reviewed_at = datetime.now(timezone.utc)
    ev.status = "draft"

    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=ev.host_id,
        type="event_rejected",
        title=f"Event needs changes: {ev.title}",
        body=body.note,
        reference_id=ev.id,
        reference_type="event",
        actor_id=admin.id,
    ))
    await db.flush()
    await db.refresh(ev)
    return _admin_event_out(ev)


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


@router.post("/events/draft", response_model=AIEventDraft)
async def ai_draft_event(
    text: str | None = Form(None),
    url: str | None = Form(None),
    image: UploadFile | None = File(None),
    _: User = Depends(get_current_moderator),
    db: AsyncSession = Depends(get_db),
):
    """Draft structured event fields from a pasted description, a URL, and/or a flyer image.

    Moderator/admin only. Returns a suggestion for the caller to review and edit — nothing
    is created here.
    """
    image_bytes = None
    image_media_type = None
    if image is not None:
        image_bytes = await image.read()
        image_media_type = image.content_type or "image/jpeg"

    categories = (await db.execute(select(Category.name).order_by(Category.name))).scalars().all()

    try:
        result = await draft_event(
            text=text,
            url=url,
            image_bytes=image_bytes,
            image_media_type=image_media_type,
            category_names=list(categories),
        )
    except AIAgentError as e:
        raise HTTPException(422, str(e))

    return AIEventDraft(**result)


# ── Daily scout agent: RSS sources, run log, manual trigger ────────────────────

@router.get("/scout/sources", response_model=list[ScoutSourceOut])
async def list_scout_sources(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScoutSource).order_by(ScoutSource.created_at.desc()))
    return result.scalars().all()


@router.post("/scout/sources", response_model=ScoutSourceOut, status_code=201)
async def create_scout_source(
    body: ScoutSourceCreate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    source = ScoutSource(id=str(uuid.uuid4()), name=body.name, url=body.url)
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return source


@router.patch("/scout/sources/{source_id}", response_model=ScoutSourceOut)
async def update_scout_source(
    source_id: str,
    body: ScoutSourceUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    source = (await db.execute(select(ScoutSource).where(ScoutSource.id == source_id))).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(source, field, val)
    await db.flush()
    await db.refresh(source)
    return source


@router.delete("/scout/sources/{source_id}", status_code=204)
async def delete_scout_source(
    source_id: str,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    source = (await db.execute(select(ScoutSource).where(ScoutSource.id == source_id))).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")
    await db.delete(source)


@router.get("/scout/log", response_model=list[ScoutedItemOut])
async def list_scout_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    stmt = (
        select(ScoutedItem)
        .options(selectinload(ScoutedItem.source), selectinload(ScoutedItem.event))
        .order_by(ScoutedItem.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return [
        ScoutedItemOut(
            id=i.id, source_id=i.source_id, source_name=i.source.name if i.source else "—",
            url=i.url, status=i.status, event_id=i.event_id,
            event_title=i.event.title if i.event else None,
            error_note=i.error_note, created_at=i.created_at,
        )
        for i in items
    ]


@router.post("/scout/run-now", response_model=ScoutRunResult)
async def run_scout_now(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        summary = await run_daily_scout(db)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return ScoutRunResult(
        sources_polled=summary.sources_polled,
        items_seen=summary.items_seen,
        events_created=summary.events_created,
        skipped_duplicate=summary.skipped_duplicate,
        skipped_no_event=summary.skipped_no_event,
        failed=summary.failed,
    )
