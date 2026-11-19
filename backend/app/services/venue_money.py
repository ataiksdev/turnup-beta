"""Venue money: split payments, the venue balance, venue-funded refunds and penalties
(docs/venues-spec.md 4.2-4.5 and 4.12).

Key rules:
- Organizers pay through Paystack **split**: the venue's share goes straight to its own
  subaccount; Turnup's transaction_charge = commission + any recovery of what the venue owes.
- Refunds are **always funded by the venue**. A refund request is created, the venue pays it
  in (or it's recovered from later payments), and only then does Turnup send the organizer a
  Paystack refund. Turnup never advances its own money.
- The ledger (venue_ledger) holds what the venue owes once deadlines pass: positive amounts
  are owed, negative amounts are paid back. Balance = sum.
"""
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.venue import (
    BlockedIdentity, RefundPayout, RefundRequest, Venue, VenueBooking, VenueLedgerEntry,
    VenueMember, VenuePayment, VenueStrike,
)
from app.services.kyc_store import identity_hash
from app.services.settings import get_platform_settings
from app.services.venue_access import notify, notify_venue_team

logger = logging.getLogger(__name__)

ACTIVE_BOOKING = ("pending_payment", "confirmed", "fully_paid", "disputed")
PAID_BOOKING = ("confirmed", "fully_paid", "disputed")
OPEN_REFUND = ("awaiting_venue", "funded", "overdue", "suspended", "referred")
LATE_REFUND = ("overdue", "suspended", "referred")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}" if kobo % 100 == 0 else f"₦{kobo / 100:,.2f}"


