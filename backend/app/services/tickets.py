import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification
from app.services.settings import get_platform_settings

logger = logging.getLogger(__name__)

_NOTIFICATION_TITLES = {
    "confirmed": "You're going to {title}!",
    "refunded": "Your ticket for {title} was refunded",
    "cancelled": "Your order for {title} was cancelled",
}


def to_kobo(amount: float) -> int:
    """Naira -> kobo. round(), not int(): int(19.99 * 100) is 1998 because of float error."""
    return int(round(amount * 100))


async def payment_matches_orders(
    db: AsyncSession, ps_data: dict, orders: list[TicketOrder],
) -> bool:
    """True only if Paystack says it collected exactly what these orders cost, in the right
    currency. A "success" status alone proves nothing about HOW MUCH was paid: the amount is
    chosen in the buyer's browser when the Paystack popup opens, so a tampered client could
    pay N1 against a reference for a N50,000 order. Both verify-payment and the webhook must
    pass this check before confirming anything."""
    if ps_data.get("mock"):
        return True  # dev-only mock verify (paystack.py refuses mock mode outside debug)

    expected_kobo = to_kobo(sum(o.total_price for o in orders))
    tier_ids = {o.tier_id for o in orders}
    currencies = set((await db.execute(
        select(TicketTier.currency).where(TicketTier.id.in_(tier_ids))
    )).scalars().all())
    expected_currency = currencies.pop().upper() if len(currencies) == 1 else None

    try:
        paid_kobo = int(ps_data.get("amount"))
    except (TypeError, ValueError):
        paid_kobo = None
    paid_currency = str(ps_data.get("currency") or "").upper()

    ok = paid_kobo == expected_kobo and expected_currency is not None and paid_currency == expected_currency
    if not ok:
        logger.warning(
            "Paystack amount mismatch for reference %s: paid %s %s, expected %s %s",
            ps_data.get("reference"), paid_kobo, paid_currency, expected_kobo, expected_currency,
        )
    return ok


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
    the two arrives first wins and the other is a clean no-op (no double email/notification).

    Also snapshots the platform fee onto the order: the fee rate in effect *right now* is
    frozen onto this order permanently, so a later admin rate change never retroactively
    rewrites the economics of an order that already happened. Free tickets get a zero fee —
    there's no money to take a cut of."""
    ticket_code = str(uuid.uuid4())
    result = await db.execute(
        update(TicketOrder)
        .where(TicketOrder.id == order_id, TicketOrder.status == "pending")
        .values(status="confirmed", ticket_code=ticket_code, payment_channel=payment_channel)
    )
    if result.rowcount == 0:
        return None
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()

    fee_percent = 0.0
    fee_amount = 0.0
    if order.total_price > 0:
        platform_settings = await get_platform_settings(db)
        fee_percent = platform_settings.ticket_fee_percent
        fee_amount = round(order.total_price * fee_percent / 100, 2)
    order.platform_fee_percent = fee_percent
    order.platform_fee_amount = fee_amount
    await db.flush()
    return order


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
    """confirmed -> refunded, returning the buyer's money through Paystack and releasing the
    reservation. Returns False if the order wasn't confirmed (race-safe backstop).

    Order of operations matters: the status flip happens first (claiming the refund so two
    concurrent requests can't both pay out), then Paystack is called. If Paystack fails we
    raise, and get_db's rollback-on-exception undoes the flip -- so an order is never marked
    refunded, nor the buyer told so, unless Paystack actually accepted the refund."""
    from app.services.paystack import PaystackConfigError, refund_transaction

    result = await db.execute(
        update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == "confirmed")
        .values(status="refunded")
    )
    if result.rowcount == 0:
        return False

    if order.total_price > 0:
        if not order.payment_reference:
            raise HTTPException(409, "Order has no payment reference; refund it manually in Paystack.")
        try:
            await refund_transaction(order.payment_reference, to_kobo(order.total_price))
        except PaystackConfigError as e:
            raise HTTPException(503, str(e))
        except Exception:
            logger.exception("Paystack refund failed for order %s", order.id)
            raise HTTPException(502, "Payment provider could not process the refund. Nothing was changed; try again.")

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
