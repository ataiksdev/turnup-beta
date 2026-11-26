import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import decrement_to_zero, get_db
from app.middleware.auth import get_current_event_creator, get_current_organizer, get_current_user, get_optional_user
from app.middleware.rate_limit import limiter
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
    AnalyticsOut, CheckInRequest, CheckInResult, CheckInStats, CheckoutInitOut, CheckoutRequest,
    CoHostInviteRequest, CoHostOut, CoHostRespondRequest, DailyViewOut,
    ReviewCreate, ReviewOut, TicketOrderOut, TicketTierCreate, TicketTierOut,
    TicketTierUpdate, VerifyPaymentRequest, WaitlistEntryOut, WaitlistNotifyRequest,
    WaitlistStatusOut,
)
from app.services.activity import record as record_activity
from app.services.email import send_ticket_email
from app.services.hidden import exclude_hidden, hidden_for
from app.services.search import text_search
from app.services.paystack import PaystackConfigError, initialize_transaction, verify_transaction
from app.services.tickets import (
    auto_rsvp, confirm_order, notify_buyer, reserve_inventory, settle_paid_orders, to_kobo,
)
from app.schemas.user import UserSummary

router = APIRouter(prefix="/api/events", tags=["events"])


def _as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat those as UTC so comparisons work."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_until(event: Event) -> float:
    return round((_as_utc(event.start_date) - datetime.now(timezone.utc)).total_seconds() / 86400, 1)


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _load():
    return [
        selectinload(Event.host).selectinload(User.organizer_profile),
        selectinload(Event.category),
    ]


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
        "host_venue_id": event.host_venue_id, "venue_id": event.venue_id,
        "members_only": event.members_only, "fast_lane_enabled": event.fast_lane_enabled,
        "allow_ticket_transfers": event.allow_ticket_transfers,
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


async def _user_states(event_ids: list[str], user: User | None, db: AsyncSession) -> dict:
    """Batched _user_state for a list of events: 3 queries total instead of 3 per event."""
    if not user or not event_ids:
        return {}
    saved = set((await db.execute(select(EventSave.event_id).where(
        EventSave.user_id == user.id, EventSave.event_id.in_(event_ids)))).scalars().all())
    attending = dict((await db.execute(select(EventAttendee.event_id, EventAttendee.status).where(
        EventAttendee.user_id == user.id, EventAttendee.event_id.in_(event_ids)))).all())
    waitlisted = set((await db.execute(select(EventWaitlist.event_id).where(
        EventWaitlist.user_id == user.id, EventWaitlist.event_id.in_(event_ids),
        EventWaitlist.status.in_(["waiting", "notified"])))).scalars().all())
    return {eid: (eid in saved, attending.get(eid), eid in waitlisted) for eid in event_ids}


async def _has_event_access(event: Event, user: User, db: AsyncSession, venue_role: str = "manager") -> bool:
    """Host, accepted co-host, or (for a venue-hosted event) a venue Owner/Manager."""
    if event.host_id == user.id:
        return True
    ch = (await db.execute(select(EventCoHost).where(
        EventCoHost.event_id == event.id,
        EventCoHost.user_id == user.id,
        EventCoHost.status == "accepted",
    ))).scalar_one_or_none()
    if ch:
        return True
    if event.host_venue_id:
        from app.services.venue_access import ROLE_RANK, get_membership
        m = await get_membership(db, event.host_venue_id, user.id)
        return bool(m and ROLE_RANK[m.role] >= ROLE_RANK[venue_role])
    return False


async def _require_event_access(event_id: str, user: User, db: AsyncSession) -> Event:
    """Returns event if user is host, accepted co-host, or a manager of the hosting venue."""
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if not await _has_event_access(event, user, db):
        raise HTTPException(403, "Not authorized for this event")
    return event


async def _admin_manages_bot_event(event: Event, user: User | None, db: AsyncSession) -> bool:
    """Admins look after events the scout bot account hosts (scouted, or sent in through an
    agent connection such as the Telegram bot): no person is their host."""
    if not user or user.role != "admin":
        return False
    host_username = (await db.execute(select(User.username).where(User.id == event.host_id))).scalar_one_or_none()
    return host_username == settings.scout_bot_username


