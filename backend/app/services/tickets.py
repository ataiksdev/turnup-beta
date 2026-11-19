import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventAttendee
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification
from app.models.user import User
from app.services.settings import get_platform_settings

logger = logging.getLogger(__name__)

_NOTIFICATION_TITLES = {
    "confirmed": "You're going to {title}!",
    "refunded": "Your ticket for {title} was refunded",
    "cancelled": "Your order for {title} was cancelled",
    "refunded_unavailable": "Tickets for {title} sold out before your payment cleared. You've been refunded.",
    "needs_refund": "Tickets for {title} sold out before your payment cleared. Your refund is being processed.",
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

    # "needs_refund" = paid after expiry when tickets had already sold out, and the automatic
    # refund failed (see settle_paid_orders). It never held inventory, so none is released.
    from_status = "needs_refund" if order.status == "needs_refund" else "confirmed"
    result = await db.execute(
        update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == from_status)
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

    if from_status == "confirmed":
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


async def auto_rsvp(event: Event, user: User | None, db: AsyncSession) -> None:
    """A confirmed ticket implies a "going" RSVP."""
    if not user:
        return
    existing = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event.id,
        EventAttendee.user_id == user.id,
    ))).scalar_one_or_none()
    if not existing:
        db.add(EventAttendee(
            id=str(uuid.uuid4()), user_id=user.id,
            event_id=event.id, status="going",
        ))
        event.attendees_count += 1


# ── Settling a successful payment ──────────────────────────────────────────────

@dataclass
class EmailJob:
    """An email to send after the DB work is done. Request handlers hand these to
    BackgroundTasks; the scheduled sweep (no request) awaits them directly."""
    fn: Callable[..., Awaitable[None]]
    kwargs: dict


@dataclass
class SettleResult:
    status: str = "ok"  # "ok" | "amount_mismatch"
    newly_confirmed: list[TicketOrder] = field(default_factory=list)
    refunded_unavailable: list[TicketOrder] = field(default_factory=list)
    needs_refund: list[TicketOrder] = field(default_factory=list)
    emails: list[EmailJob] = field(default_factory=list)


async def _revive_expired_order(db: AsyncSession, order: TicketOrder) -> bool:
    """cancelled (expired unpaid) -> pending, re-taking its inventory. False if the tickets
    have sold out in the meantime. Only the expiry sweep ever cancels orders, so a cancelled
    order that later turns out to be paid is always this late-payment case."""
    tier = (await db.execute(select(TicketTier).where(TicketTier.id == order.tier_id))).scalar_one_or_none()
    if not tier or not tier.is_active:
        return False
    try:
        await reserve_inventory(db, tier, order.quantity)
    except HTTPException:
        return False  # sold out
    result = await db.execute(
        update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == "cancelled")
        .values(status="pending")
    )
    if result.rowcount == 0:  # someone else resolved it first; give the units back
        await release_inventory(db, order.tier_id, order.quantity)
        return False
    return True


async def settle_paid_orders(
    db: AsyncSession, orders: list[TicketOrder], ps_data: dict,
) -> SettleResult:
    """The one place a successful Paystack payment turns into tickets. Shared by the buyer's
    verify-payment call, the Paystack webhook, and the expiry sweep, and safe to run more
    than once for the same payment (every state change is an atomic conditional UPDATE).

    - pending orders are confirmed;
    - cancelled orders (expired before the payment arrived) are revived and confirmed if
      tickets are still available;
    - if they've sold out, the buyer's money for those orders is refunded through Paystack.
      If that refund call fails, the orders are marked "needs_refund" so an admin can retry
      from the dashboard -- a payment is never silently kept without a ticket.
    """
    from app.services.email import send_refund_email, send_ticket_email
    from app.services.paystack import refund_transaction

    result = SettleResult()
    if not await payment_matches_orders(db, ps_data, orders):
        result.status = "amount_mismatch"
        return result

    channel = ps_data.get("channel")
    unavailable: list[TicketOrder] = []
    for order in orders:
        if order.status == "cancelled" and not await _revive_expired_order(db, order):
            unavailable.append(order)
            continue
        if order.status in ("pending", "cancelled"):
            row = await confirm_order(db, order.id, channel)
            if row:
                result.newly_confirmed.append(row)

    if unavailable:
        reference = unavailable[0].payment_reference
        amount = to_kobo(sum(o.total_price for o in unavailable))
        try:
            await refund_transaction(reference, amount)
            new_status = "refunded"
        except Exception:
            logger.exception(
                "Late payment %s: tickets sold out and the automatic refund of %s kobo FAILED; "
                "orders marked needs_refund for an admin to retry", reference, amount,
            )
            new_status = "needs_refund"
        for order in unavailable:
            await db.execute(
                update(TicketOrder).where(TicketOrder.id == order.id, TicketOrder.status == "cancelled")
                .values(status=new_status, payment_channel=channel)
            )
            (result.refunded_unavailable if new_status == "refunded" else result.needs_refund).append(order)

    # Venue-hosted event paid by split: what Turnup kept towards the venue's balance.
    first = orders[0] if orders else None
    if result.newly_confirmed and first and first.venue_id and (first.recovery_kobo or 0) > 0:
        await _apply_ticket_recovery(db, first)

    # Side effects: RSVP, in-app notifications, emails.
    events: dict[str, Event] = {}
    users: dict[str, User | None] = {}

    async def _ctx(order: TicketOrder) -> tuple[Event, User | None, TicketTier | None]:
        if order.event_id not in events:
            events[order.event_id] = (await db.execute(
                select(Event).where(Event.id == order.event_id))).scalar_one()
        if order.user_id not in users:
            users[order.user_id] = (await db.execute(
                select(User).where(User.id == order.user_id))).scalar_one_or_none()
        tier = (await db.execute(select(TicketTier).where(TicketTier.id == order.tier_id))).scalar_one_or_none()
        return events[order.event_id], users[order.user_id], tier

    for row in result.newly_confirmed:
        event, buyer, tier = await _ctx(row)
        await auto_rsvp(event, buyer, db)
        await notify_buyer(db, row, event, kind="confirmed")
        result.emails.append(EmailJob(send_ticket_email, dict(
            to=(buyer.email if buyer else "") or "", order_id=row.id,
            ticket_code=row.ticket_code, event_title=event.title,
            event_date=event.start_date, event_venue=event.venue_name,
            event_address=event.address, tier_name=tier.name if tier else "",
            quantity=row.quantity, total_price=row.total_price,
        )))

    for order in result.refunded_unavailable + result.needs_refund:
        event, buyer, tier = await _ctx(order)
        kind = "refunded_unavailable" if order in result.refunded_unavailable else "needs_refund"
        await notify_buyer(db, order, event, kind=kind)
        if kind == "refunded_unavailable":
            result.emails.append(EmailJob(send_refund_email, dict(
                to=(buyer.email if buyer else "") or "", event_title=event.title,
                tier_name=tier.name if tier else "", quantity=order.quantity,
                total_price=order.total_price,
            )))

    await db.flush()
    return result


