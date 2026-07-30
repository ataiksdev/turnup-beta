import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_event_creator, get_current_organizer, get_current_user, get_optional_user
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import (
    EventCoHost, EventReview, EventView, EventWaitlist, TicketOrder, TicketTier,
)
from app.models.social import Notification
from app.models.social import Follow
from app.models.user import User
from app.schemas.event import (
    AttendRequest, CategoryOut, EventCreate, EventDetail, EventOut, EventUpdate,
)
from app.schemas.organizer import (
    AnalyticsOut, CheckInRequest, CheckInResult, CheckoutInitOut, CheckoutRequest,
    CoHostInviteRequest, CoHostOut, CoHostRespondRequest, DailyViewOut,
    ReviewCreate, ReviewOut, TicketOrderOut, TicketTierCreate, TicketTierOut,
    TicketTierUpdate, VerifyPaymentRequest, WaitlistEntryOut, WaitlistNotifyRequest,
    WaitlistStatusOut,
)
from app.services.email import send_ticket_email
from app.services.paystack import PaystackConfigError, initialize_transaction, verify_transaction
from app.services.tickets import confirm_order, notify_buyer, reserve_inventory
from app.schemas.user import UserSummary

router = APIRouter(prefix="/api/events", tags=["events"])


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _load():
    return [selectinload(Event.host), selectinload(Event.category)]


def _serialize(event: Event, is_saved: bool = False,
               attendance_status: str | None = None,
               is_waitlisted: bool = False) -> dict:
    return {
        "id": event.id, "title": event.title, "slug": event.slug,
        "cover_image": event.cover_image, "venue_name": event.venue_name,
        "address": event.address, "city": event.city, "country": event.country,
        "start_date": event.start_date, "end_date": event.end_date,
        "is_free": event.is_free, "price_min": event.price_min,
        "price_max": event.price_max, "currency": event.currency,
        "attendees_count": event.attendees_count, "interested_count": event.interested_count,
        "saves_count": event.saves_count, "waitlist_count": event.waitlist_count,
        "views_count": event.views_count, "waitlist_enabled": event.waitlist_enabled,
        "status": event.status, "is_featured": event.is_featured,
        "is_trending": event.is_trending, "tags": event.tags,
        "host": event.host, "category": event.category,
        "created_at": event.created_at,
        "description": event.description, "gallery": event.gallery,
        "latitude": event.latitude, "longitude": event.longitude,
        "timezone": event.timezone,
        "capacity": event.capacity, "template_id": event.template_id,
        "event_type": event.event_type, "meeting_url": event.meeting_url,
        "is_saved": is_saved, "attendance_status": attendance_status,
        "is_waitlisted": is_waitlisted,
        "review_status": event.review_status, "review_note": event.review_note,
        "created_via": event.created_via, "refund_policy": event.refund_policy,
    }


async def _user_state(event_id: str, user: User | None, db: AsyncSession):
    if not user:
        return False, None, False
    sv = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == user.id))).scalar_one_or_none()
    at = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id, EventWaitlist.user_id == user.id,
        EventWaitlist.status.in_(["waiting", "notified"])))).scalar_one_or_none()
    return sv is not None, (at.status if at else None), wl is not None


async def _require_event_access(event_id: str, user: User, db: AsyncSession) -> Event:
    """Returns event if user is host or accepted co-host."""
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id == user.id:
        return event
    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == user.id,
        EventCoHost.status == "accepted",
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(403, "Not authorized for this event")
    return event


# ── Categories ──────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Category).order_by(Category.name))).scalars().all()