async def _require_event_read_access(event_id: str, user: User, db: AsyncSession) -> Event:
    """Read-only reports (analytics, insights): the event's team, or any admin."""
    if user.role == "admin":
        event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
        if not event:
            raise HTTPException(404, "Event not found")
        return event
    return await _require_event_access(event_id, user, db)


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

    stmt = select(Event).options(*_load()).where(Event.status == "published")
    stmt = exclude_hidden(stmt, await hidden_for(db, user))

    if q:
        # Full-text with typo tolerance on Postgres (app/services/search.py).
        match, rank = await text_search(db, q)
        if match is not None:
            stmt = stmt.where(match)
            if sort == "relevance" and rank is not None:
                order_clause = rank.desc()
    stmt = stmt.order_by(order_clause, Event.start_date.asc())
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
    states = await _user_states([e.id for e in events], user, db)
    return [_serialize(e, *states.get(e.id, (False, None, False))) for e in events]


@router.get("/trending", response_model=list[EventOut])
async def trending_events(
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stmt = (select(Event).options(*_load())
            .where(Event.status == "published", Event.is_trending == True)
            .order_by(Event.attendees_count.desc()).limit(limit))
    stmt = exclude_hidden(stmt, await hidden_for(db, user))
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
    stmt = exclude_hidden(stmt, await hidden_for(db, user))
    return [_serialize(e) for e in (await db.execute(stmt)).scalars().all()]


@router.get("/for-you", response_model=list[EventOut])
async def for_you_events(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    city: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """
    Personalised recommendation feed (app/services/recommender.py). Signed out, it ranks by
    place, time and popularity. `lat`/`lon` (the phone's location, if shared) are used for
    this request only, never stored. The app sends its device id in X-Anonymous-Id so a
    signed-out session's browsing counts too.
    """
    from app.services.recommender import recommend
    anon = (request.headers.get("x-anonymous-id") or "")[:64] or None
    result = await recommend(db, user=user, anonymous_id=anon, lat=lat, lon=lon, city=city, limit=limit)
    states = await _user_states([e.id for e in result.events], user, db)
    out = []
    for e in result.events:
        row = _serialize(e, *states.get(e.id, (False, None, False)))
        row["rec_reason"] = result.reasons.get(e.id)
        row["rec_request_id"] = result.request_id
        out.append(row)
    return out


@router.get("/following", response_model=list[EventOut])
async def following_events(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Network-based discovery: upcoming events that people you follow are
    attending or hosting. A separate, unblended surface from /for-you — built
    directly on the follow graph rather than any scoring model."""
    now = datetime.now(timezone.utc)

    following_ids = (await db.execute(
        select(Follow.following_id).where(Follow.follower_id == user.id)
    )).scalars().all()
    if not following_ids:
        return []

    attendee_rows = (await db.execute(
        select(EventAttendee.event_id, func.count(func.distinct(EventAttendee.user_id)))
        .where(EventAttendee.user_id.in_(following_ids))
        .group_by(EventAttendee.event_id)
    )).all()
    following_counts = {row[0]: row[1] for row in attendee_rows}

    hosted_ids = set((await db.execute(
        select(Event.id).where(Event.host_id.in_(following_ids), Event.status == "published")
    )).scalars().all())

    candidate_ids = set(following_counts) | hosted_ids
    if not candidate_ids:
        return []

    stmt = exclude_hidden(
        select(Event).options(*_load())
        .where(Event.id.in_(candidate_ids), Event.status == "published", Event.start_date > now)
        .order_by(Event.start_date.asc())
        .limit(limit),
        await hidden_for(db, user),
    )
    events = (await db.execute(stmt)).scalars().all()

    states = await _user_states([e.id for e in events], user, db)
    result = []
    for e in events:
        data = _serialize(e, *states.get(e.id, (False, None, False)))
        data["following_count"] = following_counts.get(e.id, 0)
        data["following_hosted"] = e.id in hosted_ids
        result.append(data)
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
    event_name = payload.get("event") or ""
    data = payload.get("data") or {}
    reference = data.get("reference") or ""

    # Venue marketplace and subscriptions (docs/venues-spec.md).
    if event_name.startswith("charge.dispute."):
        from app.services.chargebacks import record_dispute_event
        return {"status": await record_dispute_event(db, event_name, data)}
    if event_name.startswith(("subscription.", "invoice.")):
        from app.services.plus import handle_subscription_event
        return {"status": await handle_subscription_event(db, event_name, data)}
    if event_name != "charge.success":
        return {"status": "ignored"}
    if reference.startswith("sub_"):
        from app.services.plus import activate_first_payment
        await activate_first_payment(db, reference, data)
        return {"status": "ok"}
    if reference.startswith(("vb_", "vr_", "vd_", "vf_")):
        from app.services.venue_money import settle_venue_payment
        return {"status": (await settle_venue_payment(db, reference, data)).status}
    if isinstance(data.get("plan"), dict) and data["plan"].get("plan_code"):
        # A subscription renewal: Paystack makes its own reference.
        from app.services.plus import handle_subscription_event
        return {"status": await handle_subscription_event(db, "charge.success", data)}

    orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == reference))).scalars().all()
    if not orders:
        return {"status": "unknown_reference"}

    # Always 200 so Paystack stops retrying; a mismatch leaves the orders untouched (logged).
    result = await settle_paid_orders(db, list(orders), payload["data"])
    for job in result.emails:
        background_tasks.add_task(job.fn, **job.kwargs)
    return {"status": result.status}


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
    can_admin_edit = await _admin_manages_bot_event(event, user, db)
    # Only show drafts to their host (and bot-hosted drafts to admins, who edit them)
    if event.status == "draft":
        if not user or (event.host_id != user.id and not can_admin_edit):
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
    data["can_admin_edit"] = can_admin_edit
    data["avg_rating"] = event_avg_rating
    data["review_count"] = event_review_count
    h = event.host
    data["host"] = {
        "id": h.id, "username": h.username, "full_name": h.full_name,
        "display_name": h.display_name, "bio": h.bio,
        "avatar_url": h.avatar_url, "is_verified": h.is_verified,
        "is_verified_organizer": h.is_verified_organizer,
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
            # Template data is a free-form dict stored without validation, so re-run the
            # full EventCreate validation (URL fields included) on the merged result.
            try:
                data = EventCreate.model_validate(data).model_dump()
            except ValidationError as e:
                raise HTTPException(422, f"Template contains invalid data: {e.errors()[0]['msg']}")
            data.pop("template_id", None)

    # Admins bypass approval; organizer/moderator submissions go to review as drafts.
    if user.role == "admin":
        data["review_status"] = "approved"
    else:
        data["review_status"] = "pending"
        data["status"] = "draft"

    if data.get("venue_id"):
        from app.models.venue import Venue
        if not (await db.execute(select(Venue.id).where(
                Venue.id == data["venue_id"], Venue.status == "live"))).first():
            raise HTTPException(400, "That venue isn't listed on Turnup.")

    eid = str(uuid.uuid4())
    event = Event(id=eid, slug=_slugify(payload.title, eid),
                  host_id=user.id, template_id=template_id, **data)
    db.add(event)
    await db.flush()
    if event.status == "published":
        await db.execute(update(User).where(User.id == user.id).values(
            events_hosted=User.events_hosted + 1))
        if event.review_status == "approved":
            from app.services.alerts import announce_event
            await announce_event(db, event)
    stmt = select(Event).options(*_load()).where(Event.id == eid)
    return _serialize((await db.execute(stmt)).scalar_one())


# Fields whose content a moderator approved; changing them needs another look.
REVIEWED_FIELDS = {"title", "description", "cover_image", "meeting_url", "tags", "venue_name", "address"}


@router.patch("/{event_id}", response_model=EventDetail)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    admin_on_bot_event = await _admin_manages_bot_event(event, user, db)
    if not admin_on_bot_event and not await _has_event_access(event, user, db):
        raise HTTPException(403, "Not authorized for this event")
    was_draft = event.status == "draft"
    old_status = event.status
    old_start = event.start_date

    changes = payload.model_dump(exclude_none=True)

    # A bot-hosted submission goes live through Approve in the Events queue, which also counts
    # it, announces it and tells the sender (e.g. the Telegram chat it came from).
    if (admin_on_bot_event and changes.get("status") == "published"
            and event.review_status != "approved"):
        raise HTTPException(409, "Save your changes, then approve it from the Events queue to publish it.")

    if user.role != "admin":
        if changes.get("status") == "published" and event.review_status != "approved":
            raise HTTPException(403, "This event is awaiting admin approval before it can be published.")
        # Editing a rejected (or still-pending) submission resubmits it for review.
        if changes and event.review_status in ("pending", "rejected"):
            event.review_status = "pending"
            event.review_note = None
        # Editing what attendees SEE on an approved event sends it back to the review queue,
        # otherwise approval could be bypassed by publishing something harmless and then
        # rewriting it. It stays live meanwhile (tickets may already be sold); an admin
        # re-approves it, or rejects it, which takes it down.
        elif event.review_status == "approved" and any(
            k in REVIEWED_FIELDS and v != getattr(event, k) for k, v in changes.items()
        ):
            event.review_status = "pending"
            event.review_note = "Edited after approval"

    if changes.get("category_id") and not (await db.execute(
            select(Category.id).where(Category.id == changes["category_id"]))).first():
        raise HTTPException(400, "That category doesn't exist")

    new_start = changes.get("start_date", event.start_date)
    new_end = changes.get("end_date", event.end_date)
    if new_start and new_end and _as_utc(new_end) < _as_utc(new_start):
        raise HTTPException(422, "The event can't end before it starts")

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
    if event.host_id != user.id and not (event.host_venue_id and await _has_event_access(event, user, db)):
        raise HTTPException(403, "Only the host can delete this event")
    # Deleting would also delete buyers' tickets and the payment records needed to refund them.
    sold = (await db.execute(select(func.count(TicketOrder.id)).where(
        TicketOrder.event_id == event_id,
        TicketOrder.status.in_(["confirmed", "pending", "needs_refund"]),
    ))).scalar() or 0
    if sold:
        raise HTTPException(409, "This event has ticket orders, so it can't be deleted. "
                                 "Cancel it instead (attendees are notified), and refund orders from Orders.")
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
    old_status = existing.status if existing else None
    if old_status == payload.status:
        return {"status": payload.status, "attendees_count": event.attendees_count,
                "interested_count": event.interested_count}
    if _as_utc(event.end_date or event.start_date) <= datetime.now(timezone.utc):
        raise HTTPException(400, "This event has ended.")

    becoming_going = payload.status == "going"
    clean_answers = []
    if becoming_going and event.host_id != user.id:
        from app.services.registration import check_answers
        clean_answers = await check_answers(db, event_id, user.id, payload.answers)
    if becoming_going:
        # Ticketed events: "going" means holding a ticket. Otherwise anyone could RSVP to a
        # paid event for free (and then review it, take a capacity spot, etc.).
        has_tiers = (await db.execute(select(TicketTier.id).where(
            TicketTier.event_id == event_id, TicketTier.is_active == True).limit(1))).first()
        if has_tiers and event.host_id != user.id:
            has_ticket = (await db.execute(select(TicketOrder.id).where(
                TicketOrder.event_id == event_id, TicketOrder.user_id == user.id,
                TicketOrder.status == "confirmed").limit(1))).first()
            if not has_ticket:
                raise HTTPException(409, "This event needs a ticket. Get one to mark yourself as going.")

        # Take a capacity spot atomically. This applies to switching from "interested" too,
        # which previously skipped the check entirely.
        claimed = await db.execute(
            update(Event).where(
                Event.id == event_id,
                or_(Event.capacity.is_(None), Event.capacity <= 0, Event.attendees_count < Event.capacity),
            ).values(attendees_count=Event.attendees_count + 1)
        )
        if claimed.rowcount == 0:
            if event.waitlist_enabled:
                return await _join_waitlist_internal(event, user, db)
            raise HTTPException(409, "Event is at capacity")
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=User.events_attended + 1))
    else:
        await db.execute(update(Event).where(Event.id == event_id).values(
            interested_count=Event.interested_count + 1))

    # Undo the previous status's counters.
    if old_status == "going":
        await db.execute(update(Event).where(Event.id == event_id).values(
            attendees_count=decrement_to_zero(Event.attendees_count)))
        await db.execute(update(User).where(User.id == user.id).values(
            events_attended=decrement_to_zero(User.events_attended)))
    elif old_status == "interested":
        await db.execute(update(Event).where(Event.id == event_id).values(
            interested_count=decrement_to_zero(Event.interested_count)))

    if existing:
        existing.status = payload.status
    else:
        db.add(EventAttendee(id=str(uuid.uuid4()), user_id=user.id,
                             event_id=event_id, status=payload.status))
    record_activity(db, "rsvp_changed", user_id=user.id, event_id=event_id,
                    props={"status": payload.status, "from": old_status,
                           "days_until_event": _days_until(event)})
    if becoming_going:
        from app.services.registration import save_answers
        from app.services.sharing import credit
        await save_answers(db, event_id, user.id, clean_answers)
        await credit(db, user.id, event_id, "going")  # a share link that brought them

    # Notify host when someone RSVPs going (skip if user is the host)
    if becoming_going and event.host_id != user.id:
        db.add(Notification(
            id=str(uuid.uuid4()), user_id=event.host_id, type="going",
            title=f"{user.display_name or user.full_name or user.username} is going to your event",
            body=event.title,
            reference_id=event_id, reference_type="event", actor_id=user.id,
        ))

    await db.flush()
    await db.refresh(event)
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
            events_attended=decrement_to_zero(User.events_attended)))
    else:
        event.interested_count = max(0, event.interested_count - 1)
    record_activity(db, "rsvp_changed", user_id=user.id, event_id=event_id,
                    props={"status": None, "from": att.status})
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
        record_activity(db, "event_unsaved", user_id=user.id, event_id=event_id)
        return {"saved": False}
    save = EventSave(id=str(uuid.uuid4()), user_id=user.id, event_id=event_id)
    from app.services.nudges import record_price_on_save
    await record_price_on_save(db, save, event)  # for "price dropped" alerts
    db.add(save)
    event.saves_count += 1
    record_activity(db, "event_saved", user_id=user.id, event_id=event_id,
                    props={"days_until_event": _days_until(event)})
    from app.services.sharing import credit
    await credit(db, user.id, event_id, "save")
    return {"saved": True}


# ── Attendees list ────────────────────────────────────────────────────────────────

@router.get("/{event_id}/attendees")
async def get_attendees(
    event_id: str,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # Only published events have a public guest list; drafts only to their host/co-hosts.
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.status != "published":
        if not user:
            raise HTTPException(404, "Event not found")
        await _require_event_access(event_id, user, db)
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
    # One view per viewer (signed-in user, else IP) per event per 30 minutes, so refreshing
    # or a script hammering this endpoint can't inflate an organizer's numbers.
    since = datetime.now(timezone.utc) - timedelta(minutes=30)
    viewer = (EventView.user_id == user.id) if user else (EventView.ip_address == ip)
    recent = (await db.execute(select(EventView.id).where(
        EventView.event_id == event_id, viewer, EventView.viewed_at >= since).limit(1))).first()
    if recent:
        return
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
    event = await _require_event_read_access(event_id, user, db)

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
async def list_ticket_tiers(
    event_id: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Buyers see tiers on sale. Hosts/co-hosts can ask for paused ones too (to manage them)."""
    stmt = select(TicketTier).where(TicketTier.event_id == event_id)
    if include_inactive and user:
        await _require_event_access(event_id, user, db)
    else:
        stmt = stmt.where(TicketTier.is_active == True)
    result = await db.execute(stmt.order_by(TicketTier.price.asc()))
    tiers = result.scalars().all()
    return [_tier_out(t) for t in tiers]


@router.post("/{event_id}/tickets", response_model=TicketTierOut, status_code=201)
async def create_ticket_tier(
    event_id: str,
    payload: TicketTierCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await _require_event_access(event_id, user, db)
    t = TicketTier(id=str(uuid.uuid4()), event_id=event_id, **payload.model_dump())
    db.add(t)
    await db.flush()
    if t.plus_presale_ends_at and _as_utc(t.plus_presale_ends_at) > datetime.now(timezone.utc) \
            and event.status == "published":
        from app.services.alerts import notify_presale
        await notify_presale(db, event, t.name)
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
    changes = payload.model_dump(exclude_none=True)
    if "quantity" in changes and changes["quantity"] < t.quantity_sold:
        raise HTTPException(409, f"{t.quantity_sold} tickets are already sold or reserved; "
                                 "the quantity can't go below that.")
    for k, v in changes.items():
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
@limiter.limit(settings.rate_limit_checkout)
async def checkout_tickets(
    request: Request,
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
    # A past event can still be opened (e.g. from an organizer's profile), but its tickets
    # can't be bought. Sales stay open until the event ends, for latecomers.
    if _as_utc(event.end_date or event.start_date) <= datetime.now(timezone.utc):
        raise HTTPException(400, "This event has ended, so tickets are no longer on sale.")

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
                amount_kobo=to_kobo(total),
                email=user.email or "",
                is_free=(total == 0),
            )

    from app.services.plus import is_plus
    member = is_plus(user)
    if event.members_only and not member:
        raise HTTPException(402, "This event is for Turnup+ members.")

    from app.services.registration import (
        check_answers, find_valid_promo, line_discounts, save_answers, take_use,
    )
    clean_answers = await check_answers(db, event_id, user.id, payload.answers)
    promo = await find_valid_promo(db, event_id, payload.promo_code) if payload.promo_code else None

    now = datetime.now(timezone.utc)
    reference = f"turnup-{uuid.uuid4().hex[:16]}"
    orders: list[TicketOrder] = []
    tiers_by_order: dict[str, TicketTier] = {}
    lines: list[tuple[TicketTier, int]] = []

    for item in payload.items:
        t = await _get_tier(item.tier_id, event_id, db)
        if not t.is_active:
            raise HTTPException(400, f"'{t.name}' is not available")
        if t.members_only and not member:
            raise HTTPException(402, f"'{t.name}' is for Turnup+ members.")
        if t.plus_presale_ends_at:
            presale_end = _as_utc(t.plus_presale_ends_at)
            if now < presale_end and not member:
                raise HTTPException(402, f"'{t.name}' is in a Turnup+ members' presale until "
                                         f"{presale_end:%d %b, %H:%M} UTC.")
            if now >= presale_end and t.presale_then == "close":
                raise HTTPException(400, f"The presale for '{t.name}' has ended")
        if t.sale_start and now < _as_utc(t.sale_start):
            raise HTTPException(400, f"Sales for '{t.name}' have not started yet")
        if t.sale_end and now > _as_utc(t.sale_end):
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
        lines.append((t, item.quantity))

    if promo:
        off = line_discounts(promo, lines)
        if sum(off) <= 0:
            raise HTTPException(400, "That promo code doesn't apply to the tickets you've chosen.")
        for order, discount in zip(orders, off):
            if discount > 0:
                order.discount_amount = discount
                order.total_price = round(order.total_price - discount, 2)
            order.promo_code_id = promo.id
        await take_use(db, promo, user.id, reference, round(sum(off), 2))

    await save_answers(db, event_id, user.id, clean_answers)
    await db.flush()
    total = round(sum(o.total_price for o in orders), 2)
    record_activity(db, "checkout_started", user_id=user.id, event_id=event_id, props={
        "cart_value": total, "ticket_count": sum(o.quantity for o in orders),
        "tiers": [{"tier_id": o.tier_id, "unit_price": o.unit_price, "quantity": o.quantity} for o in orders],
        **({"promo_code": promo.code, "discount": round(sum(o.discount_amount or 0 for o in orders), 2)}
           if promo else {}),
    })

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
        await auto_rsvp(event, user, db)
        return CheckoutInitOut(
            order_ids=[o.id for o in orders], payment_reference=reference,
            paystack_public_key="", amount_kobo=0, email=user.email or "", is_free=True,
        )

    # Paid — init one Paystack transaction for the summed total (amount in kobo)
    amount_kobo = to_kobo(total)
    email = user.email or f"{user.username}@turnup.app"
    split: dict = {}
    if event.host_venue_id:
        # Venue-hosted: paid to the venue's subaccount, Turnup keeps the ticket fee plus any
        # recovery of what the venue owes (docs/venues-spec.md 4.5, 4.6).
        from app.models.venue import Venue
        from app.services.settings import get_platform_settings
        from app.services.venue_money import plan_split
        venue = (await db.execute(select(Venue).where(Venue.id == event.host_venue_id))).scalar_one_or_none()
        if venue and venue.paystack_subaccount_code:
            fee_percent = (await get_platform_settings(db)).ticket_fee_percent
            fee, recovery, _ = await plan_split(db, venue, amount_kobo, fee_percent)
            split = dict(subaccount=venue.paystack_subaccount_code, transaction_charge=fee + recovery,
                         bearer="subaccount")
            for i, o in enumerate(orders):
                o.venue_id = venue.id
                o.recovery_kobo = recovery if i == 0 else 0
            await db.flush()
    try:
        await initialize_transaction(
            email=email, amount_kobo=amount_kobo, reference=reference,
            metadata={"order_ids": [o.id for o in orders], "event_id": event_id},
            **split,
        )
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Payment gateway unavailable. Please try again.")

    return CheckoutInitOut(
        order_ids=[o.id for o in orders], payment_reference=reference,
        paystack_public_key=settings.paystack_public_key, amount_kobo=amount_kobo, email=email,
    )


def _order_out(order: TicketOrder, tier_name: str) -> TicketOrderOut:
    return TicketOrderOut(
        id=order.id, event_id=order.event_id, tier_id=order.tier_id, tier_name=tier_name,
        quantity=order.quantity, unit_price=order.unit_price, total_price=order.total_price,
        status=order.status, payment_reference=order.payment_reference,
        ticket_code=order.ticket_code, checked_in_at=order.checked_in_at,
        discount_amount=order.discount_amount, created_at=order.created_at,
    )


@router.post("/{event_id}/tickets/verify-payment", response_model=list[TicketOrderOut])
async def verify_payment(
    event_id: str,
    payload: VerifyPaymentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Verify a Paystack payment and settle every order sharing this reference (a checkout
    may have created several, one per tier line). Returns this payment's confirmed orders.

    Safe to call after the webhook already confirmed them (returns them instead of an error),
    and after the orders expired (they're revived if tickets remain, refunded if not)."""
    orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == payload.reference,
        TicketOrder.user_id == user.id,
        TicketOrder.event_id == event_id,
    ))).scalars().all()
    if not orders:
        raise HTTPException(404, "Order not found")

    if any(o.status in ("pending", "cancelled") for o in orders):
        try:
            ps_resp = await verify_transaction(payload.reference)
        except PaystackConfigError as e:
            raise HTTPException(503, str(e))
        except Exception:
            raise HTTPException(502, "Could not verify payment. Please contact support.")

        ps_data = ps_resp.get("data", {})
        if ps_data.get("status") != "success":
            raise HTTPException(402, "Payment not completed")

        result = await settle_paid_orders(db, list(orders), ps_data)
        if result.status == "amount_mismatch":
            raise HTTPException(402, "Payment amount does not match your order. Please contact support.")
        for job in result.emails:
            background_tasks.add_task(job.fn, **job.kwargs)

    # An empty list means the payment went through but every ticket in it had sold out by
    # the time it cleared; the buyer has been refunded (or the refund is queued) and notified.
    tier_names = {t.id: t.name for t in (await db.execute(select(TicketTier).where(
        TicketTier.id.in_({o.tier_id for o in orders})))).scalars().all()}
    confirmed = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == payload.reference,
        TicketOrder.user_id == user.id,
        TicketOrder.status == "confirmed",
    ))).scalars().all()
    return [_order_out(o, tier_names.get(o.tier_id, "")) for o in confirmed]