def new_reference(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


# ── Balance and recovery ───────────────────────────────────────────────────────

async def ledger_balance(db: AsyncSession, venue_id: str) -> int:
    return int((await db.execute(select(func.coalesce(func.sum(VenueLedgerEntry.amount_kobo), 0)).where(
        VenueLedgerEntry.venue_id == venue_id))).scalar_one())


async def late_refund_requests(db: AsyncSession, venue_id: str) -> list[RefundRequest]:
    return list((await db.execute(select(RefundRequest).where(
        RefundRequest.venue_id == venue_id, RefundRequest.status.in_(LATE_REFUND),
    ).order_by(RefundRequest.created_at))).scalars().all())


def _unfunded(rr: RefundRequest) -> int:
    return max(rr.amount_kobo - rr.funded_kobo, 0)


async def plan_split(db: AsyncSession, venue: Venue, amount_kobo: int,
                     commission_percent: float) -> tuple[int, int, int]:
    """(commission, recovery, venue_share) for a payment of amount_kobo to this venue.

    Recovery is capped at max_recovery_percent of the venue's share, except while a refund is
    overdue: then everything the venue would get goes to the waiting organizer(s)."""
    ps = await get_platform_settings(db)
    commission = (amount_kobo * int(round(commission_percent * 100))) // 10_000
    share = amount_kobo - commission
    owed = await ledger_balance(db, venue.id)
    if owed <= 0:
        return commission, 0, share
    late = await late_refund_requests(db, venue.id)
    cap = share if late else share * ps.max_recovery_percent // 100
    recovery = min(owed, cap)
    return commission, recovery, share - recovery


async def apply_recovery(db: AsyncSession, venue_id: str, recovery_kobo: int,
                         payment_reference: str) -> list[RefundRequest]:
    """Record money Turnup kept from a payment towards the venue's balance. Overdue refunds
    are funded first (oldest first); the caller then sends those refunds out."""
    if recovery_kobo <= 0:
        return []
    db.add(VenueLedgerEntry(venue_id=venue_id, kind="recovered", amount_kobo=-recovery_kobo,
                            payment_reference=payment_reference,
                            note="Taken from a payment towards the venue's balance"))
    funded: list[RefundRequest] = []
    left = recovery_kobo
    for rr in await late_refund_requests(db, venue_id):
        if left <= 0:
            break
        part = min(left, _unfunded(rr))
        if part:
            rr.funded_kobo += part
            left -= part
            funded.append(rr)
    await db.flush()
    return funded


# ── Payments (initialize / settle) ─────────────────────────────────────────────

async def start_split_payment(
    db: AsyncSession, *, venue: Venue, booking: VenueBooking | None, payer: User, kind: str,
    amount_kobo: int, commission_percent: float, callback_url: str | None = None,
) -> tuple[VenuePayment, str]:
    """Create a pending VenuePayment and the Paystack checkout for it (split to the venue)."""
    from app.services.paystack import PaystackConfigError, initialize_transaction

    if not venue.paystack_subaccount_code:
        raise HTTPException(409, "This venue hasn't finished setting up payouts yet.")
    commission, recovery, share = await plan_split(db, venue, amount_kobo, commission_percent)
    payment = VenuePayment(
        venue_id=venue.id, booking_id=booking.id if booking else None, payer_id=payer.id,
        kind=kind, amount_kobo=amount_kobo, commission_kobo=commission, recovery_kobo=recovery,
        venue_share_kobo=share, reference=new_reference("vb"),
    )
    db.add(payment)
    await db.flush()
    try:
        init = await initialize_transaction(
            email=payer.email or f"{payer.username}@users.turnup.app",
            amount_kobo=amount_kobo, reference=payment.reference,
            metadata={"purpose": f"venue_{kind}", "booking_id": booking.id if booking else None},
            subaccount=venue.paystack_subaccount_code,
            transaction_charge=commission + recovery, bearer="subaccount",
            callback_url=callback_url,
        )
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        logger.exception("Paystack init failed for venue payment %s", payment.reference)
        raise HTTPException(502, "Couldn't start the payment. Please try again.")
    return payment, init["data"]["authorization_url"]


async def start_turnup_payment(
    db: AsyncSession, *, venue: Venue, payer: User, kind: str, amount_kobo: int,
    refund_request_id: str | None = None, prefix: str = "vr", callback_url: str | None = None,
) -> tuple[VenuePayment, str]:
    """A payment into Turnup's own account (no split): refund funding, debt payment, featured."""
    from app.services.paystack import PaystackConfigError, initialize_transaction

    payment = VenuePayment(
        venue_id=venue.id, payer_id=payer.id, kind=kind, amount_kobo=amount_kobo,
        refund_request_id=refund_request_id, reference=new_reference(prefix),
    )
    db.add(payment)
    await db.flush()
    try:
        init = await initialize_transaction(
            email=payer.email or f"{payer.username}@users.turnup.app",
            amount_kobo=amount_kobo, reference=payment.reference,
            metadata={"purpose": f"venue_{kind}", "venue_id": venue.id},
            callback_url=callback_url,
        )
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        logger.exception("Paystack init failed for %s", payment.reference)
        raise HTTPException(502, "Couldn't start the payment. Please try again.")
    return payment, init["data"]["authorization_url"]


def _amount_ok(ps_data: dict, payment: VenuePayment) -> bool:
    if ps_data.get("mock"):
        return True
    try:
        paid = int(ps_data.get("amount"))
    except (TypeError, ValueError):
        return False
    currency = str(ps_data.get("currency") or "NGN").upper()
    ok = paid == payment.amount_kobo and currency == "NGN"
    if not ok:
        logger.warning("Venue payment %s mismatch: paid %s %s, expected %s NGN",
                       payment.reference, paid, currency, payment.amount_kobo)
    return ok


async def overlapping_booking(db: AsyncSession, space_id: str, venue_id: str, starts_at: datetime,
                              ends_at: datetime, exclude_booking_id: str | None = None,
                              include_pending: bool = True) -> bool:
    from app.models.venue import VenueBlock
    statuses = ACTIVE_BOOKING if include_pending else PAID_BOOKING
    q = select(VenueBooking.id).where(
        VenueBooking.space_id == space_id, VenueBooking.status.in_(statuses),
        VenueBooking.starts_at < ends_at, VenueBooking.ends_at > starts_at,
    )
    if exclude_booking_id:
        q = q.where(VenueBooking.id != exclude_booking_id)
    if (await db.execute(q)).first():
        return True
    block = (await db.execute(select(VenueBlock.id).where(
        VenueBlock.venue_id == venue_id,
        or_(VenueBlock.space_id.is_(None), VenueBlock.space_id == space_id),
        VenueBlock.starts_at < ends_at, VenueBlock.ends_at > starts_at,
    ))).first()
    return block is not None


@dataclass
class SettleOutcome:
    status: str  # ok | amount_mismatch | already | unknown
    payment: VenuePayment | None = None


async def settle_venue_payment(db: AsyncSession, reference: str, ps_data: dict) -> SettleOutcome:
    """The single place a successful venue-related Paystack payment takes effect. Shared by the
    webhook, the verify endpoint and the expiry sweep; idempotent (atomic status flip)."""
    payment = (await db.execute(select(VenuePayment).where(
        VenuePayment.reference == reference))).scalar_one_or_none()
    if not payment:
        return SettleOutcome("unknown")
    if payment.status == "success":
        return SettleOutcome("already", payment)
    if not _amount_ok(ps_data, payment):
        return SettleOutcome("amount_mismatch", payment)
    venue = (await db.execute(select(Venue).where(Venue.id == payment.venue_id))).scalar_one()
    sub = ps_data.get("subaccount")
    sub_code = sub.get("subaccount_code") if isinstance(sub, dict) else None
    if payment.kind in ("deposit", "balance") and sub_code and sub_code != venue.paystack_subaccount_code:
        logger.warning("Venue payment %s was split to %s, not the venue's subaccount", reference, sub_code)
        return SettleOutcome("amount_mismatch", payment)
    flipped = await db.execute(update(VenuePayment).where(
        VenuePayment.id == payment.id, VenuePayment.status.in_(["pending", "expired"]),
    ).values(status="success", paid_at=utcnow(), channel=ps_data.get("channel")))
    if flipped.rowcount == 0:
        return SettleOutcome("already", payment)
    await db.refresh(payment)
    funded = await apply_recovery(db, venue.id, payment.recovery_kobo, payment.reference)

    if payment.kind in ("deposit", "balance"):
        await _apply_booking_payment(db, payment, venue)
    elif payment.kind == "refund_funding":
        rr = (await db.execute(select(RefundRequest).where(
            RefundRequest.id == payment.refund_request_id))).scalar_one_or_none()
        if rr:
            was_late = rr.status in LATE_REFUND
            rr.funded_kobo = min(rr.amount_kobo, rr.funded_kobo + payment.amount_kobo)
            if was_late:
                db.add(VenueLedgerEntry(venue_id=venue.id, kind="paid_directly",
                                        amount_kobo=-payment.amount_kobo, refund_request_id=rr.id,
                                        payment_reference=payment.reference,
                                        note="Venue paid an overdue refund"))
            funded.append(rr)
    elif payment.kind == "debt_payment":
        db.add(VenueLedgerEntry(venue_id=venue.id, kind="paid_directly",
                                amount_kobo=-payment.amount_kobo, payment_reference=payment.reference,
                                note="Venue paid off its balance"))
        # Paying the balance also funds any overdue refunds it covers.
        left = payment.amount_kobo
        for rr in await late_refund_requests(db, venue.id):
            part = min(left, _unfunded(rr))
            if part:
                rr.funded_kobo += part
                left -= part
                funded.append(rr)
    elif payment.kind == "featured":
        from app.models.venue import FeaturedSlot
        await db.execute(update(FeaturedSlot).where(
            FeaturedSlot.payment_reference == payment.reference, FeaturedSlot.status.in_(["pending", "expired"]),
        ).values(status="active"))
    await db.flush()
    for rr in {r.id: r for r in funded}.values():
        await pay_out_refund(db, rr)
    await restore_venue_if_clear(db, venue)
    await db.flush()
    return SettleOutcome("ok", payment)


async def _apply_booking_payment(db: AsyncSession, payment: VenuePayment, venue: Venue) -> None:
    booking = (await db.execute(select(VenueBooking).where(
        VenueBooking.id == payment.booking_id))).scalar_one()
    booking.paid_kobo += payment.amount_kobo
    booking.commission_kobo += payment.commission_kobo
    if payment.kind == "deposit":
        if booking.status in ("pending_payment", "expired"):
            clash = await overlapping_booking(db, booking.space_id, booking.venue_id, booking.starts_at,
                                              booking.ends_at, exclude_booking_id=booking.id,
                                              include_pending=False)
            if clash:
                # Paid after the hold lapsed and someone else got the date: the venue refunds
                # the deposit (it holds the money); no strike, it isn't the venue's fault.
                booking.status = "cancelled_by_venue"
                booking.cancelled_at = utcnow()
                booking.cancel_reason = "The date was taken before this payment arrived."
                await create_refund_request(db, booking, "venue_cancelled", payment.amount_kobo)
                notify(db, booking.organizer_id, "venue_booking_unavailable",
                       "That date was taken before your deposit arrived. The venue has been asked to refund you.",
                       reference_id=booking.id, reference_type="venue_booking")
                return
            booking.status = "confirmed"
            from app.models.venue import VenueEnquiry, VenueQuote
            await db.execute(update(VenueQuote).where(VenueQuote.id == booking.quote_id).values(status="accepted"))
            await db.execute(update(VenueEnquiry).where(VenueEnquiry.id == booking.enquiry_id).values(status="booked"))
            notify(db, booking.organizer_id, "venue_booking_confirmed",
                   f"Booking confirmed at {venue.name}", reference_id=booking.id,
                   reference_type="venue_booking")
            await notify_venue_team(db, venue.id, "venue_booking_confirmed",
                                    f"New booking confirmed: deposit of {naira(payment.amount_kobo)} paid",
                                    reference_id=booking.id, reference_type="venue_booking")
    else:
        notify(db, booking.organizer_id, "venue_balance_paid",
               f"Payment of {naira(payment.amount_kobo)} to {venue.name} received",
               reference_id=booking.id, reference_type="venue_booking")
        await notify_venue_team(db, venue.id, "venue_balance_paid",
                                f"Balance payment of {naira(payment.amount_kobo)} received",
                                reference_id=booking.id, reference_type="venue_booking")
    if booking.status == "confirmed" and booking.paid_kobo >= booking.total_kobo:
        booking.status = "fully_paid"


# ── Refund requests and payouts ────────────────────────────────────────────────

async def create_refund_request(db: AsyncSession, booking: VenueBooking, reason: str,
                                amount_kobo: int, dispute_id: str | None = None) -> RefundRequest | None:
    amount_kobo = min(amount_kobo, booking.paid_kobo - booking.refunded_kobo - await _pending_refunds(db, booking.id))
    if amount_kobo <= 0:
        return None
    ps = await get_platform_settings(db)
    rr = RefundRequest(booking_id=booking.id, venue_id=booking.venue_id, organizer_id=booking.organizer_id,
                       dispute_id=dispute_id, reason=reason, amount_kobo=amount_kobo,
                       due_at=utcnow() + timedelta(hours=ps.refund_funding_hours))
    db.add(rr)
    await db.flush()
    notify(db, booking.organizer_id, "venue_refund_requested",
           f"Refund of {naira(amount_kobo)} requested from the venue",
           "The venue must pay it in within the deadline; Turnup then sends it to you.",
           reference_id=rr.id, reference_type="refund_request")
    await notify_venue_team(db, booking.venue_id, "venue_refund_due",
                            f"Refund of {naira(amount_kobo)} due within {ps.refund_funding_hours} hours",
                            "Pay it from the venue portal. Late refunds pause your listing.",
                            reference_id=rr.id, reference_type="refund_request")
    return rr


async def _pending_refunds(db: AsyncSession, booking_id: str) -> int:
    rows = (await db.execute(select(RefundRequest).where(
        RefundRequest.booking_id == booking_id, RefundRequest.status.in_(OPEN_REFUND)))).scalars().all()
    return sum(r.amount_kobo - r.refunded_kobo for r in rows)


async def pay_out_refund(db: AsyncSession, rr: RefundRequest) -> int:
    """Send the organizer whatever has been funded but not yet refunded, as Paystack refunds
    against their booking payments (newest first). Returns kobo sent."""
    from app.services.paystack import refund_transaction

    available = rr.funded_kobo - rr.refunded_kobo
    if available <= 0:
        return 0
    payments = (await db.execute(select(VenuePayment).where(
        VenuePayment.booking_id == rr.booking_id, VenuePayment.kind.in_(["deposit", "balance"]),
        VenuePayment.status == "success",
    ).order_by(VenuePayment.paid_at.desc()))).scalars().all()
    sent = 0
    for p in payments:
        if available <= 0:
            break
        room = p.amount_kobo - p.refunded_kobo
        part = min(room, available)
        if part <= 0:
            continue
        try:
            await refund_transaction(p.reference, part)
        except Exception as e:  # retried by the refund sweep
            logger.exception("Refund payout failed for %s", p.reference)
            db.add(RefundPayout(refund_request_id=rr.id, payment_id=p.id, amount_kobo=part,
                                status="failed", error=str(e)[:500]))
            break
        db.add(RefundPayout(refund_request_id=rr.id, payment_id=p.id, amount_kobo=part))
        p.refunded_kobo += part
        rr.refunded_kobo += part
        available -= part
        sent += part
    if sent:
        booking = (await db.execute(select(VenueBooking).where(VenueBooking.id == rr.booking_id))).scalar_one()
        booking.refunded_kobo += sent
        notify(db, rr.organizer_id, "venue_refund_sent", f"{naira(sent)} refunded to you",
               "Banks usually take a few working days to show it.",
               reference_id=rr.id, reference_type="refund_request")
    if rr.refunded_kobo >= rr.amount_kobo:
        rr.status = "refunded"
        await lift_blocks(db, rr.id)
    elif rr.funded_kobo >= rr.amount_kobo and rr.status == "awaiting_venue":
        rr.status = "funded"
    await db.flush()
    return sent


# ── Penalties ──────────────────────────────────────────────────────────────────

async def add_strike(db: AsyncSession, venue: Venue, reason: str, booking_id: str | None = None,
                     note: str | None = None, by: str | None = None) -> int:
    ps = await get_platform_settings(db)
    db.add(VenueStrike(venue_id=venue.id, booking_id=booking_id, reason=reason, note=note, created_by_id=by))
    await db.flush()
    count = await strikes_last_year(db, venue.id)
    if count >= ps.strike_suspend_count and venue.status in ("live", "paused"):
        venue.status = "suspended"
        venue.pause_reason = "strikes"
        await notify_venue_team(db, venue.id, "venue_suspended",
                                f"{venue.name} is suspended after {count} strikes in 12 months",
                                "Contact Turnup support to appeal.", minimum="viewer")
    return count


async def strikes_last_year(db: AsyncSession, venue_id: str) -> int:
    since = utcnow() - timedelta(days=365)
    return int((await db.execute(select(func.count()).select_from(VenueStrike).where(
        VenueStrike.venue_id == venue_id, VenueStrike.created_at >= since))).scalar_one())


async def lift_blocks(db: AsyncSession, refund_request_id: str) -> None:
    await db.execute(update(BlockedIdentity).where(
        BlockedIdentity.refund_request_id == refund_request_id, BlockedIdentity.lifted_at.is_(None),
    ).values(lifted_at=utcnow()))


async def is_blocked(db: AsyncSession, *, cac: str | None = None, bank_account: str | None = None,
                     user_id: str | None = None) -> bool:
    hashes = []
    if cac:
        hashes.append(identity_hash(cac))
    if bank_account:
        hashes.append(identity_hash(bank_account))
    if user_id:
        hashes.append(identity_hash(f"user:{user_id}"))
    if not hashes:
        return False
    row = (await db.execute(select(BlockedIdentity.id).where(
        BlockedIdentity.value_hash.in_(hashes), BlockedIdentity.lifted_at.is_(None)))).first()
    return row is not None


async def restore_venue_if_clear(db: AsyncSession, venue: Venue) -> None:
    """Undo a pause/suspension caused by money once nothing is late any more."""
    if venue.status not in ("paused", "suspended") or venue.pause_reason not in ("unpaid_refund", "debt"):
        return
    if await late_refund_requests(db, venue.id):
        return
    if await ledger_balance(db, venue.id) > 0 and await _debt_overdue(db, venue.id):
        return
    venue.status = "live"
    venue.pause_reason = None
    await notify_venue_team(db, venue.id, "venue_restored", f"{venue.name} is live again", minimum="viewer")


async def _debt_overdue(db: AsyncSession, venue_id: str) -> bool:
    """True if the balance has been above zero for longer than venue_debt_pause_days."""
    ps = await get_platform_settings(db)
    entries = (await db.execute(select(VenueLedgerEntry.amount_kobo, VenueLedgerEntry.created_at).where(
        VenueLedgerEntry.venue_id == venue_id).order_by(VenueLedgerEntry.created_at))).all()
    running, positive_since = 0, None
    for amount, at in entries:
        before = running
        running += amount
        if before <= 0 < running:
            positive_since = as_utc(at)
        elif running <= 0:
            positive_since = None
    return bool(positive_since and utcnow() - positive_since > timedelta(days=ps.venue_debt_pause_days))


async def _block_identities(db: AsyncSession, venue: Venue, rr: RefundRequest) -> None:
    reason = f"Unpaid refund {rr.id} referred to the organizer"
    values = []
    if venue.cac_number:
        values.append(("cac", identity_hash(venue.cac_number)))
    if venue.bank_account_hash:
        values.append(("bank_account", venue.bank_account_hash))
    owners = (await db.execute(select(VenueMember.user_id).where(
        VenueMember.venue_id == venue.id, VenueMember.role == "owner"))).scalars().all()
    values += [("user", identity_hash(f"user:{uid}")) for uid in owners]
    for kind, h in values:
        db.add(BlockedIdentity(kind=kind, value_hash=h, refund_request_id=rr.id, reason=reason))


@dataclass
class PenaltySummary:
    overdue: int = 0
    suspended: int = 0
    referred: int = 0
    reminded: int = 0
    paid_out: int = 0
    debt_paused: int = 0


async def run_refund_penalties(db: AsyncSession) -> PenaltySummary:
    """The unpaid-refund timeline (spec 4.12), run by the worker."""
    ps = await get_platform_settings(db)
    now = utcnow()
    summary = PenaltySummary()
    rows = (await db.execute(select(RefundRequest).where(RefundRequest.status.in_(OPEN_REFUND)))).scalars().all()
    for rr in rows:
        venue = (await db.execute(select(Venue).where(Venue.id == rr.venue_id))).scalar_one()
        # Retry payouts that failed or are funded but unsent.
        if rr.funded_kobo > rr.refunded_kobo:
            summary.paid_out += await pay_out_refund(db, rr)
            if rr.status == "refunded":
                await restore_venue_if_clear(db, venue)
                continue
        created = as_utc(rr.created_at)
        if rr.status in ("awaiting_venue", "funded") and now > as_utc(rr.due_at) and _unfunded(rr) > 0:
            rr.status = "overdue"
            rr.paused_at = now
            db.add(VenueLedgerEntry(venue_id=venue.id, kind="refund_owed", amount_kobo=_unfunded(rr),
                                    booking_id=rr.booking_id, refund_request_id=rr.id,
                                    note="Refund not paid in by the deadline"))
            if venue.status == "live":
                venue.status = "paused"
                venue.pause_reason = "unpaid_refund"
            notify(db, rr.organizer_id, "venue_refund_overdue",
                   "The venue missed the refund deadline",
                   "Its listing is paused and its next payments will go to your refund.",
                   reference_id=rr.id, reference_type="refund_request")
            await notify_venue_team(db, venue.id, "venue_refund_overdue",
                                    f"Refund of {naira(_unfunded(rr))} is overdue: your listing is paused",
                                    reference_id=rr.id, reference_type="refund_request", minimum="viewer")
            summary.overdue += 1
        elif rr.status == "overdue" and now - created > timedelta(days=ps.refund_suspend_days):
            rr.status = "suspended"
            rr.suspended_at = now
            if venue.status in ("live", "paused"):
                venue.status = "suspended"
                venue.pause_reason = "unpaid_refund"
            await add_strike(db, venue, "unpaid_refund", booking_id=rr.booking_id)
            upcoming = (await db.execute(select(VenueBooking).where(
                VenueBooking.venue_id == venue.id, VenueBooking.status.in_(PAID_BOOKING),
                VenueBooking.starts_at > now))).scalars().all()
            for b in upcoming:
                notify(db, b.organizer_id, "venue_suspended_notice",
                       f"{venue.name} is suspended on Turnup",
                       "Your booking still stands. Talk to the venue in your enquiry thread, or cancel "
                       "under the normal rules.", reference_id=b.id, reference_type="venue_booking")
            summary.suspended += 1
        elif rr.status == "suspended" and now - created > timedelta(days=ps.refund_referral_days):
            rr.status = "referred"
            rr.referred_at = now
            await _block_identities(db, venue, rr)
            notify(db, rr.organizer_id, "venue_refund_referred",
                   "Turnup's enforcement period has ended",
                   "Download your claim pack from the booking. It has the records and the venue's "
                   "verified legal details for pursuing the refund directly.",
                   reference_id=rr.id, reference_type="refund_request")
            summary.referred += 1
        # Daily reminders while late.
        if rr.status in ("overdue", "suspended") and (
                not rr.last_reminder_at or now - as_utc(rr.last_reminder_at) > timedelta(hours=23)):
            rr.last_reminder_at = now
            await notify_venue_team(db, venue.id, "venue_refund_reminder",
                                    f"Reminder: refund of {naira(_unfunded(rr))} is unpaid",
                                    reference_id=rr.id, reference_type="refund_request")
            summary.reminded += 1

    # Pause venues whose general balance (e.g. lost chargebacks) has been unpaid too long.
    debtors = (await db.execute(select(VenueLedgerEntry.venue_id).group_by(VenueLedgerEntry.venue_id).having(
        func.sum(VenueLedgerEntry.amount_kobo) > 0))).scalars().all()
    for vid in debtors:
        venue = (await db.execute(select(Venue).where(Venue.id == vid))).scalar_one()
        if venue.status == "live" and await _debt_overdue(db, vid):
            venue.status = "paused"
            venue.pause_reason = "debt"
            await notify_venue_team(db, vid, "venue_paused_debt",
                                    f"{venue.name} is paused: your Turnup balance is unpaid",
                                    "Pay it from the venue portal to go live again.", minimum="viewer")
            summary.debt_paused += 1
    await db.commit()
    return summary


async def settle_directly(db: AsyncSession, rr: RefundRequest, side: str) -> RefundRequest:
    """Either side confirms the refund was settled outside Turnup; both must confirm."""
    if side == "organizer":
        rr.settled_by_organizer = True
    else:
        rr.settled_by_venue = True
    if rr.settled_by_organizer and rr.settled_by_venue and rr.status in OPEN_REFUND:
        unfunded = _unfunded(rr)
        if rr.status in LATE_REFUND and unfunded:
            db.add(VenueLedgerEntry(venue_id=rr.venue_id, kind="adjustment", amount_kobo=-unfunded,
                                    refund_request_id=rr.id, note="Settled directly between the parties"))
        rr.status = "settled_directly"
        await lift_blocks(db, rr.id)
        venue = (await db.execute(select(Venue).where(Venue.id == rr.venue_id))).scalar_one()
        await db.flush()
        await restore_venue_if_clear(db, venue)
    await db.flush()
    return rr