# ── Listing ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[EventOut])
async def list_events(
    q: str | None = None,
    tag: str | None = None,
    city: str | None = None,
    category: str | None = None,
    event_type: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    free: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "date",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # Determine order
    _sort_map = {
        "popular":    Event.attendees_count.desc(),
        "price_asc":  Event.price_min.asc(),
        "price_desc": Event.price_min.desc(),
        "newest":     Event.created_at.desc(),
    }
    order_clause = _sort_map.get(sort, Event.start_date.asc())

    stmt = (select(Event).options(*_load())
            .where(Event.status == "published")
            .order_by(order_clause))

    if q:
        stmt = stmt.where(or_(Event.title.ilike(f"%{q}%"), Event.city.ilike(f"%{q}%"),
                              Event.tags.ilike(f"%{q}%"), Event.venue_name.ilike(f"%{q}%"),
                              Event.description.ilike(f"%{q}%")))
    if tag:
        stmt = stmt.where(Event.tags.ilike(f"%{tag}%"))
    if city:
        stmt = stmt.where(Event.city.ilike(f"%{city}%"))
    if category:
        cat = (await db.execute(select(Category).where(Category.slug == category))).scalar_one_or_none()
        if cat:
            stmt = stmt.where(Event.category_id == cat.id)
    if event_type and event_type in ("physical", "virtual", "hybrid"):
        stmt = stmt.where(Event.event_type == event_type)
    if featured is not None:
        stmt = stmt.where(Event.is_featured == featured)
    if trending is not None:
        stmt = stmt.where(Event.is_trending == trending)
    if free is not None:
        stmt = stmt.where(Event.is_free == free)
    if date_from:
        try:
            from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            stmt = stmt.where(Event.start_date >= from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            stmt = stmt.where(Event.start_date <= to_dt)
        except ValueError:
            pass

    events = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    result = []
    for e in events:
        saved, att, waitlisted = await _user_state(e.id, user, db)
        result.append(_serialize(e, saved, att, waitlisted))
    return result


@router.get("/trending", response_model=list[EventOut])
async def trending_events(
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published", Event.is_trending == True)
            .order_by(Event.attendees_count.desc()).limit(limit))
    return [_serialize(e) for e in (await db.execute(stmt)).scalars().all()]


@router.get("/featured", response_model=list[EventOut])
async def featured_events(
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published", Event.is_featured == True)
            .order_by(Event.start_date.asc()).limit(limit))
    return [_serialize(e) for e in (await db.execute(stmt)).scalars().all()]


@router.get("/for-you", response_model=list[EventOut])
async def for_you_events(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """
    Personalised recommendation feed. Scores upcoming events across eight
    signals. For organizers, preferences are inferred from their hosted events
    rather than asked during onboarding.
    """
    now = datetime.now(timezone.utc)

    candidates = (await db.execute(
        select(Event).options(*_load())
        .where(Event.status == "published", Event.start_date > now)
        .order_by(Event.start_date.asc())
        .limit(300)
    )).scalars().all()

    if not user:
        candidates.sort(key=lambda e: (e.is_trending, e.is_featured, e.attendees_count), reverse=True)
        return [_serialize(e) for e in candidates[:limit]]

    # ── Build preference profile ────────────────────────────────────────────────

    if user.role == "organizer":
        hosted = (await db.execute(
            select(Event.category_id, Event.city, Event.event_type)
            .where(Event.host_id == user.id, Event.status == "published")
        )).all()
        pref_category_ids = {row[0] for row in hosted if row[0]}
        from collections import Counter
        city_counts = Counter(row[1].strip() for row in hosted if row[1])
        user_city = city_counts.most_common(1)[0][0].lower() if city_counts else (user.city or "").lower()
        format_counts = Counter(row[2] for row in hosted if row[2])
        inferred_format = format_counts.most_common(1)[0][0] if format_counts else None
        price_sensitivity = user.price_sensitivity
        goes_out_when = user.goes_out_when
    else:
        raw_prefs = [p.strip() for p in (user.category_preferences or "").split(",") if p.strip()]
        pref_category_ids: set[str] = set()
        if raw_prefs:
            cats = (await db.execute(select(Category).where(Category.slug.in_(raw_prefs)))).scalars().all()
            pref_category_ids = {c.id for c in cats}

        saved_ids_all = {
            r[0] for r in (await db.execute(
                select(EventSave.event_id).where(EventSave.user_id == user.id)
            )).all()
        }
        if saved_ids_all:
            saved_cat_ids = {
                r[0] for r in (await db.execute(
                    select(Event.category_id).where(
                        Event.id.in_(saved_ids_all), Event.category_id.isnot(None)
                    )
                )).all()
                if r[0]
            }
            pref_category_ids = pref_category_ids | saved_cat_ids

        user_city = (user.city or (user.location or "").split(",")[0]).strip().lower()
        inferred_format = user.event_format_pref
        price_sensitivity = user.price_sensitivity
        goes_out_when = user.goes_out_when

    # ── Signals shared by both roles ────────────────────────────────────────────

    attended_ids = {
        r[0] for r in (await db.execute(
            select(EventAttendee.event_id).where(EventAttendee.user_id == user.id)
        )).all()
    }
    saved_ids = {
        r[0] for r in (await db.execute(
            select(EventSave.event_id).where(EventSave.user_id == user.id)
        )).all()
    }
    excluded_ids = attended_ids | saved_ids

    history_tags_rows = (await db.execute(
        select(Event.tags).where(Event.id.in_(attended_ids), Event.tags.isnot(None))
    )).scalars().all()
    user_tags: set[str] = set()
    for row in history_tags_rows:
        user_tags.update(t.strip().lower() for t in row.split(",") if t.strip())

    if saved_ids:
        saved_tags_rows = (await db.execute(
            select(Event.tags).where(Event.id.in_(saved_ids), Event.tags.isnot(None))
        )).scalars().all()
        for row in saved_tags_rows:
            user_tags.update(t.strip().lower() for t in row.split(",") if t.strip())

    followed_ids = {
        r[0] for r in (await db.execute(
            select(Follow.following_id).where(Follow.follower_id == user.id)
        )).all()
    }
    social_event_ids: set[str] = set()
    if followed_ids:
        social_event_ids = {
            r[0] for r in (await db.execute(
                select(EventAttendee.event_id).where(
                    EventAttendee.user_id.in_(followed_ids),
                    EventAttendee.status == "going",
                )
            )).all()
        }

    if not price_sensitivity:
        paid_prices = (await db.execute(
            select(TicketOrder.unit_price).where(
                TicketOrder.user_id == user.id,
                TicketOrder.status == "confirmed",
                TicketOrder.unit_price > 0,
            )
        )).scalars().all()
        max_spend = max(paid_prices, default=0.0)
        prefers_free = max_spend == 0 and user.events_attended < 3
    else:
        paid_prices = []
        max_spend = {"free": 0, "budget": 5000, "mid": 20000, "any": 9999999}.get(price_sensitivity, 0)
        prefers_free = price_sensitivity == "free"

    # ── Score candidates ────────────────────────────────────────────────────────

    scored: list[tuple[float, Event]] = []
    for e in candidates:
        if e.id in excluded_ids:
            continue
        score = 0.0

        if e.category_id and e.category_id in pref_category_ids:
            score += 3.0

        if user_city:
            e_city = e.city.lower()
            if user_city in e_city or e_city in user_city:
                score += 2.0

        if e.is_free:
            score += 1.5 if prefers_free else 0.5
        elif price_sensitivity == "any":
            score += 1.0
        elif max_spend > 0 and e.price_min is not None and e.price_min <= max_spend * 1.3:
            score += 1.5

        if inferred_format and inferred_format != "both":
            if e.event_type == inferred_format:
                score += 1.5
            elif e.event_type != "hybrid":
                score -= 0.5

        if goes_out_when and goes_out_when != "any":
            event_dow = e.start_date.weekday()
            is_weekend = event_dow >= 4
            if goes_out_when == "weekends" and is_weekend:
                score += 1.0
            elif goes_out_when == "weekdays" and not is_weekend:
                score += 1.0

        if e.id in social_event_ids:
            score += 2.0

        if e.tags and user_tags:
            e_tags = {t.strip().lower() for t in e.tags.split(",") if t.strip()}
            score += len(e_tags & user_tags) * 0.8

        if e.is_trending:
            score += 0.8
        if e.is_featured:
            score += 0.5

        score += min(e.attendees_count / 50.0, 1.0)

        days_away = max((e.start_date.replace(tzinfo=timezone.utc) - now).days, 0)
        if days_away <= 7:
            score += 0.5

        score += (hash(f"{user.id}:{e.id}") % 100) / 1000.0

        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    for _, e in scored[:limit]:
        sv, at, wl = await _user_state(e.id, user, db)
        result.append(_serialize(e, sv, at, wl))

    if len(result) < limit:
        seen = {r["id"] for r in result} | excluded_ids
        fallback = [e for e in candidates if e.id not in seen]
        fallback.sort(key=lambda e: (e.is_trending, e.attendees_count), reverse=True)
        for e in fallback[: limit - len(result)]:
            sv, at, wl = await _user_state(e.id, user, db)
            result.append(_serialize(e, sv, at, wl))

    return result


@router.post("/webhooks/paystack", status_code=200)
async def paystack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Server-side payment reconciliation, independent of the buyer's browser. If a buyer
    pays but their callback never fires (closed tab, crash, flaky network), this is what
    still confirms the order. Idempotent against verify-payment via confirm_order()'s atomic
    pending->confirmed flip -- whichever of the two arrives first wins, the other is a no-op."""
    raw = await request.body()
    if not settings.paystack_secret_key:
        raise HTTPException(503, "Paystack not configured")
    expected = hmac.new(settings.paystack_secret_key.encode(), raw, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-paystack-signature", "")):
        raise HTTPException(401, "Invalid signature")

    payload = json.loads(raw)
    if payload.get("event") != "charge.success":
        return {"status": "ignored"}

    reference = payload.get("data", {}).get("reference")
    orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == reference))).scalars().all()
    if not orders:
        return {"status": "unknown_reference"}

    channel = payload["data"].get("channel")
    for order in orders:
        row = await confirm_order(db, order.id, channel)
        if not row:
            continue  # already confirmed via the client's verify-payment call
        event = (await db.execute(select(Event).where(Event.id == row.event_id))).scalar_one_or_none()
        t = await _get_tier(row.tier_id, row.event_id, db)
        buyer = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
        await _auto_rsvp(event, buyer, db)
        await notify_buyer(db, row, event, kind="confirmed")
        background_tasks.add_task(
            send_ticket_email, to=(buyer.email if buyer else "") or "", order_id=row.id,
            ticket_code=row.ticket_code, event_title=event.title,
            event_date=event.start_date, event_venue=event.venue_name,
            event_address=event.address, tier_name=t.name,
            quantity=row.quantity, total_price=row.total_price,
        )
    return {"status": "ok"}


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = select(Event).options(*_load()).where(
        or_(Event.id == event_id, Event.slug == event_id))
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    # Only show drafts to their host
    if event.status == "draft":
        if not user or event.host_id != user.id:
            raise HTTPException(404, "Event not found")
    saved, att, waitlisted = await _user_state(event.id, user, db)

    # Per-event avg rating
    ev_review_agg = (await db.execute(
        select(func.avg(EventReview.rating), func.count(EventReview.id))
        .where(EventReview.event_id == event.id)
    )).one()
    event_avg_rating = round(float(ev_review_agg[0]), 1) if ev_review_agg[0] else None
    event_review_count = ev_review_agg[1] or 0

    # Host aggregate stats
    host_review_agg = (await db.execute(
        select(func.avg(EventReview.rating), func.count(EventReview.id))
        .join(Event, Event.id == EventReview.event_id)
        .where(Event.host_id == event.host_id)
    )).one()
    host_avg_rating = round(float(host_review_agg[0]), 1) if host_review_agg[0] else None
    host_review_count = host_review_agg[1] or 0
    host_events_hosted = (await db.execute(
        select(func.count(Event.id))
        .where(Event.host_id == event.host_id, Event.status == "published")
    )).scalar() or 0

    data = _serialize(event, saved, att, waitlisted)
    data["avg_rating"] = event_avg_rating
    data["review_count"] = event_review_count
    h = event.host
    data["host"] = {
        "id": h.id, "username": h.username, "full_name": h.full_name,
        "display_name": h.display_name, "bio": h.bio,
        "avatar_url": h.avatar_url, "is_verified": h.is_verified,
        "role": h.role, "followers_count": h.followers_count,
        "events_hosted": host_events_hosted,
        "avg_rating": host_avg_rating, "review_count": host_review_count,
    }
    return data


# ── Create / Update ─────────────────────────────────────────────────────────────

@router.post("", response_model=EventDetail, status_code=201)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_event_creator),
):
    data = payload.model_dump()
    template_id = data.pop("template_id", None)

    # If creating from template, merge template defaults (payload fields take precedence)
    if template_id:
        from app.models.organizer import EventTemplate
        tmpl = (await db.execute(select(EventTemplate).where(
            EventTemplate.id == template_id,
            EventTemplate.organizer_id == user.id,
        ))).scalar_one_or_none()
        if tmpl:
            defaults = json.loads(tmpl.template_data)
            for k, v in defaults.items():
                if k in data and data[k] is None:
                    data[k] = v

    # Admins bypass approval; organizer/moderator submissions go to review as drafts.
    if user.role == "admin":
        data["review_status"] = "approved"
    else:
        data["review_status"] = "pending"
        data["status"] = "draft"

    eid = str(uuid.uuid4())
    event = Event(id=eid, slug=_slugify(payload.title, eid),
                  host_id=user.id, template_id=template_id, **data)
    db.add(event)
    await db.flush()
    if event.status == "published":
        await db.execute(update(User).where(User.id == user.id).values(
            events_hosted=User.events_hosted + 1))
    stmt = select(Event).options(*_load()).where(Event.id == eid)
    return _serialize((await db.execute(stmt)).scalar_one())


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)
    was_draft = event.status == "draft"
    old_status = event.status
    old_start = event.start_date

    changes = payload.model_dump(exclude_none=True)

    if user.role != "admin":
        if changes.get("status") == "published" and event.review_status != "approved":
            raise HTTPException(403, "This event is awaiting admin approval before it can be published.")
        # Editing a rejected (or still-pending) submission resubmits it for review.
        if changes and event.review_status in ("pending", "rejected"):
            event.review_status = "pending"
            event.review_note = None

    for k, v in changes.items():
        setattr(event, k, v)

    # Increment events_hosted counter when publishing for the first time
    if was_draft and event.status == "published":
        await db.execute(update(User).where(User.id == user.id).values(
            events_hosted=User.events_hosted + 1))

    # Notify attendees on cancellation or reschedule
    new_status = changes.get("status")
    new_start  = changes.get("start_date")
    notify_type = None
    notify_title = None
    notify_body  = None

    if new_status == "cancelled" and old_status != "cancelled":
        notify_type  = "event_update"
        notify_title = f"Event cancelled: {event.title}"
        notify_body  = f'"{event.title}" has been cancelled by the organizer.'
    elif new_start and old_start and str(new_start) != str(old_start):
        notify_type  = "event_update"
        notify_title = f"Event rescheduled: {event.title}"
        notify_body  = f'"{event.title}" has been moved to a new date. Check the event page for details.'

    if notify_type:
        attendee_rows = (await db.execute(
            select(EventAttendee.user_id)
            .where(EventAttendee.event_id == event_id,
                   EventAttendee.user_id != user.id)
        )).scalars().all()
        for attendee_id in attendee_rows:
            db.add(Notification(
                id=str(uuid.uuid4()),
                user_id=attendee_id,
                type=notify_type,
                title=notify_title,
                body=notify_body,
                reference_id=event_id,
                reference_type="event",
                actor_id=user.id,
            ))

    await db.flush()
    stmt = select(Event).options(*_load()).where(Event.id == event_id)
    return _serialize((await db.execute(stmt)).scalar_one())


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        raise HTTPException(403, "Only the host can delete this event")
    await db.delete(event)


# ── RSVP (attendees) ────────────────────────────────────────────────────────────

@router.post("/{event_id}/attend")
async def attend(
    event_id: str,
    payload: AttendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event or event.status != "published":
        raise HTTPException(404, "Event not found")

    existing = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()

    # Capacity check for "going" RSVPs
    if payload.status == "going" and not existing:
        if event.capacity and event.attendees_count >= event.capacity:
            if event.waitlist_enabled:
                return await _join_waitlist_internal(event, user, db)
            raise HTTPException(409, "Event is at capacity")

    if existing:
        old_status = existing.status
        if old_status == "going":
            event.attendees_count = max(0, event.attendees_count - 1)
        else:
            event.interested_count = max(0, event.interested_count - 1)
        existing.status = payload.status
    else:
        db.add(EventAttendee(id=str(uuid.uuid4()), user_id=user.id,
                             event_id=event_id, status=payload.status))
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=User.events_attended + 1))

    if payload.status == "going":
        event.attendees_count += 1
    else:
        event.interested_count += 1

    # Notify host when someone RSVPs going (skip if user is the host)
    if payload.status == "going" and event.host_id != user.id:
        db.add(Notification(
            id=str(uuid.uuid4()), user_id=event.host_id, type="going",
            title=f"{user.full_name} is going to your event",
            body=event.title,
            reference_id=event_id, reference_type="event", actor_id=user.id,
        ))

    return {"status": payload.status, "attendees_count": event.attendees_count,
            "interested_count": event.interested_count}


async def _join_waitlist_internal(event: Event, user: User, db: AsyncSession) -> dict:
    existing_wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event.id,
        EventWaitlist.user_id == user.id,
        EventWaitlist.status.in_(["waiting", "notified"]),
    ))).scalar_one_or_none()
    if existing_wl:
        return {"status": "waitlisted", "position": existing_wl.position,
                "waitlist_count": event.waitlist_count}
    position = event.waitlist_count + 1
    db.add(EventWaitlist(
        id=str(uuid.uuid4()),
        event_id=event.id,
        user_id=user.id,
        position=position,
    ))
    event.waitlist_count += 1
    return {"status": "waitlisted", "position": position,
            "waitlist_count": event.waitlist_count}


@router.delete("/{event_id}/attend")
async def remove_attendance(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Not attending")
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if att.status == "going":
        event.attendees_count = max(0, event.attendees_count - 1)
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=max(0, User.events_attended - 1)))
    else:
        event.interested_count = max(0, event.interested_count - 1)
    await db.delete(att)
    return {"status": None}


# ── Save ─────────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/save")
async def toggle_save(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    existing = (await db.execute(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.user_id == user.id))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        event.saves_count = max(0, event.saves_count - 1)
        return {"saved": False}
    db.add(EventSave(id=str(uuid.uuid4()), user_id=user.id, event_id=event_id))
    event.saves_count += 1
    return {"saved": True}


# ── Attendees list ────────────────────────────────────────────────────────────────

@router.get("/{event_id}/attendees")
async def get_attendees(
    event_id: str,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = (select(EventAttendee).options(selectinload(EventAttendee.user))
            .where(EventAttendee.event_id == event_id))
    if status:
        stmt = stmt.where(EventAttendee.status == status)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [{"user": UserSummary.model_validate(r.user), "status": r.status,
             "created_at": r.created_at} for r in rows]


# ── Views / Analytics ─────────────────────────────────────────────────────────────

@router.post("/{event_id}/views", status_code=204)
async def record_view(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        return
    ip = request.client.host if request.client else None
    db.add(EventView(
        id=str(uuid.uuid4()),
        event_id=event_id,
        user_id=user.id if user else None,
        ip_address=ip,
    ))
    event.views_count += 1


@router.get("/{event_id}/analytics", response_model=AnalyticsOut)
async def get_analytics(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)

    # Daily views — last 14 days
    since = datetime.now(timezone.utc) - timedelta(days=14)
    views_result = await db.execute(
        select(
            func.date(EventView.viewed_at).label("date"),
            func.count(EventView.id).label("views"),
        )
        .where(EventView.event_id == event_id, EventView.viewed_at >= since)
        .group_by(func.date(EventView.viewed_at))
        .order_by(func.date(EventView.viewed_at))
    )
    daily_views = [DailyViewOut(date=str(r.date), views=r.views) for r in views_result]

    unique_views = (await db.execute(
        select(func.count(func.distinct(EventView.ip_address)))
        .where(EventView.event_id == event_id)
    )).scalar() or 0

    rsvp_going = (await db.execute(
        select(func.count(EventAttendee.id))
        .where(EventAttendee.event_id == event_id, EventAttendee.status == "going")
    )).scalar() or 0

    rsvp_interested = (await db.execute(
        select(func.count(EventAttendee.id))
        .where(EventAttendee.event_id == event_id, EventAttendee.status == "interested")
    )).scalar() or 0

    orders_result = await db.execute(
        select(func.count(TicketOrder.id), func.sum(TicketOrder.total_price))
        .where(TicketOrder.event_id == event_id, TicketOrder.status == "confirmed")
    )
    orders_row = orders_result.one()
    orders_count = orders_row[0] or 0
    revenue = float(orders_row[1] or 0)

    waitlist_count = (await db.execute(
        select(func.count(EventWaitlist.id))
        .where(EventWaitlist.event_id == event_id,
               EventWaitlist.status.in_(["waiting", "notified"]))
    )).scalar() or 0

    return AnalyticsOut(
        event_id=event_id,
        total_views=event.views_count,
        unique_views=unique_views,
        rsvp_going=rsvp_going,
        rsvp_interested=rsvp_interested,
        saves_count=event.saves_count,
        waitlist_count=waitlist_count,
        ticket_orders_count=orders_count,
        estimated_revenue=revenue,
        daily_views=daily_views,
    )


# ── Ticket tiers ──────────────────────────────────────────────────────────────────

@router.get("/{event_id}/tickets", response_model=list[TicketTierOut])
async def list_ticket_tiers(event_id: str, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TicketTier)
        .where(TicketTier.event_id == event_id, TicketTier.is_active == True)
        .order_by(TicketTier.price.asc())
    )
    tiers = result.scalars().all()
    return [_tier_out(t) for t in tiers]


@router.post("/{event_id}/tickets", response_model=TicketTierOut, status_code=201)
async def create_ticket_tier(
    event_id: str,
    payload: TicketTierCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = TicketTier(id=str(uuid.uuid4()), event_id=event_id, **payload.model_dump())
    db.add(t)
    await db.flush()
    return _tier_out(t)


@router.patch("/{event_id}/tickets/{tier_id}", response_model=TicketTierOut)
async def update_ticket_tier(
    event_id: str,
    tier_id: str,
    payload: TicketTierUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = await _get_tier(tier_id, event_id, db)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    await db.flush()
    return _tier_out(t)


@router.delete("/{event_id}/tickets/{tier_id}", status_code=204)
async def delete_ticket_tier(
    event_id: str,
    tier_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    t = await _get_tier(tier_id, event_id, db)
    if t.quantity_sold > 0:
        raise HTTPException(409, "Cannot delete a tier with existing orders")
    await db.delete(t)


@router.post("/{event_id}/tickets/checkout", response_model=CheckoutInitOut)
async def checkout_tickets(
    event_id: str,
    payload: CheckoutRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Buy one or more ticket tiers in a single checkout. All resulting orders share one
    `payment_reference` — that's the cart grouping (no separate cart table needed).
    For paid carts: reserves inventory, creates pending orders, returns Paystack init data
    for ONE transaction covering the summed total. For all-free carts: confirms immediately.
    """
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    # Idempotency replay: a retried submit of the same checkout intent returns the same
    # reservation instead of creating a duplicate one.
    if payload.idempotency_key:
        existing = (await db.execute(select(TicketOrder).where(
            TicketOrder.user_id == user.id,
            TicketOrder.idempotency_key == payload.idempotency_key,
        ))).scalars().all()
        if existing:
            total = sum(o.total_price for o in existing)
            return CheckoutInitOut(
                order_ids=[o.id for o in existing],
                payment_reference=existing[0].payment_reference,
                paystack_public_key=settings.paystack_public_key if total > 0 else "",
                amount_kobo=int(total * 100),
                email=user.email or "",
                is_free=(total == 0),
            )

    now = datetime.now(timezone.utc)
    reference = f"turnup-{uuid.uuid4().hex[:16]}"
    orders: list[TicketOrder] = []
    tiers_by_order: dict[str, TicketTier] = {}

    for item in payload.items:
        t = await _get_tier(item.tier_id, event_id, db)
        if not t.is_active:
            raise HTTPException(400, f"'{t.name}' is not available")
        if t.sale_start and now < t.sale_start:
            raise HTTPException(400, f"Sales for '{t.name}' have not started yet")
        if t.sale_end and now > t.sale_end:
            raise HTTPException(400, f"Sales for '{t.name}' have ended")
        if item.quantity > t.max_per_order:
            raise HTTPException(400, f"Maximum {t.max_per_order} '{t.name}' tickets per order")

        # Reserves inventory atomically -- raises 409 if not enough left. Any failure here
        # rolls back the whole request (including reservations already taken earlier in this
        # same loop) via get_db's rollback-on-exception, so a cart never partially reserves.
        await reserve_inventory(db, t, item.quantity)

        order = TicketOrder(
            id=str(uuid.uuid4()), user_id=user.id, event_id=event_id, tier_id=t.id,
            quantity=item.quantity, unit_price=t.price, total_price=t.price * item.quantity,
            status="pending", payment_reference=reference,
            idempotency_key=payload.idempotency_key,
        )
        db.add(order)
        orders.append(order)
        tiers_by_order[order.id] = t

    await db.flush()
    total = sum(o.total_price for o in orders)

    if total == 0:
        for order in orders:
            row = await confirm_order(db, order.id, payment_channel=None)
            await notify_buyer(db, row, event, kind="confirmed")
            background_tasks.add_task(
                send_ticket_email, to=user.email or "", order_id=row.id,
                ticket_code=row.ticket_code, event_title=event.title,
                event_date=event.start_date, event_venue=event.venue_name,
                event_address=event.address, tier_name=tiers_by_order[row.id].name,
                quantity=row.quantity, total_price=0.0,
            )
        await _auto_rsvp(event, user, db)
        return CheckoutInitOut(
            order_ids=[o.id for o in orders], payment_reference=reference,
            paystack_public_key="", amount_kobo=0, email=user.email or "", is_free=True,
        )

    # Paid — init one Paystack transaction for the summed total (amount in kobo)
    amount_kobo = int(total * 100)
    email = user.email or f"{user.username}@turnup.app"
    try:
        await initialize_transaction(
            email=email, amount_kobo=amount_kobo, reference=reference,
            metadata={"order_ids": [o.id for o in orders], "event_id": event_id},
        )
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Payment gateway unavailable. Please try again.")

    return CheckoutInitOut(
        order_ids=[o.id for o in orders], payment_reference=reference,
        paystack_public_key=settings.paystack_public_key, amount_kobo=amount_kobo, email=email,
    )


async def _auto_rsvp(event: Event, user: User, db: AsyncSession) -> None:
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


def _order_out(order: TicketOrder, tier_name: str) -> TicketOrderOut:
    return TicketOrderOut(
        id=order.id, event_id=order.event_id, tier_id=order.tier_id, tier_name=tier_name,
        quantity=order.quantity, unit_price=order.unit_price, total_price=order.total_price,
        status=order.status, payment_reference=order.payment_reference,
        ticket_code=order.ticket_code, checked_in_at=order.checked_in_at,
        created_at=order.created_at,
    )


@router.post("/{event_id}/tickets/verify-payment", response_model=list[TicketOrderOut])
async def verify_payment(
    event_id: str,
    payload: VerifyPaymentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Verify a Paystack payment and confirm every pending order sharing this reference
    (a checkout may have created several, one per tier line)."""
    orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == payload.reference,
        TicketOrder.user_id == user.id,
        TicketOrder.status == "pending",
    ))).scalars().all()
    if not orders:
        raise HTTPException(404, "Order not found or already processed")

    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    try:
        ps_resp = await verify_transaction(payload.reference)
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Could not verify payment. Please contact support.")

    ps_data = ps_resp.get("data", {})
    if ps_data.get("status") != "success":
        raise HTTPException(402, "Payment not completed")

    confirmed: list[TicketOrderOut] = []
    for order in orders:
        row = await confirm_order(db, order.id, ps_data.get("channel"))
        if not row:
            continue  # already confirmed by the webhook -- no-op, avoids double email/notify
        t = await _get_tier(row.tier_id, event_id, db)
        await notify_buyer(db, row, event, kind="confirmed")
        background_tasks.add_task(
            send_ticket_email, to=user.email or "", order_id=row.id,
            ticket_code=row.ticket_code, event_title=event.title,
            event_date=event.start_date, event_venue=event.venue_name,
            event_address=event.address, tier_name=t.name,
            quantity=row.quantity, total_price=row.total_price,
        )
        confirmed.append(_order_out(row, t.name))

    if confirmed:
        await _auto_rsvp(event, user, db)
    return confirmed


def _tier_out(t: TicketTier) -> TicketTierOut:
    available = (t.quantity - t.quantity_sold) if t.quantity is not None else None
    return TicketTierOut(
        id=t.id, event_id=t.event_id, name=t.name, description=t.description,
        price=t.price, currency=t.currency, quantity=t.quantity,
        quantity_sold=t.quantity_sold, available=available,
        max_per_order=t.max_per_order, is_active=t.is_active,
        sale_start=t.sale_start, sale_end=t.sale_end, created_at=t.created_at,
    )


async def _get_tier(tier_id: str, event_id: str, db: AsyncSession) -> TicketTier:
    t = (await db.execute(select(TicketTier).where(
        TicketTier.id == tier_id, TicketTier.event_id == event_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Ticket tier not found")
    return t


# ── Co-hosts ──────────────────────────────────────────────────────────────────────

@router.get("/{event_id}/cohosts", response_model=list[CoHostOut])
async def list_cohosts(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EventCoHost)
        .options(selectinload(EventCoHost.user))
        .where(EventCoHost.event_id == event_id)
    )
    return [_cohost_out(ch) for ch in result.scalars().all()]


@router.post("/{event_id}/cohosts", response_model=CoHostOut, status_code=201)
async def invite_cohost(
    event_id: str,
    payload: CoHostInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        raise HTTPException(403, "Only the host can invite co-hosts")

    invitee = (await db.execute(select(User).where(
        User.username == payload.username.lower()))).scalar_one_or_none()
    if not invitee:
        raise HTTPException(404, f"User @{payload.username} not found")
    if invitee.id == user.id:
        raise HTTPException(400, "Cannot invite yourself as co-host")

    existing = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == invitee.id,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"@{payload.username} already has a co-host entry for this event")

    ch = EventCoHost(
        id=str(uuid.uuid4()),
        event_id=event_id,
        user_id=invitee.id,
    )
    db.add(ch)

    # In-app notification
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=invitee.id,
        type="event_invite",
        title=f"Co-host invitation: {event.title}",
        body=f"@{user.username} invited you to co-host \"{event.title}\"",
        reference_id=event_id,
        reference_type="event",
        actor_id=user.id,
    ))
    await db.flush()
    await db.refresh(ch)
    ch.user = invitee
    return _cohost_out(ch)


@router.delete("/{event_id}/cohosts/{cohost_user_id}", status_code=204)
async def remove_cohost(
    event_id: str,
    cohost_user_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id and user.id != cohost_user_id:
        raise HTTPException(403, "Not authorized")

    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == cohost_user_id,
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "Co-host entry not found")
    await db.delete(ch)


@router.post("/{event_id}/cohosts/respond", status_code=200)
async def respond_to_cohost(
    event_id: str,
    payload: CoHostRespondRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event_id,
        EventCoHost.user_id == user.id,
        EventCoHost.status == "invited",
    ))).scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "No pending co-host invitation for this event")

    ch.status = "accepted" if payload.accept else "declined"
    ch.responded_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": ch.status}


def _cohost_out(ch: EventCoHost) -> CoHostOut:
    return CoHostOut(
        id=ch.id,
        user_id=ch.user_id,
        username=ch.user.username,
        full_name=ch.user.full_name,
        avatar_url=ch.user.avatar_url,
        status=ch.status,
        invited_at=ch.invited_at,
        responded_at=ch.responded_at,
    )


# ── Waitlist ──────────────────────────────────────────────────────────────────────

@router.post("/{event_id}/waitlist")
async def join_waitlist(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(
        Event.id == event_id, Event.status == "published"))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.waitlist_enabled:
        raise HTTPException(400, "This event does not have a waitlist")
    return await _join_waitlist_internal(event, user, db)


@router.delete("/{event_id}/waitlist", status_code=204)
async def leave_waitlist(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id,
        EventWaitlist.user_id == user.id,
    ))).scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Not on the waitlist")
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    await db.delete(wl)
    event.waitlist_count = max(0, event.waitlist_count - 1)


@router.get("/{event_id}/waitlist/status", response_model=WaitlistStatusOut)
async def waitlist_status(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wl = (await db.execute(select(EventWaitlist).where(
        EventWaitlist.event_id == event_id, EventWaitlist.user_id == user.id))).scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Not on the waitlist")
    ahead = (await db.execute(
        select(func.count(EventWaitlist.id))
        .where(EventWaitlist.event_id == event_id,
               EventWaitlist.status == "waiting",
               EventWaitlist.position < wl.position)
    )).scalar() or 0
    return WaitlistStatusOut(position=wl.position, status=wl.status, total_ahead=ahead)


@router.get("/{event_id}/waitlist", response_model=list[WaitlistEntryOut])
async def list_waitlist(
    event_id: str,
    status: str | None = "waiting",
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_event_access(event_id, user, db)
    stmt = (
        select(EventWaitlist)
        .options(selectinload(EventWaitlist.user))
        .where(EventWaitlist.event_id == event_id)
        .order_by(EventWaitlist.position.asc())
    )
    if status:
        stmt = stmt.where(EventWaitlist.status == status)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [
        WaitlistEntryOut(
            id=w.id, user_id=w.user_id,
            username=w.user.username, full_name=w.user.full_name,
            avatar_url=w.user.avatar_url, position=w.position,
            status=w.status, created_at=w.created_at, notified_at=w.notified_at,
        )
        for w in rows
    ]


@router.post("/{event_id}/waitlist/notify")
async def notify_waitlist(
    event_id: str,
    payload: WaitlistNotifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EventWaitlist)
        .options(selectinload(EventWaitlist.user))
        .where(EventWaitlist.event_id == event_id, EventWaitlist.status == "waiting")
        .order_by(EventWaitlist.position.asc())
        .limit(payload.count)
    )
    entries = result.scalars().all()
    notified = []
    for entry in entries:
        entry.status = "notified"
        entry.notified_at = now
        # In-app notification
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=entry.user_id,
            type="event_invite",
            title=f"You're off the waitlist! {event.title}",
            body=f"A spot opened up for \"{event.title}\". Register now before it's taken!",
            reference_id=event_id,
            reference_type="event",
            actor_id=user.id,
        ))
        notified.append(entry.user.username)
    await db.flush()
    return {"notified": notified, "count": len(notified)}


# ── Check-in ─────────────────────────────────────────────────────────────────

@router.post("/{event_id}/checkin", response_model=CheckInResult)
async def check_in_ticket(
    event_id: str,
    payload: CheckInRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Validate and mark a ticket as checked in. Only the event host can call this."""
    event = (await db.execute(
        select(Event).where(Event.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.host_id != user.id:
        # Also allow co-hosts
        cohost = (await db.execute(
            select(EventCoHost).where(
                EventCoHost.event_id == event_id,
                EventCoHost.user_id == user.id,
                EventCoHost.status == "accepted",
            )
        )).scalar_one_or_none()
        if not cohost:
            raise HTTPException(403, "Only the event host or a co-host can check in attendees")

    order = (await db.execute(
        select(TicketOrder)
        .options(selectinload(TicketOrder.tier), selectinload(TicketOrder.user))
        .where(
            TicketOrder.ticket_code == payload.ticket_code,
            TicketOrder.event_id == event_id,
        )
    )).scalar_one_or_none()

    if not order:
        raise HTTPException(404, "Ticket not found for this event")
    if order.status != "confirmed":
        raise HTTPException(400, f"Ticket is not confirmed (status: {order.status})")
    if order.checked_in_at is not None:
        raise HTTPException(409, "Ticket already checked in")

    order.checked_in_at = datetime.now(timezone.utc)
    await db.flush()

    attendee_name = (
        order.user.display_name or order.user.full_name or order.user.username
        if order.user else "Attendee"
    )

    return CheckInResult(
        order_id=order.id,
        ticket_code=order.ticket_code,
        attendee_name=attendee_name,
        tier_name=order.tier.name,
        quantity=order.quantity,
        checked_in_at=order.checked_in_at,
    )


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/{event_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EventReview)
        .options(selectinload(EventReview.user))
        .where(EventReview.event_id == event_id)
        .order_by(EventReview.created_at.desc())
    )
    reviews = result.scalars().all()
    return [
        ReviewOut(
            id=r.id, event_id=r.event_id, user_id=r.user_id,
            username=r.user.username, full_name=r.user.full_name,
            avatar_url=r.user.avatar_url, rating=r.rating,
            body=r.body, created_at=r.created_at,
        )
        for r in reviews
    ]


@router.get("/{event_id}/reviews/me", response_model=ReviewOut | None)
async def my_review(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EventReview)
        .options(selectinload(EventReview.user))
        .where(EventReview.event_id == event_id, EventReview.user_id == user.id)
    )
    r = result.scalar_one_or_none()
    if not r:
        return None
    return ReviewOut(
        id=r.id, event_id=r.event_id, user_id=r.user_id,
        username=r.user.username, full_name=r.user.full_name,
        avatar_url=r.user.avatar_url, rating=r.rating,
        body=r.body, created_at=r.created_at,
    )


@router.post("/{event_id}/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    event_id: str,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(
        select(Event).where(Event.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")

    attended = (await db.execute(
        select(EventAttendee).where(
            EventAttendee.event_id == event_id,
            EventAttendee.user_id == user.id,
            EventAttendee.status == "going",
        )
    )).scalar_one_or_none()
    if not attended:
        raise HTTPException(403, "You can only review events you attended")

    existing = (await db.execute(
        select(EventReview).where(
            EventReview.event_id == event_id, EventReview.user_id == user.id
        )
    )).scalar_one_or_none()
    if existing:
        existing.rating = payload.rating
        existing.body = payload.body
        await db.flush()
        r = existing
    else:
        r = EventReview(
            id=str(uuid.uuid4()),
            event_id=event_id,
            user_id=user.id,
            rating=payload.rating,
            body=payload.body,
        )
        db.add(r)
        await db.flush()

    return ReviewOut(
        id=r.id, event_id=r.event_id, user_id=r.user_id,
        username=user.username, full_name=user.full_name,
        avatar_url=user.avatar_url, rating=r.rating,
        body=r.body, created_at=r.created_at,
    )


@router.delete("/{event_id}/reviews/me", status_code=204)
async def delete_review(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EventReview).where(
            EventReview.event_id == event_id, EventReview.user_id == user.id
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Review not found")
    await db.delete(r)
    await db.flush()