def _tier_out(t: TicketTier) -> TicketTierOut:
    available = (t.quantity - t.quantity_sold) if t.quantity is not None else None
    return TicketTierOut(
        id=t.id, event_id=t.event_id, name=t.name, description=t.description,
        price=t.price, currency=t.currency, quantity=t.quantity,
        quantity_sold=t.quantity_sold, available=available,
        max_per_order=t.max_per_order, is_active=t.is_active,
        sale_start=t.sale_start, sale_end=t.sale_end, created_at=t.created_at,
        members_only=bool(t.members_only), plus_presale_ends_at=t.plus_presale_ends_at,
        presale_then=t.presale_then or "open",
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
    if _as_utc(event.end_date or event.start_date) <= datetime.now(timezone.utc):
        raise HTTPException(400, "This event has ended.")
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
    # Turnup+ members are offered spots first, then everyone else in order (spec 4.8 perk 2).
    from app.services.plus import is_plus
    waiting = (await db.execute(
        select(EventWaitlist)
        .options(selectinload(EventWaitlist.user))
        .where(EventWaitlist.event_id == event_id, EventWaitlist.status == "waiting")
        .order_by(EventWaitlist.position.asc())
    )).scalars().all()
    entries = sorted(waiting, key=lambda e: (0 if is_plus(e.user) else 1, e.position))[:payload.count]
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
@limiter.limit(settings.rate_limit_checkin)
async def check_in_ticket(
    request: Request,
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
    if not await _has_event_access(event, user, db, venue_role="viewer"):
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
    # Tickets checked in before partial admission existed count as fully admitted.
    admitted = order.quantity if (order.checked_in_at and not order.admitted_count) else (order.admitted_count or 0)
    remaining = order.quantity - admitted
    if remaining <= 0:
        who = f"all {order.quantity}" if order.quantity > 1 else "already"
        raise HTTPException(409, f"Ticket already checked in ({who} in)" if order.quantity > 1 else "Ticket already checked in")

    from app.services.plus import is_plus
    attendee_name = (
        order.user.display_name or order.user.full_name or order.user.username
        if order.user else "Attendee"
    )

    def result(admitted_now: int, needs_choice: bool = False) -> CheckInResult:
        return CheckInResult(
            order_id=order.id, ticket_code=order.ticket_code, attendee_name=attendee_name,
            tier_name=order.tier.name, quantity=order.quantity,
            checked_in_at=order.checked_in_at or datetime.now(timezone.utc),
            # Checked at scan time, so a lapsed membership doesn't get the fast lane.
            fast_lane=bool(event.fast_lane_enabled and is_plus(order.user)),
            admitted_count=admitted + admitted_now, admitted_now=admitted_now,
            remaining=remaining - admitted_now, needs_choice=needs_choice,
        )

    if payload.admit is None and remaining > 1:
        return result(0, needs_choice=True)  # staff choose how many are at the door
    n = payload.admit or 1
    if n > remaining:
        raise HTTPException(409, f"Only {remaining} of this ticket's {order.quantity} still to come in")

    # Atomic, so two door phones scanning the same ticket can't admit more than it covers.
    now = datetime.now(timezone.utc)
    done = await db.execute(
        update(TicketOrder)
        .where(TicketOrder.id == order.id, TicketOrder.admitted_count == (order.admitted_count or 0))
        .values(admitted_count=admitted + n,
                checked_in_at=func.coalesce(TicketOrder.checked_in_at, now))
    )
    if done.rowcount == 0:
        raise HTTPException(409, "This ticket was just scanned at another door. Scan it again.")
    record_activity(db, "event_checked_in", user_id=order.user_id, event_id=event_id, props={
        "order_id": order.id, "admitted": n,
        "minutes_from_start": round((now - _as_utc(event.start_date)).total_seconds() / 60),
    })
    await db.refresh(order)
    return result(n)


@router.get("/{event_id}/checkin/stats", response_model=CheckInStats)
async def check_in_stats(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live door count shared by everyone scanning: people in vs expected, and the latest
    check-ins (any door)."""
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    if not await _has_event_access(event, user, db, venue_role="viewer"):
        raise HTTPException(403, "Only the event's team can see the door count")
    orders = (await db.execute(
        select(TicketOrder).options(selectinload(TicketOrder.tier), selectinload(TicketOrder.user))
        .where(TicketOrder.event_id == event_id, TicketOrder.status == "confirmed")
    )).scalars().all()

    def admitted(o: TicketOrder) -> int:
        return o.quantity if (o.checked_in_at and not o.admitted_count) else (o.admitted_count or 0)

    recent = sorted((o for o in orders if o.checked_in_at), key=lambda o: o.checked_in_at, reverse=True)[:30]
    return CheckInStats(
        people_in=sum(admitted(o) for o in orders),
        people_expected=sum(o.quantity for o in orders),
        tickets_in=sum(1 for o in orders if admitted(o) >= o.quantity),
        tickets_total=len(orders),
        recent=[{"order_id": o.id, "code": (o.ticket_code or "")[:8].upper(), "tier": o.tier.name,
                 "name": (o.user.display_name or o.user.full_name or o.user.username) if o.user else "Attendee",
                 "admitted": admitted(o), "quantity": o.quantity, "first_in": o.checked_in_at} for o in recent],
    )


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.get("/{event_id}/insights")
async def event_insights(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """For the event's team: best day and time, price vs comparable events, booking pace,
    and searches in its city that found nothing (app/services/insights.py)."""
    from app.services.insights import event_insights as build
    event = await _require_event_read_access(event_id, user, db)
    return await build(db, event)


@router.get("/{event_id}/similar", response_model=list[EventOut])
async def similar(
    event_id: str,
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """"You might also like": people who went to this also went to..., then similar events
    (app/services/similar.py). The reason is in rec_reason."""
    from app.services.similar import similar_events
    source = (await db.execute(select(Event).where(
        or_(Event.id == event_id, Event.slug == event_id)))).scalar_one_or_none()
    if not source or source.status != "published":
        raise HTTPException(404, "Event not found")
    found = await similar_events(db, source, viewer=user, limit=limit)
    states = await _user_states([s.event.id for s in found], user, db)
    out = []
    for s in found:
        row = _serialize(s.event, *states.get(s.event.id, (False, None, False)))
        row["rec_reason"] = s.reason
        out.append(row)
    return out


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
@limiter.limit(settings.rate_limit_review)
async def create_review(
    request: Request,
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
    record_activity(db, "event_reviewed", user_id=user.id, event_id=event_id,
                    props={"rating": payload.rating, "has_text": bool(payload.body)})

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
