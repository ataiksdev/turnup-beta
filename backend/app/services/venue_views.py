"""Turning venue rows into API responses (plain dicts, shared by several routers)."""
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.venue import (
    Area, EnquiryMessage, RefundRequest, Venue, VenueBooking, VenueEnquiry, VenueMedia,
    VenueQuote, VenueSpace,
)
from app.services.plus import is_pro
from app.services.settings import get_platform_settings
from app.services.venue_policy import PRESET_LABELS


def _json_list(value: str | None) -> list:
    try:
        return list(json.loads(value or "[]"))
    except ValueError:
        return []


def user_brief(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.full_name,
            "avatar_url": u.avatar_url}


async def media_limits(db: AsyncSession, venue: Venue) -> dict:
    ps = await get_platform_settings(db)
    pro = is_pro(venue)
    return {"photos": ps.pro_photo_limit if pro else ps.free_photo_limit,
            "videos": ps.pro_video_limit if pro else ps.free_video_limit,
            "team_seats": ps.pro_team_seats if pro else ps.free_team_seats}


async def media_for(db: AsyncSession, venue: Venue, include_hidden: bool) -> list[dict]:
    """Media in the venue's order. Items past the plan's limit are hidden (kept, not deleted)."""
    rows = (await db.execute(select(VenueMedia).where(VenueMedia.venue_id == venue.id).order_by(
        VenueMedia.sort_order, VenueMedia.created_at))).scalars().all()
    limits = await media_limits(db, venue)
    seen = {"photo": 0, "video": 0}
    out = []
    for m in rows:
        seen[m.kind] += 1
        hidden = seen[m.kind] > limits["photos" if m.kind == "photo" else "videos"]
        if hidden and not include_hidden:
            continue
        out.append({"id": m.id, "kind": m.kind, "url": m.url, "poster_url": m.poster_url,
                    "duration_s": m.duration_s, "caption": m.caption, "space_id": m.space_id,
                    "sort_order": m.sort_order, "hidden": hidden})
    return out


def space_out(s: VenueSpace) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description,
            "capacity_seated": s.capacity_seated, "capacity_standing": s.capacity_standing,
            "setting": s.setting, "price_from_kobo": s.price_from_kobo, "price_to_kobo": s.price_to_kobo,
            "price_unit": s.price_unit, "min_hours": s.min_hours, "is_active": s.is_active,
            "sort_order": s.sort_order}


def public_price(venue: Venue, spaces: list[VenueSpace]) -> dict:
    if venue.price_display == "on_request":
        return {"display": "on_request"}
    lows = [s.price_from_kobo for s in spaces if s.is_active and s.price_from_kobo]
    highs = [s.price_to_kobo or s.price_from_kobo for s in spaces if s.is_active and s.price_from_kobo]
    if not lows:
        return {"display": "on_request"}
    out = {"display": venue.price_display, "from_kobo": min(lows)}
    if venue.price_display == "range":
        out["to_kobo"] = max(highs)
    return out


async def area_name(db: AsyncSession, venue: Venue) -> str | None:
    if venue.area_id:
        return (await db.execute(select(Area.name).where(Area.id == venue.area_id))).scalar_one_or_none()
    return venue.area_other


def capacity(spaces: list[VenueSpace]) -> int:
    return max([max(s.capacity_seated or 0, s.capacity_standing or 0) for s in spaces if s.is_active] or [0])


async def venue_card(db: AsyncSession, venue: Venue, featured: str | None = None,
                     spaces: list[VenueSpace] | None = None, distance_m: float | None = None) -> dict:
    if spaces is None:
        spaces = list((await db.execute(select(VenueSpace).where(VenueSpace.venue_id == venue.id))).scalars().all())
    return {
        "id": venue.id, "slug": venue.slug, "name": venue.name, "type": venue.type,
        "state": venue.state, "area": await area_name(db, venue), "area_id": venue.area_id,
        "cover_image": venue.cover_image, "capacity": capacity(spaces), "price": public_price(venue, spaces),
        "is_verified": venue.verification_status == "visit_passed", "is_pro": is_pro(venue),
        "featured": featured, "followers_count": venue.followers_count,
        "rating_organizers": venue.rating_organizers, "reviews_organizers_count": venue.reviews_organizers_count,
        "rating_guests": venue.rating_guests, "reviews_guests_count": venue.reviews_guests_count,
        "latitude": venue.latitude, "longitude": venue.longitude,
        "distance_m": round(distance_m) if distance_m is not None else None,
    }


def quote_out(q: VenueQuote) -> dict:
    return {"id": q.id, "space_id": q.space_id, "starts_at": q.starts_at, "ends_at": q.ends_at,
            "total_kobo": q.total_kobo, "deposit_kobo": q.deposit_kobo,
            "balance_kobo": q.total_kobo - q.deposit_kobo, "balance_due_days": q.balance_due_days,
            "refund_preset": q.refund_preset, "refund_policy": PRESET_LABELS.get(q.refund_preset),
            "inclusions": q.inclusions, "valid_until": q.valid_until, "status": q.status,
            "created_at": q.created_at}


async def message_out(db: AsyncSession, m: EnquiryMessage) -> dict:
    quote = None
    if m.quote_id:
        q = (await db.execute(select(VenueQuote).where(VenueQuote.id == m.quote_id))).scalar_one_or_none()
        quote = quote_out(q) if q else None
    return {"id": m.id, "sender_side": m.sender_side, "sender_id": m.sender_id, "body": m.body,
            "quote": quote, "flagged_contact": m.flagged_contact, "created_at": m.created_at}