# ── Expiry sweep ───────────────────────────────────────────────────────────────

# If Paystack can't be reached, stale paid orders are left pending and retried on the next
# sweep -- but not forever.
_GIVE_UP_VERIFYING_AFTER = timedelta(hours=24)


@dataclass
class ExpireSummary:
    checked: int = 0
    expired: int = 0
    recovered: int = 0   # found paid at Paystack and confirmed instead of cancelled
    deferred: int = 0    # Paystack unreachable; retried next sweep


async def run_expire_pending_orders(db: AsyncSession, older_than_minutes: int) -> ExpireSummary:
    """Cancel pending orders abandoned before payment, releasing their reserved inventory.

    Before cancelling a paid order, ask Paystack whether it was actually paid: if the buyer
    paid but neither their browser callback nor the webhook got through, this is the last
    line of defence, and the order is confirmed instead. (A payment that completes AFTER
    cancellation is still handled: settle_paid_orders revives or refunds it.)"""
    from app.config import settings
    from app.services.paystack import verify_transaction

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=older_than_minutes)
    stale = (await db.execute(select(TicketOrder).where(
        TicketOrder.status == "pending", TicketOrder.created_at < cutoff,
    ))).scalars().all()
    summary = ExpireSummary(checked=len(stale))

    by_reference: dict[str | None, list[TicketOrder]] = {}
    for order in stale:
        by_reference.setdefault(order.payment_reference, []).append(order)

    for reference, group in by_reference.items():
        is_paid = sum(o.total_price for o in group) > 0
        # Without a real Paystack key (local dev) there's nothing to ask -- the dev mock
        # would claim every reference succeeded -- so just expire as before.
        if is_paid and reference and settings.paystack_secret_key:
            try:
                ps_data = (await verify_transaction(reference)).get("data") or {}
            except Exception:
                created = group[0].created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if now - created < _GIVE_UP_VERIFYING_AFTER:
                    logger.warning("Expiry sweep: could not verify %s with Paystack; retrying later", reference)
                    summary.deferred += len(group)
                    continue
                ps_data = {}
            if ps_data.get("status") == "success":
                settled = await settle_paid_orders(db, group, ps_data)
                summary.recovered += len(settled.newly_confirmed)
                await db.commit()
                for job in settled.emails:
                    try:
                        await job.fn(**job.kwargs)
                    except Exception:
                        logger.exception("Expiry sweep: email failed")
                if settled.status == "ok":
                    continue
                # amount mismatch: fall through and expire like any unpaid order

        for order in group:
            if await cancel_order(db, order, reason="expired"):
                summary.expired += 1
    await db.commit()
    return summary


async def _apply_ticket_recovery(db: AsyncSession, order: TicketOrder) -> None:
    from app.models.venue import Venue, VenueLedgerEntry
    from app.services.venue_money import apply_recovery, pay_out_refund, restore_venue_if_clear
    done = (await db.execute(select(VenueLedgerEntry.id).where(
        VenueLedgerEntry.payment_reference == order.payment_reference,
        VenueLedgerEntry.kind == "recovered"))).first()
    if done:
        return
    for rr in await apply_recovery(db, order.venue_id, order.recovery_kobo, order.payment_reference):
        await pay_out_refund(db, rr)
    venue = (await db.execute(select(Venue).where(Venue.id == order.venue_id))).scalar_one()
    await restore_venue_if_clear(db, venue)
