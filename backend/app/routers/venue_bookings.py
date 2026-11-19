"""Enquiry threads, quotes, bookings, refunds and disputes, for organizers (/api/enquiries,
/api/venue-bookings) and venue teams (/api/venue-portal/venues/{id}/...)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_event_creator, get_current_user
from app.middleware.rate_limit import limiter
from app.models.event import Event
from app.models.user import User
from app.models.venue import (
    KycAccessLog, OffPlatformReport, RefundRequest, Venue, VenueBooking, VenueEnquiry, VenueQuote,
)
from app.schemas.venue import (
    CancelIn, DisputeIn, EnquiryCreate, MessageIn, PayIn, QuoteIn, ReportIn, ReviewIn,
)
from app.services import venue_booking as svc
from app.services.venue_access import notify_venue_team, require_venue_role
from app.services.venue_money import (
    LATE_REFUND, OPEN_REFUND, settle_directly, start_turnup_payment, utcnow,
)
from app.services.venue_views import booking_out, enquiry_out, refund_request_out

router = APIRouter(tags=["venue bookings"])


# ── Organizer side ─────────────────────────────────────────────────────────────

@router.post("/api/venues/{slug}/enquiries", status_code=201)
@limiter.limit("20/hour")
async def create_enquiry(request: Request, slug: str, payload: EnquiryCreate, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_event_creator)):
    venue = (await db.execute(select(Venue).where(or_(Venue.slug == slug, Venue.id == slug)))).scalar_one_or_none()
    if not venue:
        raise HTTPException(404, "Venue not found")
    e = await svc.create_enquiry(db, venue, user, payload)
    return await enquiry_out(db, e, "organizer", with_messages=True)


@router.get("/api/enquiries")
async def my_enquiries(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(VenueEnquiry).where(VenueEnquiry.organizer_id == user.id).order_by(
        VenueEnquiry.last_message_at.desc()).limit(200))).scalars().all()
    return [await enquiry_out(db, e, "organizer") for e in rows]


async def _my_enquiry(db: AsyncSession, enquiry_id: str, user: User) -> VenueEnquiry:
    e = (await db.execute(select(VenueEnquiry).where(VenueEnquiry.id == enquiry_id))).scalar_one_or_none()
    if not e or e.organizer_id != user.id:
        raise HTTPException(404, "Enquiry not found")
    return e


@router.get("/api/enquiries/{enquiry_id}")
async def get_enquiry(enquiry_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    e = await _my_enquiry(db, enquiry_id, user)
    e.organizer_last_read_at = utcnow()
    return await enquiry_out(db, e, "organizer", with_messages=True)


@router.post("/api/enquiries/{enquiry_id}/messages", status_code=201)
@limiter.limit("60/hour")
async def organizer_message(request: Request, enquiry_id: str, payload: MessageIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    e = await _my_enquiry(db, enquiry_id, user)
    await svc.post_message(db, e, "organizer", user, payload.body)
    return await enquiry_out(db, e, "organizer", with_messages=True)


@router.post("/api/enquiries/{enquiry_id}/report")
async def report_off_platform(enquiry_id: str, payload: ReportIn, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """The venue asked for payment outside Turnup. An admin reviews; upheld = a strike."""
    e = await _my_enquiry(db, enquiry_id, user)
    db.add(OffPlatformReport(enquiry_id=e.id, venue_id=e.venue_id, reporter_id=user.id,
                             message_id=payload.message_id, details=payload.details))
    for aid in (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all():
        from app.services.venue_access import notify
        notify(db, aid, "off_platform_report", "Venue reported for asking for off-platform payment",
               reference_id=e.id, reference_type="venue_enquiry")
    return {"ok": True}


@router.post("/api/quotes/{quote_id}/accept")
async def accept_quote(quote_id: str, payload: PayIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    q = (await db.execute(select(VenueQuote).where(VenueQuote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    booking, payment, url = await svc.accept_quote(db, q, user, payload.callback_url)
    return {"booking_id": booking.id, "reference": payment.reference, "authorization_url": url,
            "amount_kobo": payment.amount_kobo}


@router.post("/api/quotes/{quote_id}/decline")
async def decline_quote(quote_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    q = (await db.execute(select(VenueQuote).where(VenueQuote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    e = await _my_enquiry(db, q.enquiry_id, user)
    if q.status != "sent":
        raise HTTPException(409, "This quote is no longer open.")
    q.status = "declined"
    await svc.post_message(db, e, "system", None, "The organizer declined the quote.")
    return {"ok": True}


@router.post("/api/venue-payments/verify")
async def verify_venue_payment(reference: str = Query(..., min_length=6, max_length=60),
                               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await svc.verify_payment(db, reference)


@router.get("/api/venue-bookings")
async def my_bookings(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(VenueBooking).where(
        VenueBooking.organizer_id == user.id, VenueBooking.status != "expired").order_by(
        VenueBooking.starts_at.desc()))).scalars().all()
    return [await booking_out(db, b, "organizer") for b in rows]


async def _my_booking(db: AsyncSession, booking_id: str, user: User) -> VenueBooking:
    b = (await db.execute(select(VenueBooking).where(VenueBooking.id == booking_id))).scalar_one_or_none()
    if not b or b.organizer_id != user.id:
        raise HTTPException(404, "Booking not found")
    return b


@router.get("/api/venue-bookings/{booking_id}")
async def get_booking(booking_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await booking_out(db, await _my_booking(db, booking_id, user), "organizer")


@router.post("/api/venue-bookings/{booking_id}/pay")
async def pay_balance(booking_id: str, payload: PayIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    b = await _my_booking(db, booking_id, user)
    payment, url = await svc.pay_balance(db, b, user, payload.amount_kobo, payload.callback_url)
    return {"reference": payment.reference, "authorization_url": url, "amount_kobo": payment.amount_kobo}


@router.post("/api/venue-bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, payload: CancelIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    b = await _my_booking(db, booking_id, user)
    return await svc.cancel_by_organizer(db, b, user, payload.reason, payload.preview)


@router.post("/api/venue-bookings/{booking_id}/disputes", status_code=201)
async def organizer_dispute(booking_id: str, payload: DisputeIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    b = await _my_booking(db, booking_id, user)
    d = await svc.open_dispute(db, b, "organizer", user, payload)
    return {"id": d.id, "status": d.status}


@router.post("/api/venue-bookings/{booking_id}/review")
async def review_booking(booking_id: str, payload: ReviewIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    b = await _my_booking(db, booking_id, user)
    r = await svc.review_booking(db, b, user, payload)
    return {"id": r.id, "rating": r.rating, "body": r.body}


@router.post("/api/venue-bookings/{booking_id}/link-event")
async def link_event(booking_id: str, event_id: str = Query(...), db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    b = await _my_booking(db, booking_id, user)
    from app.routers.events import _require_event_access
    event = await _require_event_access(event_id, user, db)
    b.event_id = event.id
    event.venue_id = b.venue_id
    return {"ok": True}


@router.post("/api/refund-requests/{rr_id}/settled")
async def organizer_settled(rr_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.id == rr_id))).scalar_one_or_none()
    if not rr or rr.organizer_id != user.id:
        raise HTTPException(404, "Not found")
    if rr.status not in OPEN_REFUND:
        raise HTTPException(409, "This refund is already closed.")
    return refund_request_out(await settle_directly(db, rr, "organizer"))


@router.get("/api/refund-requests/{rr_id}/claim-pack")
async def claim_pack(rr_id: str, request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """PDF for an organizer whose refund was referred (spec 4.12)."""
    from app.services.claim_pack import build_claim_pack
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.id == rr_id))).scalar_one_or_none()
    if not rr or (rr.organizer_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Not found")
    if rr.status != "referred":
        raise HTTPException(409, "A claim pack is available once Turnup's enforcement period has ended.")
    db.add(KycAccessLog(venue_id=rr.venue_id, user_id=user.id, action="disclose",
                        ip=request.client.host if request.client else None))
    pdf = await build_claim_pack(db, rr)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="turnup-claim-{rr.id[:8]}.pdf"',
        "Cache-Control": "no-store"})


@router.post("/api/events/{event_id}/venue-review")
async def guest_review(event_id: str, payload: ReviewIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    r = await svc.review_as_guest(db, event, user, payload)
    return {"id": r.id, "rating": r.rating, "body": r.body}


# ── Venue side ─────────────────────────────────────────────────────────────────

P = "/api/venue-portal/venues/{venue_id}"


@router.get(P + "/enquiries")
async def venue_enquiries(venue_id: str, status: str | None = None, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    q = select(VenueEnquiry).where(VenueEnquiry.venue_id == v.id)
    if status:
        q = q.where(VenueEnquiry.status == status)
    rows = (await db.execute(q.order_by(VenueEnquiry.last_message_at.desc()).limit(300))).scalars().all()
    return [await enquiry_out(db, e, "venue") for e in rows]


async def _venue_enquiry(db: AsyncSession, venue_id: str, enquiry_id: str) -> VenueEnquiry:
    e = (await db.execute(select(VenueEnquiry).where(
        VenueEnquiry.id == enquiry_id, VenueEnquiry.venue_id == venue_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Enquiry not found")
    return e


@router.get(P + "/enquiries/{enquiry_id}")
async def venue_enquiry(venue_id: str, enquiry_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    e = await _venue_enquiry(db, v.id, enquiry_id)
    e.venue_last_read_at = utcnow()
    return await enquiry_out(db, e, "venue", with_messages=True)


@router.post(P + "/enquiries/{enquiry_id}/messages", status_code=201)
@limiter.limit("120/hour")
async def venue_message(request: Request, venue_id: str, enquiry_id: str, payload: MessageIn,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    e = await _venue_enquiry(db, v.id, enquiry_id)
    await svc.post_message(db, e, "venue", user, payload.body)
    return await enquiry_out(db, e, "venue", with_messages=True)


@router.post(P + "/enquiries/{enquiry_id}/quotes", status_code=201)
async def venue_quote(venue_id: str, enquiry_id: str, payload: QuoteIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    e = await _venue_enquiry(db, v.id, enquiry_id)
    await svc.send_quote(db, e, v, user, payload)
    return await enquiry_out(db, e, "venue", with_messages=True)


@router.post(P + "/enquiries/{enquiry_id}/decline")
async def venue_decline(venue_id: str, enquiry_id: str, payload: MessageIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    e = await _venue_enquiry(db, v.id, enquiry_id)
    if e.status == "booked":
        raise HTTPException(409, "This enquiry has a booking. Cancel the booking instead.")
    await svc.post_message(db, e, "venue", user, payload.body)
    e.status = "declined"
    return await enquiry_out(db, e, "venue", with_messages=True)


@router.get(P + "/bookings")
async def venue_bookings(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    rows = (await db.execute(select(VenueBooking).where(
        VenueBooking.venue_id == v.id, VenueBooking.status.notin_(["expired", "pending_payment"])).order_by(
        VenueBooking.starts_at.desc()))).scalars().all()
    return [await booking_out(db, b, "venue") for b in rows]


async def _venue_booking(db: AsyncSession, venue_id: str, booking_id: str) -> VenueBooking:
    b = (await db.execute(select(VenueBooking).where(
        VenueBooking.id == booking_id, VenueBooking.venue_id == venue_id))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Booking not found")
    return b


@router.get(P + "/bookings/{booking_id}")
async def venue_booking(venue_id: str, booking_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    return await booking_out(db, await _venue_booking(db, v.id, booking_id), "venue")


@router.post(P + "/bookings/{booking_id}/cancel")
async def venue_cancel(venue_id: str, booking_id: str, payload: CancelIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    b = await _venue_booking(db, v.id, booking_id)
    return await svc.cancel_by_venue(db, b, v, user, payload.reason, payload.preview)


@router.post(P + "/bookings/{booking_id}/cancel-unpaid")
async def venue_cancel_unpaid(venue_id: str, booking_id: str, payload: CancelIn, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    b = await _venue_booking(db, v.id, booking_id)
    return await svc.cancel_unpaid_balance(db, b, user, payload.preview)


@router.post(P + "/bookings/{booking_id}/disputes", status_code=201)
async def venue_dispute(venue_id: str, booking_id: str, payload: DisputeIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    b = await _venue_booking(db, v.id, booking_id)
    d = await svc.open_dispute(db, b, "venue", user, payload)
    return {"id": d.id, "status": d.status}


@router.get(P + "/refunds")
async def venue_refunds(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    rows = (await db.execute(select(RefundRequest).where(RefundRequest.venue_id == v.id).order_by(
        RefundRequest.created_at.desc()))).scalars().all()
    return [refund_request_out(r) for r in rows]


@router.post(P + "/refunds/{rr_id}/fund")
async def fund_refund(venue_id: str, rr_id: str, payload: PayIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """The venue pays a refund in; Turnup then sends it to the organizer."""
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    rr = (await db.execute(select(RefundRequest).where(
        RefundRequest.id == rr_id, RefundRequest.venue_id == v.id))).scalar_one_or_none()
    if not rr or rr.status not in ("awaiting_venue", *LATE_REFUND):
        raise HTTPException(404, "No unpaid refund here.")
    amount = rr.amount_kobo - rr.funded_kobo
    if amount <= 0:
        raise HTTPException(409, "Already funded.")
    payment, url = await start_turnup_payment(db, venue=v, payer=user, kind="refund_funding", amount_kobo=amount,
                                              refund_request_id=rr.id, prefix="vr",
                                              callback_url=payload.callback_url)
    return {"reference": payment.reference, "authorization_url": url, "amount_kobo": amount}


@router.post(P + "/refunds/{rr_id}/settled")
async def venue_settled(venue_id: str, rr_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    rr = (await db.execute(select(RefundRequest).where(
        RefundRequest.id == rr_id, RefundRequest.venue_id == v.id))).scalar_one_or_none()
    if not rr or rr.status not in OPEN_REFUND:
        raise HTTPException(404, "No open refund here.")
    rr = await settle_directly(db, rr, "venue")
    if not rr.settled_by_organizer:
        from app.services.venue_access import notify
        notify(db, rr.organizer_id, "venue_refund_settle_confirm",
               "The venue says your refund was settled directly",
               "If that's right, confirm it on the booking to close the case.",
               reference_id=rr.id, reference_type="refund_request")
    return refund_request_out(rr)
