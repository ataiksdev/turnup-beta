"""Turnup+ for attendees (docs/venues-spec.md 4.8): membership, deals, ticket transfers,
weekend picks and Turnup Wrapped. Organizer-side deal management for events lives here too."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import limiter
from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.user import User
from app.models.venue import Deal, DealRedemption, Subscription, SubscriptionPlan, TicketTransfer
from app.schemas.venue import DealIn, RedeemIn, SubscribeIn
from app.services import deals as deal_svc
from app.services.plus import cancel_subscription, is_plus, start_subscription
from app.services.venue_access import notify

router = APIRouter(tags=["turnup+"])

PERKS = [
    {"id": "presale", "title": "Presale", "body": "Buy before everyone else when organizers and venues open a members' presale."},
    {"id": "waitlist", "title": "Priority waitlist", "body": "When a sold-out event frees a spot, members are offered it first."},
    {"id": "early_alerts", "title": "Early alerts", "body": "Hear about new events from venues and organizers you follow straight away."},
    {"id": "members_only", "title": "Members-only events and guest lists", "body": "Get into events and guest lists only members can join."},
    {"id": "fast_lane", "title": "Fast lane", "body": "Use the separate entry queue at events that offer one."},
    {"id": "deals", "title": "Member deals", "body": "Free entry, discounts, drinks and reserved tables from venues and organizers."},
    {"id": "transfer", "title": "Free ticket transfer", "body": "Send a ticket to a friend if you can't go."},
    {"id": "weekend", "title": "Weekend picks", "body": "A personal list of events for your weekend, every Thursday."},
    {"id": "badge", "title": "Plus badge", "body": "Show you're a member on your profile, comments and reviews."},
    {"id": "wrapped", "title": "Full Turnup Wrapped", "body": "Your whole year of going out, made to share."},
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Membership ─────────────────────────────────────────────────────────────────

@router.get("/api/plus/plans")
async def plus_plans(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SubscriptionPlan).where(
        SubscriptionPlan.product == "turnup_plus", SubscriptionPlan.is_active == True))).scalars().all()  # noqa: E712
    return {"perks": PERKS, "plans": [{"code": p.code, "name": p.name, "amount_kobo": p.amount_kobo,
                                       "interval": p.interval} for p in rows]}


@router.get("/api/plus/me")
async def plus_me(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    sub = (await db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.product == "turnup_plus",
        Subscription.status.in_(["active", "non_renewing", "past_due"])).order_by(
        Subscription.created_at.desc()))).scalars().first()
    return {"is_plus": is_plus(user), "until": user.plus_until,
            "status": sub.status if sub else None, "plan_code": sub.plan_code if sub else None,
            "renews": bool(sub and sub.status == "active"),
            "show_plus_badge": user.show_plus_badge, "wrapped_opt_in": user.wrapped_opt_in}


@router.post("/api/plus/subscribe")
async def plus_subscribe(payload: SubscribeIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    sub, url = await start_subscription(db, user=user, plan_code=payload.plan_code, callback_url=payload.callback_url)
    return {"reference": sub.reference, "authorization_url": url}


@router.delete("/api/plus")
async def plus_cancel(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    sub = (await db.execute(select(Subscription).where(
        Subscription.user_id == user.id, Subscription.product == "turnup_plus",
        Subscription.status.in_(["active", "past_due"])))).scalars().first()
    if not sub:
        raise HTTPException(404, "No active Turnup+ subscription.")
    await cancel_subscription(db, sub)
    return {"status": sub.status, "until": user.plus_until}


class PlusSettings(BaseModel):
    show_plus_badge: bool | None = None
    wrapped_opt_in: bool | None = None


@router.patch("/api/plus/settings")
async def plus_settings(payload: PlusSettings, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    return {"show_plus_badge": user.show_plus_badge, "wrapped_opt_in": user.wrapped_opt_in}


# ── Deals ──────────────────────────────────────────────────────────────────────

@router.get("/api/me/deals")
async def my_deals(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await deal_svc.my_deals(db, user)


@router.post("/api/deals/{deal_id}/claim")
async def claim_deal(deal_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    r = await deal_svc.claim(db, deal_id, user)
    return {"code": r.code, "claimed_at": r.claimed_at}


@router.get("/api/events/{event_id}/deals")
async def event_deals(event_id: str, db: AsyncSession = Depends(get_db),
                      user: User | None = Depends(get_optional_user)):
    rows = (await db.execute(select(Deal).where(Deal.event_id == event_id, Deal.is_active == True))).scalars().all()  # noqa: E712
    return [{"id": d.id, "title": d.title, "description": d.description, "kind": d.kind,
             "valid_to": d.valid_to} for d in rows]


async def _event_for_host(db: AsyncSession, event_id: str, user: User) -> Event:
    from app.routers.events import _require_event_access
    return await _require_event_access(event_id, user, db)


@router.get("/api/events/{event_id}/deals/manage")
async def manage_event_deals(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.routers.venue_portal import deal_out
    await _event_for_host(db, event_id, user)
    rows = (await db.execute(select(Deal).where(Deal.event_id == event_id).order_by(Deal.created_at.desc()))).scalars().all()
    counts = dict((await db.execute(select(DealRedemption.deal_id, func.count()).where(
        DealRedemption.deal_id.in_([d.id for d in rows]), DealRedemption.redeemed_at.is_not(None)).group_by(
        DealRedemption.deal_id))).all()) if rows else {}
    return [deal_out(d, counts.get(d.id, 0)) for d in rows]


@router.post("/api/events/{event_id}/deals", status_code=201)
async def create_event_deal(event_id: str, payload: DealIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    from app.routers.venue_portal import deal_out
    await _event_for_host(db, event_id, user)
    d = Deal(event_id=event_id, created_by_id=user.id, **payload.model_dump())
    db.add(d)
    await db.flush()
    return deal_out(d)


@router.put("/api/events/{event_id}/deals/{deal_id}")
async def update_event_deal(event_id: str, deal_id: str, payload: DealIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    from app.routers.venue_portal import deal_out
    await _event_for_host(db, event_id, user)
    d = (await db.execute(select(Deal).where(Deal.id == deal_id, Deal.event_id == event_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump().items():
        setattr(d, k, v)
    return deal_out(d)


@router.post("/api/events/{event_id}/deals/redeem")
async def redeem_event_deal(event_id: str, payload: RedeemIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    await _event_for_host(db, event_id, user)
    return await deal_svc.redeem_code(db, payload.code, user, event_id=event_id)


# ── Ticket transfer ────────────────────────────────────────────────────────────

class TransferIn(BaseModel):
    to_username: str = Field(min_length=2, max_length=50)


@router.post("/api/tickets/{order_id}/transfer")
@limiter.limit("20/hour")
async def transfer_ticket(request: Request, order_id: str, payload: TransferIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Members can send a ticket to another Turnup user before the event. The old QR code
    stops working; the new holder gets a new one."""
    if not is_plus(user):
        raise HTTPException(402, "Ticket transfer is a Turnup+ perk.")
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one_or_none()
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Ticket not found")
    event = (await db.execute(select(Event).where(Event.id == order.event_id))).scalar_one()
    if not event.allow_ticket_transfers:
        raise HTTPException(409, "The organizer doesn't allow transfers for this event.")
    if order.status != "confirmed" or order.checked_in_at:
        raise HTTPException(409, "Only unused, confirmed tickets can be transferred.")
    start = event.start_date if event.start_date.tzinfo else event.start_date.replace(tzinfo=timezone.utc)
    if start <= utcnow():
        raise HTTPException(409, "Tickets can't be transferred once the event has started.")
    to = (await db.execute(select(User).where(
        func.lower(User.username) == payload.to_username.strip().lstrip("@").lower(),
        User.is_active == True, User.is_deleted == False))).scalar_one_or_none()  # noqa: E712
    if not to or to.id == user.id:
        raise HTTPException(404, "No other Turnup user with that username.")
    tier = (await db.execute(select(TicketTier).where(TicketTier.id == order.tier_id))).scalar_one()
    if (tier.members_only or event.members_only) and not is_plus(to):
        raise HTTPException(409, "This ticket is for members, and they aren't a Turnup+ member.")
    new_code = str(uuid.uuid4())
    db.add(TicketTransfer(order_id=order.id, from_user_id=user.id, to_user_id=to.id,
                          old_ticket_code=order.ticket_code, new_ticket_code=new_code))
    order.user_id = to.id
    order.ticket_code = new_code
    from app.services.tickets import auto_rsvp
    await auto_rsvp(event, to, db)
    notify(db, to.id, "ticket_received", f"{user.display_name or user.username} sent you a ticket to {event.title}",
           reference_id=order.id, reference_type="ticket_order")
    return {"ok": True, "to": to.username}


# ── Weekend picks and Wrapped ──────────────────────────────────────────────────

@router.get("/api/me/weekend-picks")
async def weekend_picks(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.picks import weekend_picks as build
    if not is_plus(user):
        raise HTTPException(402, "Weekend picks are a Turnup+ perk.")
    return await build(db, user)


@router.get("/api/me/wrapped/{year}")
async def wrapped(year: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.wrapped import get_wrapped
    return await get_wrapped(db, user, year)


@router.get("/api/me/wrapped/{year}/image.png")
async def wrapped_image(year: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.wrapped import get_wrapped, render_png
    data = await get_wrapped(db, user, year)
    return Response(render_png(data), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600",
                             "Content-Disposition": f'inline; filename="turnup-wrapped-{year}.png"'})
