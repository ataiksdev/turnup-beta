"""Enquiries, quotes, bookings, cancellations and disputes (docs/venues-spec.md 4.2-4.4)."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.venue import (
    EnquiryMessage, RefundRequest, Venue, VenueBooking, VenueDispute, VenueEnquiry, VenuePayment,
    VenueQuote, VenueReview, VenueSpace,
)
from app.services.settings import get_platform_settings
from app.services.venue_access import notify, notify_venue_team
from app.services.venue_money import (
    PAID_BOOKING, add_strike, as_utc, create_refund_request, naira, overlapping_booking,
    settle_venue_payment, start_split_payment, utcnow,
)
from app.services.venue_policy import refund_amount

_PHONE = re.compile(r"(?:\+?234|0)[789][01]\d[\s-]?\d{3}[\s-]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_WHATSAPP = re.compile(r"wa\.me|whatsapp", re.I)


def has_contact_details(body: str) -> bool:
    return bool(_PHONE.search(body) or _EMAIL.search(body) or _WHATSAPP.search(body))


async def post_message(db: AsyncSession, enquiry: VenueEnquiry, side: str, sender: User | None, body: str,
                       quote_id: str | None = None) -> EnquiryMessage:
    if enquiry.status in ("closed", "expired") and side != "system":
        raise HTTPException(409, "This conversation is closed.")
    m = EnquiryMessage(enquiry_id=enquiry.id, sender_id=sender.id if sender else None, sender_side=side,
                       body=body.strip(), quote_id=quote_id,
                       flagged_contact=side != "system" and has_contact_details(body))
    db.add(m)
    enquiry.last_message_at = utcnow()
    if side == "organizer":
        enquiry.organizer_last_read_at = enquiry.last_message_at
        venue = (await db.execute(select(Venue).where(Venue.id == enquiry.venue_id))).scalar_one()
        await notify_venue_team(db, venue.id, "venue_enquiry_message", f"New message about {venue.name}",
                                body[:140], reference_id=enquiry.id, reference_type="venue_enquiry",
                                minimum="viewer")
    elif side == "venue":
        enquiry.venue_last_read_at = enquiry.last_message_at
        venue = (await db.execute(select(Venue).where(Venue.id == enquiry.venue_id))).scalar_one()
        notify(db, enquiry.organizer_id, "venue_enquiry_message", f"{venue.name} replied", body[:140],
               reference_id=enquiry.id, reference_type="venue_enquiry")
    await db.flush()
    return m


async def create_enquiry(db: AsyncSession, venue: Venue, organizer: User, payload) -> VenueEnquiry:
    if venue.status != "live":
        raise HTTPException(409, "This venue isn't accepting enquiries right now.")
    if as_utc(payload.starts_at) < utcnow():
        raise HTTPException(400, "Pick a date in the future.")
    if payload.space_id:
        space = (await db.execute(select(VenueSpace).where(
            VenueSpace.id == payload.space_id, VenueSpace.venue_id == venue.id, VenueSpace.is_active == True))).scalar_one_or_none()  # noqa: E712
        if not space:
            raise HTTPException(404, "Space not found")
    if await _is_team(db, venue.id, organizer.id):
        raise HTTPException(400, "You can't enquire about your own venue.")
    open_count = (await db.execute(select(func.count()).select_from(VenueEnquiry).where(
        VenueEnquiry.organizer_id == organizer.id, VenueEnquiry.created_at > utcnow() - timedelta(days=1)))).scalar_one()
    if open_count >= 30:
        raise HTTPException(429, "Too many enquiries today. Try again tomorrow.")
    e = VenueEnquiry(venue_id=venue.id, space_id=payload.space_id, organizer_id=organizer.id,
                     starts_at=payload.starts_at, ends_at=payload.ends_at, guest_count=payload.guest_count,
                     event_type=payload.event_type, budget_kobo=payload.budget_kobo)
    db.add(e)
    await db.flush()
    await post_message(db, e, "organizer", organizer, payload.message)
    return e


async def _is_team(db: AsyncSession, venue_id: str, user_id: str) -> bool:
    from app.models.venue import VenueMember
    return (await db.execute(select(VenueMember.id).where(
        VenueMember.venue_id == venue_id, VenueMember.user_id == user_id))).first() is not None


def default_deposit(venue: Venue, total_kobo: int) -> int:
    if venue.deposit_type == "fixed":
        return min(max(int(venue.deposit_value), 1), total_kobo)
    return max(total_kobo * int(venue.deposit_value) // 100, 1)


async def send_quote(db: AsyncSession, enquiry: VenueEnquiry, venue: Venue, user: User, payload) -> VenueQuote:
    if enquiry.status in ("booked", "closed", "expired", "declined"):
        raise HTTPException(409, "This enquiry can't take a new quote.")
    space = (await db.execute(select(VenueSpace).where(
        VenueSpace.id == payload.space_id, VenueSpace.venue_id == venue.id))).scalar_one_or_none()
    if not space:
        raise HTTPException(404, "Space not found")
    if await overlapping_booking(db, space.id, venue.id, payload.starts_at, payload.ends_at, include_pending=False):
        raise HTTPException(409, "That space is already booked or blocked at that time.")
    await db.execute(update(VenueQuote).where(VenueQuote.enquiry_id == enquiry.id, VenueQuote.status == "sent")
                     .values(status="superseded"))
    q = VenueQuote(enquiry_id=enquiry.id, space_id=space.id, starts_at=payload.starts_at, ends_at=payload.ends_at,
                   total_kobo=payload.total_kobo,
                   deposit_kobo=payload.deposit_kobo or default_deposit(venue, payload.total_kobo),
                   balance_due_days=payload.balance_due_days if payload.balance_due_days is not None else venue.balance_due_days,
                   refund_preset=venue.refund_preset, inclusions=payload.inclusions,
                   valid_until=utcnow() + timedelta(days=payload.valid_days), created_by_id=user.id)
    db.add(q)
    await db.flush()
    enquiry.status = "quoted"
    await post_message(db, enquiry, "venue", user, f"Quote: {naira(q.total_kobo)} for {space.name}", quote_id=q.id)
    return q


async def accept_quote(db: AsyncSession, quote: VenueQuote, organizer: User, callback_url: str | None):
    enquiry = (await db.execute(select(VenueEnquiry).where(VenueEnquiry.id == quote.enquiry_id))).scalar_one()
    if enquiry.organizer_id != organizer.id:
        raise HTTPException(403, "Not your enquiry")
    venue = (await db.execute(select(Venue).where(Venue.id == enquiry.venue_id))).scalar_one()
    if quote.status != "sent":
        # Retrying the payment of a quote already accepted (pending payment).
        pending = (await db.execute(select(VenueBooking).where(
            VenueBooking.quote_id == quote.id, VenueBooking.status == "pending_payment"))).scalar_one_or_none()
        if not pending:
            raise HTTPException(409, "This quote is no longer open.")
        booking = pending
    else:
        if as_utc(quote.valid_until) < utcnow():
            quote.status = "expired"
            raise HTTPException(409, "This quote has expired. Ask the venue for a new one.")
        if venue.status != "live":
            raise HTTPException(409, "This venue isn't taking bookings right now.")
        if not venue.deposits_enabled:
            raise HTTPException(409, "This venue can take payments once Turnup has visited it. Ask it to arrange the visit.")
        if await overlapping_booking(db, quote.space_id, venue.id, quote.starts_at, quote.ends_at):
            raise HTTPException(409, "That date has just been taken. Ask the venue for another.")
        ps = await get_platform_settings(db)
        due = as_utc(quote.starts_at) - timedelta(days=quote.balance_due_days)
        booking = VenueBooking(
            quote_id=quote.id, enquiry_id=enquiry.id, venue_id=venue.id, space_id=quote.space_id,
            organizer_id=organizer.id, starts_at=quote.starts_at, ends_at=quote.ends_at,
            total_kobo=quote.total_kobo, deposit_kobo=quote.deposit_kobo, balance_due_at=max(due, utcnow()),
            commission_percent=ps.venue_commission_percent, refund_preset=quote.refund_preset,
        )
        db.add(booking)
        await db.flush()
    payment, url = await start_split_payment(db, venue=venue, booking=booking, payer=organizer, kind="deposit",
                                             amount_kobo=booking.deposit_kobo,
                                             commission_percent=booking.commission_percent, callback_url=callback_url)
    return booking, payment, url


async def pay_balance(db: AsyncSession, booking: VenueBooking, organizer: User, amount_kobo: int | None,
                      callback_url: str | None):
    if booking.organizer_id != organizer.id:
        raise HTTPException(403, "Not your booking")
    if booking.status != "confirmed":
        raise HTTPException(409, "There's no balance to pay on this booking.")
    remaining = booking.total_kobo - booking.paid_kobo
    pending = (await db.execute(select(func.coalesce(func.sum(VenuePayment.amount_kobo), 0)).where(
        VenuePayment.booking_id == booking.id, VenuePayment.status == "pending",
        VenuePayment.created_at > utcnow() - timedelta(minutes=30)))).scalar_one()
    remaining -= int(pending)
    if remaining <= 0:
        raise HTTPException(409, "The balance is paid (or a payment is in progress).")
    amount = min(amount_kobo or remaining, remaining)
    if amount < min(100_000, remaining):  # parts of at least ₦1,000 (or what's left)
        raise HTTPException(400, "Pay at least ₦1,000 at a time.")
    venue = (await db.execute(select(Venue).where(Venue.id == booking.venue_id))).scalar_one()
    return await start_split_payment(db, venue=venue, booking=booking, payer=organizer, kind="balance",
                                     amount_kobo=amount, commission_percent=booking.commission_percent,
                                     callback_url=callback_url)


async def verify_payment(db: AsyncSession, reference: str) -> dict:
    """Browser callback after Paystack checkout (the webhook does the same independently)."""
    from app.services.paystack import PaystackConfigError, verify_transaction
    try:
        data = (await verify_transaction(reference)).get("data") or {}
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Couldn't check the payment. If you paid, it will show up shortly.")
    if data.get("status") != "success":
        return {"status": data.get("status") or "unknown"}
    if reference.startswith("sub_"):
        from app.services.plus import activate_first_payment
        await activate_first_payment(db, reference, data)
        return {"status": "ok"}
    out = await settle_venue_payment(db, reference, data)
    return {"status": out.status}


# ── Cancellations ──────────────────────────────────────────────────────────────

async def _refundable(db: AsyncSession, booking: VenueBooking) -> int:
    open_amount = (await db.execute(select(func.coalesce(func.sum(RefundRequest.amount_kobo - RefundRequest.refunded_kobo), 0)).where(
        RefundRequest.booking_id == booking.id,
        RefundRequest.status.in_(["awaiting_venue", "funded", "overdue", "suspended", "referred"])))).scalar_one()
    return max(booking.paid_kobo - booking.refunded_kobo - int(open_amount), 0)


async def cancel_by_organizer(db: AsyncSession, booking: VenueBooking, organizer: User, reason: str | None,
                              preview: bool, kind: str = "cancelled_by_organizer") -> dict:
    if kind == "cancelled_by_organizer" and booking.organizer_id != organizer.id:
        raise HTTPException(403, "Not your booking")
    if booking.status not in ("confirmed", "fully_paid", "pending_payment"):
        raise HTTPException(409, "This booking can't be cancelled.")
    ps = await get_platform_settings(db)
    paid = await _refundable(db, booking)
    pct, amount = refund_amount(paid, booking.refund_preset, as_utc(booking.starts_at), utcnow(), ps.refund_presets)
    out = {"refund_percent": pct, "refund_kobo": amount, "paid_kobo": paid, "funded_by": "venue"}
    if preview:
        return out
    if booking.status == "pending_payment":
        booking.status = "expired"
        return out | {"status": booking.status}
    booking.status = kind
    booking.cancelled_at = utcnow()
    booking.cancel_reason = reason
    await _free_enquiry(db, booking)
    if amount:
        await create_refund_request(db, booking, "organizer_cancelled" if kind == "cancelled_by_organizer"
                                    else "unpaid_balance", amount)
    await notify_venue_team(db, booking.venue_id, "venue_booking_cancelled",
                            "A booking was cancelled" + (f": refund of {naira(amount)} due" if amount else ""),
                            reason, reference_id=booking.id, reference_type="venue_booking")
    if kind != "cancelled_by_organizer":
        notify(db, booking.organizer_id, "venue_booking_cancelled",
               "Your booking was cancelled because the balance wasn't paid",
               f"Under the booking's policy you get {naira(amount)} back from the venue." if amount else None,
               reference_id=booking.id, reference_type="venue_booking")
    await db.flush()
    return out | {"status": booking.status}


async def cancel_by_venue(db: AsyncSession, booking: VenueBooking, venue: Venue, user: User, reason: str | None,
                          preview: bool) -> dict:
    if booking.status not in ("confirmed", "fully_paid"):
        raise HTTPException(409, "This booking can't be cancelled.")
    amount = await _refundable(db, booking)
    out = {"refund_percent": 100, "refund_kobo": amount, "paid_kobo": amount, "funded_by": "venue",
           "strike": True}
    if preview:
        return out
    if not (reason or "").strip():
        raise HTTPException(400, "Give the organizer a reason.")
    booking.status = "cancelled_by_venue"
    booking.cancelled_at = utcnow()
    booking.cancel_reason = reason
    await _free_enquiry(db, booking)
    if amount:
        await create_refund_request(db, booking, "venue_cancelled", amount)
    count = await add_strike(db, venue, "venue_cancelled", booking_id=booking.id, note=reason, by=user.id)
    notify(db, booking.organizer_id, "venue_booking_cancelled", f"{venue.name} cancelled your booking",
           f"Reason: {reason}. You get everything you paid back ({naira(amount)}), paid by the venue.",
           reference_id=booking.id, reference_type="venue_booking")
    await db.flush()
    return out | {"status": booking.status, "strikes_last_year": count}


async def cancel_unpaid_balance(db: AsyncSession, booking: VenueBooking, user: User, preview: bool) -> dict:
    if booking.status != "confirmed" or booking.paid_kobo >= booking.total_kobo:
        raise HTTPException(409, "The balance isn't outstanding.")
    if utcnow() < as_utc(booking.balance_due_at) + timedelta(hours=24):
        raise HTTPException(409, "You can cancel for an unpaid balance 24 hours after the due date.")
    return await cancel_by_organizer(db, booking, user, "Balance not paid by the due date", preview,
                                     kind="cancelled_unpaid_balance")


async def _free_enquiry(db: AsyncSession, booking: VenueBooking) -> None:
    await db.execute(update(VenueEnquiry).where(VenueEnquiry.id == booking.enquiry_id).values(status="closed"))


# ── Disputes ───────────────────────────────────────────────────────────────────

async def open_dispute(db: AsyncSession, booking: VenueBooking, side: str, user: User, payload) -> VenueDispute:
    import json
    ps = await get_platform_settings(db)
    if booking.status not in PAID_BOOKING:
        raise HTTPException(409, "Disputes can be opened on confirmed bookings only.")
    if utcnow() > as_utc(booking.ends_at) + timedelta(hours=ps.dispute_window_hours):
        raise HTTPException(409, f"Disputes close {ps.dispute_window_hours} hours after the booking ends.")
    if (await db.execute(select(VenueDispute.id).where(
            VenueDispute.booking_id == booking.id, VenueDispute.status == "open"))).first():
        raise HTTPException(409, "There's already an open dispute on this booking.")
    d = VenueDispute(booking_id=booking.id, opened_by_id=user.id, side=side, reason=payload.reason,
                     description=payload.description, evidence=json.dumps([str(u) for u in payload.evidence]))
    db.add(d)
    booking.status = "disputed"
    await db.flush()
    if side == "organizer":
        await notify_venue_team(db, booking.venue_id, "venue_dispute_opened", "An organizer opened a dispute",
                                payload.description[:140], reference_id=booking.id, reference_type="venue_booking")
    else:
        notify(db, booking.organizer_id, "venue_dispute_opened", "The venue opened a dispute on your booking",
               payload.description[:140], reference_id=booking.id, reference_type="venue_booking")
    for aid in (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all():
        notify(db, aid, "venue_dispute_opened", "New venue booking dispute", reference_id=d.id,
               reference_type="venue_dispute")
    return d


async def decide_dispute(db: AsyncSession, dispute: VenueDispute, admin: User, payload) -> VenueDispute:
    if dispute.status != "open":
        raise HTTPException(409, "Already decided.")
    booking = (await db.execute(select(VenueBooking).where(VenueBooking.id == dispute.booking_id))).scalar_one()
    refundable = await _refundable(db, booking)
    if payload.resolution == "full":
        amount = refundable
    elif payload.resolution == "partial":
        if not payload.refund_kobo:
            raise HTTPException(400, "Enter the partial refund amount.")
        amount = min(payload.refund_kobo, refundable)
    else:
        amount = 0
    dispute.status = "resolved"
    dispute.resolution = payload.resolution
    dispute.refund_kobo = amount
    dispute.decided_by_id = admin.id
    dispute.decision_note = payload.note
    dispute.resolved_at = utcnow()
    booking.status = "fully_paid" if booking.paid_kobo >= booking.total_kobo else "confirmed"
    if amount:
        await create_refund_request(db, booking, "dispute", amount, dispute_id=dispute.id)
    msg = f"Decision: {payload.resolution.replace('_', ' ')}" + (f", {naira(amount)} refunded by the venue" if amount else "")
    notify(db, booking.organizer_id, "venue_dispute_decided", msg, payload.note[:300],
           reference_id=booking.id, reference_type="venue_booking")
    await notify_venue_team(db, booking.venue_id, "venue_dispute_decided", msg, payload.note[:300],
                            reference_id=booking.id, reference_type="venue_booking")
    await db.flush()
    return dispute


# ── Reviews ────────────────────────────────────────────────────────────────────

async def _recompute_ratings(db: AsyncSession, venue_id: str) -> None:
    venue = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one()
    for kind in ("organizer", "guest"):
        avg, n = (await db.execute(select(func.avg(VenueReview.rating), func.count()).where(
            VenueReview.venue_id == venue_id, VenueReview.kind == kind, VenueReview.is_hidden == False))).one()  # noqa: E712
        setattr(venue, f"rating_{kind}s", round(float(avg), 2) if avg is not None else None)
        setattr(venue, f"reviews_{kind}s_count", int(n))


async def review_booking(db: AsyncSession, booking: VenueBooking, user: User, payload) -> VenueReview:
    if booking.organizer_id != user.id:
        raise HTTPException(403, "Not your booking")
    if booking.status != "completed":
        raise HTTPException(409, "You can review once the booking is completed.")
    existing = (await db.execute(select(VenueReview).where(
        VenueReview.author_id == user.id, VenueReview.booking_id == booking.id))).scalar_one_or_none()
    r = existing or VenueReview(venue_id=booking.venue_id, author_id=user.id, kind="organizer", booking_id=booking.id,
                                rating=payload.rating)
    r.rating, r.body = payload.rating, payload.body
    if not existing:
        db.add(r)
    await db.flush()
    await _recompute_ratings(db, booking.venue_id)
    return r


async def review_as_guest(db: AsyncSession, event, user: User, payload) -> VenueReview:
    from app.models.organizer import TicketOrder
    venue_id = event.venue_id or event.host_venue_id
    if not venue_id:
        raise HTTPException(400, "This event isn't linked to a venue.")
    end = as_utc(event.end_date)
    now = utcnow()
    if now < end or now > end + timedelta(days=14):
        raise HTTPException(409, "Guest reviews open when the event ends and close 14 days later.")
    attended = (await db.execute(select(TicketOrder.id).where(
        TicketOrder.event_id == event.id, TicketOrder.user_id == user.id,
        TicketOrder.checked_in_at.is_not(None)))).first()
    if not attended:
        raise HTTPException(403, "Only guests whose ticket was checked in can review the venue.")
    existing = (await db.execute(select(VenueReview).where(
        VenueReview.author_id == user.id, VenueReview.event_id == event.id))).scalar_one_or_none()
    r = existing or VenueReview(venue_id=venue_id, author_id=user.id, kind="guest", event_id=event.id,
                                rating=payload.rating)
    r.rating, r.body = payload.rating, payload.body
    if not existing:
        db.add(r)
    await db.flush()
    await _recompute_ratings(db, venue_id)
    return r


# ── Sweeps ─────────────────────────────────────────────────────────────────────

async def run_booking_sweeps(db: AsyncSession) -> dict:
    """Expire unpaid checkouts (checking Paystack first), complete finished bookings, send
    balance reminders. Run by the worker every few minutes."""
    from app.services.paystack import verify_transaction
    from app.models.venue import FeaturedSlot
    now = utcnow()
    out = {"expired": 0, "recovered": 0, "completed": 0, "reminders": 0}
    stale = (await db.execute(select(VenuePayment).where(
        VenuePayment.status == "pending", VenuePayment.created_at < now - timedelta(minutes=30)))).scalars().all()
    for p in stale:
        if settings.paystack_secret_key:
            try:
                data = (await verify_transaction(p.reference)).get("data") or {}
            except Exception:
                if now - as_utc(p.created_at) < timedelta(hours=24):
                    continue
                data = {}
            if data.get("status") == "success":
                res = await settle_venue_payment(db, p.reference, data)
                if res.status == "ok":
                    out["recovered"] += 1
                    continue
        p.status = "expired"
        if p.kind == "deposit" and p.booking_id:
            await db.execute(update(VenueBooking).where(
                VenueBooking.id == p.booking_id, VenueBooking.status == "pending_payment").values(status="expired"))
        if p.kind == "featured":
            await db.execute(update(FeaturedSlot).where(
                FeaturedSlot.payment_reference == p.reference, FeaturedSlot.status == "pending").values(status="expired"))
        out["expired"] += 1

    ps = await get_platform_settings(db)
    from app.models.venue import VenueDispute as D
    done = (await db.execute(select(VenueBooking).where(
        VenueBooking.status.in_(["confirmed", "fully_paid"]),
        VenueBooking.ends_at < now - timedelta(hours=ps.dispute_window_hours)))).scalars().all()
    for b in done:
        if (await db.execute(select(D.id).where(D.booking_id == b.id, D.status == "open"))).first():
            continue
        b.status = "completed"
        b.completed_at = now
        notify(db, b.organizer_id, "venue_review_prompt", "How was the venue? Leave a review",
               reference_id=b.id, reference_type="venue_booking")
        out["completed"] += 1

    owing = (await db.execute(select(VenueBooking).where(
        VenueBooking.status == "confirmed", VenueBooking.paid_kobo < VenueBooking.total_kobo,
        VenueBooking.balance_due_at > now))).scalars().all()
    for b in owing:
        days_left = (as_utc(b.balance_due_at) - now).days
        sent = set((b.reminders_sent or "").split(",")) - {""}
        for mark in (7, 3, 1):
            if days_left < mark and str(mark) not in sent:
                sent.add(str(mark))
                notify(db, b.organizer_id, "venue_balance_reminder",
                       f"Balance of {naira(b.total_kobo - b.paid_kobo)} due in {max(days_left, 0) + 1} day(s)",
                       "Pay through Turnup so the booking terms protect it.",
                       reference_id=b.id, reference_type="venue_booking")
                out["reminders"] += 1
                break
        b.reminders_sent = ",".join(sorted(sent))
    await db.execute(update(VenueQuote).where(VenueQuote.status == "sent", VenueQuote.valid_until < now)
                     .values(status="expired"))
    await db.commit()
    return out
