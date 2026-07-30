import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_organizer, get_current_user
from app.models.event import Event, EventAttendee
from app.models.organizer import (
    EventCoHost, EventTemplate, OrganizerProfile, TicketOrder, TicketTier,
)
from app.models.user import User
from app.schemas.organizer import (
    DashboardOut, OrganizerBecomeRequest, OrganizerProfileOut, OrganizerProfileUpdate,
    TemplateCreate, TemplateOut, TemplateUpdate, TicketOrderOut, VerificationRequest,
)
from app.schemas.user import UserMe
from app.services.email import send_refund_email
from app.services.tickets import notify_buyer, refund_order

router = APIRouter(prefix="/api/organizer", tags=["organizer"])


# ── Become an organizer ───────────────────────────────────────────────────────

@router.post("/become", response_model=UserMe)
async def become_organizer(
    payload: OrganizerBecomeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upgrade an existing account to organizer role."""
    if user.role == "organizer":
        raise HTTPException(400, "Already an organizer")

    user.role = "organizer"

    if not user.organizer_profile:
        db.add(OrganizerProfile(
            user_id=user.id,
            organization_name=payload.organization_name,
            organizer_bio=payload.organizer_bio,
            website=payload.website,
        ))
    else:
        if payload.organization_name is not None:
            user.organizer_profile.organization_name = payload.organization_name
        if payload.organizer_bio is not None:
            user.organizer_profile.organizer_bio = payload.organizer_bio
        if payload.website is not None:
            user.organizer_profile.website = payload.website

    await db.flush()
    await db.refresh(user)
    return user


# ── Organizer profile ─────────────────────────────────────────────────────────

@router.get("/profile", response_model=OrganizerProfileOut)
async def get_organizer_profile(user: User = Depends(get_current_organizer)):
    if not user.organizer_profile:
        raise HTTPException(404, "Organizer profile not found")
    return user.organizer_profile


@router.patch("/profile", response_model=OrganizerProfileOut)
async def update_organizer_profile(
    payload: OrganizerProfileUpdate,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    if not user.organizer_profile:
        raise HTTPException(404, "Organizer profile not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(user.organizer_profile, field, val)
    await db.flush()
    return user.organizer_profile


# ── Verification (self-serve application → admin review queue) ───────────────

@router.post("/verification/request", response_model=OrganizerProfileOut)
async def request_verification(
    payload: VerificationRequest,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    """Apply for the verified-organizer trust badge.

    Purely cosmetic once approved — does not change what the organizer can do;
    they still go through the normal event-review queue either way.
    """
    profile = user.organizer_profile
    if not profile:
        raise HTTPException(404, "Organizer profile not found")
    if profile.is_verified_organizer:
        raise HTTPException(400, "Already verified")
    if profile.verification_status == "pending":
        raise HTTPException(400, "A verification request is already pending review")

    profile.verification_status = "pending"
    profile.verification_note = payload.note
    profile.verification_requested_at = datetime.now(timezone.utc)
    profile.reviewed_by_id = None
    profile.reviewed_at = None
    await db.flush()
    return profile


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardOut)
async def organizer_dashboard(
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    # Count events by status
    events_result = await db.execute(
        select(Event.status, func.count(Event.id))
        .where(Event.host_id == user.id)
        .group_by(Event.status)
    )
    status_counts: dict[str, int] = dict(events_result.all())
    total_events = sum(status_counts.values())
    published = status_counts.get("published", 0)
    drafts = status_counts.get("draft", 0)

    # Total attendees across all published events
    att_result = await db.execute(
        select(func.sum(Event.attendees_count))
        .where(Event.host_id == user.id, Event.status == "published")
    )
    total_attendees = att_result.scalar() or 0

    # Revenue from confirmed ticket orders
    rev_result = await db.execute(
        select(func.sum(TicketOrder.total_price))
        .where(
            TicketOrder.event_id.in_(
                select(Event.id).where(Event.host_id == user.id)
            ),
            TicketOrder.status == "confirmed",
        )
    )
    total_revenue = float(rev_result.scalar() or 0)

    fee_result = await db.execute(
        select(func.sum(TicketOrder.platform_fee_amount))
        .where(
            TicketOrder.event_id.in_(
                select(Event.id).where(Event.host_id == user.id)
            ),
            TicketOrder.status == "confirmed",
        )
    )
    platform_fee_total = float(fee_result.scalar() or 0)

    # Pending co-host invites for the organizer's events
    pending_result = await db.execute(
        select(func.count(EventCoHost.id))
        .where(
            EventCoHost.event_id.in_(select(Event.id).where(Event.host_id == user.id)),
            EventCoHost.status == "invited",
        )
    )
    pending_cohosts = pending_result.scalar() or 0

    return DashboardOut(
        total_events=total_events,
        published_events=published,
        draft_events=drafts,
        total_attendees=total_attendees,
        total_revenue=total_revenue,
        platform_fee_total=platform_fee_total,
        net_revenue=total_revenue - platform_fee_total,
        pending_cohost_invites=pending_cohosts,
    )


# ── My events (incl. drafts) ──────────────────────────────────────────────────

@router.get("/events")
async def my_events(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    from app.models.event import Category
    stmt = (
        select(Event)
        .options(selectinload(Event.category))
        .where(Event.host_id == user.id)
        .order_by(Event.created_at.desc())
    )
    if status:
        stmt = stmt.where(Event.status == status)
    events = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    return [
        {
            "id": e.id, "title": e.title, "slug": e.slug, "status": e.status,
            "start_date": e.start_date, "city": e.city, "venue_name": e.venue_name,
            "attendees_count": e.attendees_count, "waitlist_count": e.waitlist_count,
            "views_count": e.views_count, "cover_image": e.cover_image,
            "category": e.category, "is_free": e.is_free,
            "price_min": e.price_min, "price_max": e.price_max,
            "created_at": e.created_at,
        }
        for e in events
    ]


# ── Co-host invitations received ──────────────────────────────────────────────

@router.get("/cohost-invites")
async def my_cohost_invites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EventCoHost)
        .options(selectinload(EventCoHost.event))
        .where(EventCoHost.user_id == user.id, EventCoHost.status == "invited")
        .order_by(EventCoHost.invited_at.desc())
    )
    invites = result.scalars().all()
    return [
        {
            "id": inv.id,
            "event_id": inv.event_id,
            "event_title": inv.event.title,
            "event_start": inv.event.start_date,
            "status": inv.status,
            "invited_at": inv.invited_at,
        }
        for inv in invites
    ]


# ── My ticket orders ──────────────────────────────────────────────────────────

@router.get("/my-tickets", response_model=list[TicketOrderOut])
async def my_ticket_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TicketOrder)
        .options(selectinload(TicketOrder.tier), selectinload(TicketOrder.event))
        .where(TicketOrder.user_id == user.id, TicketOrder.status != "cancelled")
        .order_by(TicketOrder.created_at.desc())
    )
    orders = result.scalars().all()
    return [
        TicketOrderOut(
            id=o.id, event_id=o.event_id, tier_id=o.tier_id,
            tier_name=o.tier.name, quantity=o.quantity,
            unit_price=o.unit_price, total_price=o.total_price,
            status=o.status, payment_reference=o.payment_reference,
            ticket_code=o.ticket_code,
            checked_in_at=o.checked_in_at,
            event_title=o.event.title if o.event else None,
            event_slug=o.event.slug if o.event else None,
            event_cover=o.event.cover_image if o.event else None,
            event_date=o.event.start_date if o.event else None,
            event_city=o.event.city if o.event else None,
            event_address=o.event.address if o.event else None,
            event_venue=o.event.venue_name if o.event else None,
            created_at=o.created_at,
        )
        for o in orders
    ]


# ── Single ticket order detail ────────────────────────────────────────────────

@router.get("/tickets/{order_id}", response_model=TicketOrderOut)
async def get_ticket_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TicketOrder)
        .options(selectinload(TicketOrder.tier), selectinload(TicketOrder.event))
        .where(TicketOrder.id == order_id, TicketOrder.user_id == user.id)
    )
    o = result.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Ticket not found")
    return TicketOrderOut(
        id=o.id, event_id=o.event_id, tier_id=o.tier_id,
        tier_name=o.tier.name, quantity=o.quantity,
        unit_price=o.unit_price, total_price=o.total_price,
        status=o.status, payment_reference=o.payment_reference,
        ticket_code=o.ticket_code,
        checked_in_at=o.checked_in_at,
        event_title=o.event.title if o.event else None,
        event_slug=o.event.slug if o.event else None,
        event_cover=o.event.cover_image if o.event else None,
        event_date=o.event.start_date if o.event else None,
        event_city=o.event.city if o.event else None,
        event_address=o.event.address if o.event else None,
        event_venue=o.event.venue_name if o.event else None,
        created_at=o.created_at,
    )


# ── All orders for organizer's events ─────────────────────────────────────────

@router.get("/orders")
async def organizer_orders(
    event_id: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    my_event_ids = (
        await db.execute(select(Event.id).where(Event.host_id == user.id))
    ).scalars().all()

    stmt = (
        select(TicketOrder)
        .options(selectinload(TicketOrder.tier), selectinload(TicketOrder.user))
        .where(TicketOrder.event_id.in_(my_event_ids))
        .order_by(TicketOrder.created_at.desc())
    )
    if event_id:
        if event_id not in my_event_ids:
            raise HTTPException(403, "Not your event")
        stmt = stmt.where(TicketOrder.event_id == event_id)

    orders = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    return [
        {
            "id": o.id, "event_id": o.event_id, "tier_id": o.tier_id,
            "tier_name": o.tier.name, "buyer_username": o.user.username,
            "buyer_email": o.user.email,
            "quantity": o.quantity, "unit_price": o.unit_price,
            "total_price": o.total_price, "platform_fee_amount": o.platform_fee_amount,
            "status": o.status,
            "created_at": o.created_at,
        }
        for o in orders
    ]


@router.post("/orders/{order_id}/refund", response_model=TicketOrderOut)
async def organizer_refund_order(
    order_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TicketOrder)
        .options(selectinload(TicketOrder.tier), selectinload(TicketOrder.event), selectinload(TicketOrder.user))
        .where(TicketOrder.id == order_id)
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if not order.event or order.event.host_id != user.id:
        raise HTTPException(403, "Not your event")
    if order.status != "confirmed":
        raise HTTPException(400, f"Cannot refund an order with status '{order.status}'")

    if not await refund_order(db, order):
        raise HTTPException(409, "Order was already resolved by another request")

    await notify_buyer(db, order, order.event, kind="refunded")
    background_tasks.add_task(
        send_refund_email, to=(order.user.email if order.user else "") or "",
        event_title=order.event.title, tier_name=order.tier.name if order.tier else "",
        quantity=order.quantity, total_price=order.total_price,
    )
    return TicketOrderOut(
        id=order.id, event_id=order.event_id, tier_id=order.tier_id,
        tier_name=order.tier.name if order.tier else "", quantity=order.quantity,
        unit_price=order.unit_price, total_price=order.total_price,
        status=order.status, payment_reference=order.payment_reference,
        ticket_code=order.ticket_code, checked_in_at=order.checked_in_at,
        created_at=order.created_at,
    )


# ── Templates ─────────────────────────────────────────────────────────────────

def _parse_template(t: EventTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        organizer_id=t.organizer_id,
        name=t.name,
        description=t.description,
        template_data=json.loads(t.template_data),
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    payload: TemplateCreate,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    t = EventTemplate(
        id=str(uuid.uuid4()),
        organizer_id=user.id,
        name=payload.name,
        description=payload.description,
        template_data=json.dumps(payload.template_data),
    )
    db.add(t)
    await db.flush()
    return _parse_template(t)


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EventTemplate)
        .where(EventTemplate.organizer_id == user.id)
        .order_by(EventTemplate.updated_at.desc())
    )
    return [_parse_template(t) for t in result.scalars().all()]


@router.get("/templates/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: str,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_own_template(template_id, user.id, db)
    return _parse_template(t)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_own_template(template_id, user.id, db)
    if payload.name is not None:
        t.name = payload.name
    if payload.description is not None:
        t.description = payload.description
    if payload.template_data is not None:
        t.template_data = json.dumps(payload.template_data)
    await db.flush()
    return _parse_template(t)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    user: User = Depends(get_current_organizer),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_own_template(template_id, user.id, db)
    await db.delete(t)


async def _get_own_template(template_id: str, organizer_id: str, db: AsyncSession) -> EventTemplate:
    result = await db.execute(
        select(EventTemplate).where(
            EventTemplate.id == template_id,
            EventTemplate.organizer_id == organizer_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Template not found")
    return t