async def enquiry_out(db: AsyncSession, e: VenueEnquiry, side: str, with_messages: bool = False) -> dict:
    venue = (await db.execute(select(Venue).where(Venue.id == e.venue_id))).scalar_one()
    organizer = (await db.execute(select(User).where(User.id == e.organizer_id))).scalar_one_or_none()
    space = (await db.execute(select(VenueSpace).where(VenueSpace.id == e.space_id))).scalar_one_or_none() if e.space_id else None
    last_read = e.organizer_last_read_at if side == "organizer" else e.venue_last_read_at
    other = "venue" if side == "organizer" else "organizer"
    unread_q = select(func.count()).select_from(EnquiryMessage).where(
        EnquiryMessage.enquiry_id == e.id, EnquiryMessage.sender_side.in_([other, "system"]))
    if last_read:
        unread_q = unread_q.where(EnquiryMessage.created_at > last_read)
    booking = (await db.execute(select(VenueBooking).where(VenueBooking.enquiry_id == e.id).order_by(
        VenueBooking.created_at.desc()))).scalars().first()
    out = {
        "id": e.id, "status": e.status, "starts_at": e.starts_at, "ends_at": e.ends_at,
        "guest_count": e.guest_count, "event_type": e.event_type, "budget_kobo": e.budget_kobo,
        "last_message_at": e.last_message_at, "created_at": e.created_at,
        "unread": (await db.execute(unread_q)).scalar_one(),
        "venue": {"id": venue.id, "slug": venue.slug, "name": venue.name, "cover_image": venue.cover_image,
                  "deposits_enabled": venue.deposits_enabled, "status": venue.status},
        "space": space_out(space) if space else None,
        "organizer": user_brief(organizer),
        "organizer_trusted": await trusted_organizer(db, e.organizer_id),
        "booking_id": booking.id if booking else None,
    }
    if with_messages:
        msgs = (await db.execute(select(EnquiryMessage).where(EnquiryMessage.enquiry_id == e.id).order_by(
            EnquiryMessage.created_at))).scalars().all()
        out["messages"] = [await message_out(db, m) for m in msgs]
    return out


async def trusted_organizer(db: AsyncSession, organizer_id: str) -> dict:
    """Bookings paid fully through Turnup and completed: the 'Trusted organizer' signal."""
    n = (await db.execute(select(func.count()).select_from(VenueBooking).where(
        VenueBooking.organizer_id == organizer_id, VenueBooking.status == "completed",
        VenueBooking.paid_kobo >= VenueBooking.total_kobo))).scalar_one()
    return {"completed_bookings": n, "trusted": n >= 2}


def refund_request_out(rr: RefundRequest) -> dict:
    return {"id": rr.id, "booking_id": rr.booking_id, "reason": rr.reason, "amount_kobo": rr.amount_kobo,
            "funded_kobo": rr.funded_kobo, "refunded_kobo": rr.refunded_kobo, "due_at": rr.due_at,
            "status": rr.status, "paused_at": rr.paused_at, "suspended_at": rr.suspended_at,
            "referred_at": rr.referred_at, "settled_by_organizer": rr.settled_by_organizer,
            "settled_by_venue": rr.settled_by_venue, "created_at": rr.created_at}


async def booking_out(db: AsyncSession, b: VenueBooking, side: str) -> dict:
    venue = (await db.execute(select(Venue).where(Venue.id == b.venue_id))).scalar_one()
    space = (await db.execute(select(VenueSpace).where(VenueSpace.id == b.space_id))).scalar_one()
    organizer = (await db.execute(select(User).where(User.id == b.organizer_id))).scalar_one_or_none()
    confirmed = b.status in ("confirmed", "fully_paid", "completed", "disputed")
    rrs = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b.id).order_by(
        RefundRequest.created_at))).scalars().all()
    from app.models.venue import VenueDispute
    disputes = (await db.execute(select(VenueDispute).where(VenueDispute.booking_id == b.id).order_by(
        VenueDispute.created_at))).scalars().all()
    out = {
        "id": b.id, "status": b.status, "enquiry_id": b.enquiry_id, "quote_id": b.quote_id,
        "starts_at": b.starts_at, "ends_at": b.ends_at, "total_kobo": b.total_kobo,
        "deposit_kobo": b.deposit_kobo, "paid_kobo": b.paid_kobo, "refunded_kobo": b.refunded_kobo,
        "balance_kobo": max(b.total_kobo - b.paid_kobo, 0), "balance_due_at": b.balance_due_at,
        "refund_preset": b.refund_preset, "refund_policy": PRESET_LABELS.get(b.refund_preset),
        "cancelled_at": b.cancelled_at, "cancel_reason": b.cancel_reason, "completed_at": b.completed_at,
        "event_id": b.event_id, "created_at": b.created_at,
        "venue": {"id": venue.id, "slug": venue.slug, "name": venue.name, "cover_image": venue.cover_image,
                  "status": venue.status, "address": venue.address if confirmed else None,
                  "phone": venue.phone if confirmed else None, "email": venue.email if confirmed else None},
        "space": space_out(space),
        "organizer": user_brief(organizer) | ({"email": organizer.email, "phone": organizer.phone_number}
                                               if organizer and confirmed and side == "venue" else {}),
        "refund_requests": [refund_request_out(r) for r in rrs],
        "disputes": [{"id": d.id, "side": d.side, "reason": d.reason, "description": d.description,
                      "status": d.status, "resolution": d.resolution, "refund_kobo": d.refund_kobo,
                      "decision_note": d.decision_note, "created_at": d.created_at,
                      "resolved_at": d.resolved_at} for d in disputes],
    }
    if side == "venue":
        out["commission_kobo"] = b.commission_kobo
        out["commission_percent"] = b.commission_percent
    return out


def iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
