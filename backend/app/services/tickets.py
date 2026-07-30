import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification

_NOTIFICATION_TITLES = {
    "confirmed": "You're going to {title}!",
    "refunded": "Your ticket for {title} was refunded",
    "cancelled": "Your order for {title} was cancelled",
}


async def reserve_inventory(db: AsyncSession, tier: TicketTier, qty: int) -> None:
    """Atomically reserve `qty` units of a tier's inventory at pending-order creation time
    (not at confirm time) — this is what closes the oversell race: the capacity check and
    the increment happen as one indivisible UPDATE, so two concurrent requests for the last
    unit can't both pass. Raises 409 if there isn't enough left. No-op for unlimited tiers."""
    if tier.quantity is None:
        return
    result = await db.execute(
        update(TicketTier)
        .where(
            TicketTier.id == tier.id,
            (TicketTier.quantity - TicketTier.quantity_sold) >= qty,
        )
        .values(quantity_sold=TicketTier.quantity_sold + qty)
    )
    if result.rowcount == 0:
        raise HTTPException(409, f"Not enough tickets remaining for '{tier.name}'")


async def release_inventory(db: AsyncSession, tier_id: str, qty: int) -> None:
    """Give back a reservation — used by cancel/refund/expire."""
    await db.execute(
        update(TicketTier).where(TicketTier.id == tier_id)
        .values(quantity_sold=TicketTier.quantity_sold - qty)
    )


async def confirm_order(db: AsyncSession, order_id: str, payment_channel: str | None) -> TicketOrder | None:
    """Atomic pending->confirmed flip. Returns the order only if THIS call flipped it —
    the shared idempotency primitive for verify-payment and the webhook, so whichever of
    the two arrives first wins and the other is a clean no-op (no double email/notification)."""
    ticket_code = str(uuid.uuid4())
    result = await db.execute(
        update(TicketOrder)
        .where(TicketOrder.id == order_id, TicketOrder.status == "pending")
        .values(status="confirmed", ticket_code=ticket_code, payment_channel=payment_channel)
    )
    if result.rowcount == 0:
        return None
    return (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()


async def cancel_order(db: AsyncSession, order: TicketOrder, reason: str) -> bool:
    """pending -> cancelled, releasing its reservation. Returns False if already resolved
    by something else (e.g. confirmed between when the caller loaded it and now)."""
    result = await db.execute(
        update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == "pending")
        .values(status="cancelled")
    )
    if result.rowcount == 0:
        return False
    await release_inventory(db, order.tier_id, order.quantity)
    return True


async def refund_order(db: AsyncSession, order: TicketOrder) -> bool:
    """confirmed -> refunded, releasing its reservation. Returns False if the order wasn't
    confirmed (caller should have already checked, this is the race-safe backstop)."""
    result = await db.execute(
        update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == "confirmed")
        .values(status="refunded")
    )
    if result.rowcount == 0:
        return False
    await release_inventory(db, order.tier_id, order.quantity)
    return True


async def notify_buyer(db: AsyncSession, order: TicketOrder, event: Event, kind: str) -> None:
    """Creates the in-app Notification row. Email is scheduled separately by the caller via
    BackgroundTasks (request-scoped call sites) or awaited directly (the webhook, which is
    still a request but doesn't need the extra indirection)."""
    db.add(Notification(
        id=str(uuid.uuid4()), user_id=order.user_id, type=f"ticket_{kind}",
        title=_NOTIFICATION_TITLES[kind].format(title=event.title),
        reference_id=order.id, reference_type="ticket_order",
    ))


@dataclass
class ExpireSummary:
    checked: int = 0
    expired: int = 0


async def run_expire_pending_orders(db: AsyncSession, older_than_minutes: int) -> ExpireSummary:
    """Auto-cancel pending orders abandoned before payment ever completed, releasing their
    reserved inventory. Runs on a schedule (see main.py) — cancellations here are silent/
    internal, not buyer-facing, since there's no request context to hang a notification/email
    delivery off of and the buyer never actually paid for anything to be refunded."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    stale = (await db.execute(select(TicketOrder).where(
        TicketOrder.status == "pending", TicketOrder.created_at < cutoff,
    ))).scalars().all()
    summary = ExpireSummary(checked=len(stale))
    for order in stale:
        if await cancel_order(db, order, reason="expired"):
            summary.expired += 1
    await db.commit()
    return summary
