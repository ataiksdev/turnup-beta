"""Public venue marketplace: places, search, featured strip, venue pages, follows
(docs/venues-spec.md 4.10, 4.11, section 5)."""
import random
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import decrement_to_zero, get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.models.event import Event
from app.models.user import User
from app.models.venue import (
    Area, Deal, FeaturedSlot, Venue, VenueBlock, VenueBooking, VenueFollow, VenueReview,
    VenueSpace,
)
from app.services.places import STATE_LABELS, STATES, bounding_box, haversine_m, normalize_state
from app.services.plus import is_plus, is_pro
from app.services.venue_money import PAID_BOOKING, ACTIVE_BOOKING, strikes_last_year
from app.services.venue_policy import PRESET_LABELS
from app.services.venue_views import (
    _json_list, area_name, media_for, public_price, space_out, user_brief, venue_card,
)

router = APIRouter(tags=["venues"])

PUBLIC_STATUSES = ("live", "paused", "suspended")
TYPES = {"hall": "Event halls & centres", "lounge": "Lounges, clubs & bars",
         "hotel_studio": "Hotels & studios", "outdoor": "Outdoor & beach"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def monday_of(d: datetime) -> datetime:
    d = d.astimezone(timezone.utc)
    start = datetime.combine((d - timedelta(days=d.weekday())).date(), time(0), tzinfo=timezone.utc)
    return start


# ── Places ──────────────────────────────────────────────────────────────────────

@router.get("/api/places/states")
async def list_states():
    return [{"id": s, "label": STATE_LABELS.get(s, s)} for s in STATES]


@router.get("/api/places/areas")
async def list_areas(state: str, db: AsyncSession = Depends(get_db)):
    st = normalize_state(state)
    if not st:
        raise HTTPException(404, "Unknown state")
    rows = (await db.execute(select(Area).where(Area.state == st, Area.is_active == True).order_by(  # noqa: E712
        Area.sort_order, Area.name))).scalars().all()
    return [{"id": a.id, "state": a.state, "name": a.name, "slug": a.slug, "kind": a.kind,
             "latitude": a.latitude, "longitude": a.longitude} for a in rows]


@router.get("/api/venues/types")
async def venue_types():
    return [{"id": k, "label": v} for k, v in TYPES.items()]


# ── Search ──────────────────────────────────────────────────────────────────────

class _Filters:
    def __init__(self, state, area_ids, lat, lng, radius_km, type_, min_capacity, date,
                 max_price_kobo, amenities, verified_only, q):
        self.state = normalize_state(state) if state else None
        if state and not self.state:
            raise HTTPException(400, "Unknown state")
        self.area_ids = [a for a in (area_ids or "").split(",") if a]
        self.lat, self.lng = lat, lng
        self.radius_m = (radius_km or 10) * 1000 if lat is not None and lng is not None else None
        self.type, self.min_capacity, self.date = type_, min_capacity, date
        self.max_price_kobo = max_price_kobo
        self.amenities = [a.strip().lower() for a in (amenities or "").split(",") if a.strip()]
        self.verified_only, self.q = verified_only, (q or "").strip()


def _filters(
    state: str | None = None, area_ids: str | None = None,
    lat: float | None = Query(None, ge=-90, le=90), lng: float | None = Query(None, ge=-180, le=180),
    radius_km: int | None = Query(None, ge=1, le=100), type: str | None = None,
    min_capacity: int | None = Query(None, ge=1), date: str | None = None,
    max_price_kobo: int | None = Query(None, ge=0), amenities: str | None = None,
    verified_only: bool = False, q: str | None = None,
) -> _Filters:
    if type and type not in TYPES:
        raise HTTPException(400, "Unknown venue type")
    return _Filters(state, area_ids, lat, lng, radius_km, type, min_capacity, date,
                    max_price_kobo, amenities, verified_only, q)


async def _search(db: AsyncSession, f: _Filters, ignore_place: bool = False) -> list[tuple[Venue, list[VenueSpace], float | None]]:
    """Venues matching every filter, with their spaces and distance (if near-me)."""
    q = select(Venue).where(Venue.status == "live")
    if f.state:
        q = q.where(Venue.state == f.state)
    if not ignore_place:
        if f.area_ids:
            q = q.where(Venue.area_id.in_(f.area_ids))
        if f.radius_m:
            a, b, c, d = bounding_box(f.lat, f.lng, f.radius_m)
            q = q.where(Venue.latitude.between(a, b), Venue.longitude.between(c, d))
    if f.type:
        q = q.where(Venue.type == f.type)
    if f.verified_only:
        q = q.where(Venue.verification_status == "visit_passed")
    if f.q:
        like = f"%{f.q.lower()}%"
        q = q.where(or_(func.lower(Venue.name).like(like), func.lower(Venue.description).like(like)))
    venues = (await db.execute(q.limit(500))).scalars().all()
    if not venues:
        return []
    ids = [v.id for v in venues]
    spaces_by: dict[str, list[VenueSpace]] = {}
    for s in (await db.execute(select(VenueSpace).where(VenueSpace.venue_id.in_(ids), VenueSpace.is_active == True))).scalars().all():  # noqa: E712
        spaces_by.setdefault(s.venue_id, []).append(s)

    busy_spaces: set[str] = set()
    blocked_venues: set[str] = set()
    if f.date:
        try:
            day = datetime.fromisoformat(f.date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD")
        day_end = day + timedelta(days=1)
        busy_spaces = set((await db.execute(select(VenueBooking.space_id).where(
            VenueBooking.venue_id.in_(ids), VenueBooking.status.in_(ACTIVE_BOOKING),
            VenueBooking.starts_at < day_end, VenueBooking.ends_at > day))).scalars().all())
        for vid, sid in (await db.execute(select(VenueBlock.venue_id, VenueBlock.space_id).where(
                VenueBlock.venue_id.in_(ids), VenueBlock.starts_at < day_end, VenueBlock.ends_at > day))).all():
            if sid:
                busy_spaces.add(sid)
            else:
                blocked_venues.add(vid)

    out = []
    for v in venues:
        spaces = spaces_by.get(v.id, [])
        if not spaces:
            continue
        usable = spaces
        if f.min_capacity:
            usable = [s for s in usable if max(s.capacity_seated or 0, s.capacity_standing or 0) >= f.min_capacity]
        if f.date:
            usable = [] if v.id in blocked_venues else [s for s in usable if s.id not in busy_spaces]
        if f.max_price_kobo is not None and v.price_display != "on_request":
            usable = [s for s in usable if s.price_from_kobo is None or s.price_from_kobo <= f.max_price_kobo]
        if not usable:
            continue
        if f.amenities:
            have = {a.lower() for a in _json_list(v.amenities)}
            if not all(a in have for a in f.amenities):
                continue
        dist = None
        if f.radius_m and not ignore_place:
            if v.latitude is None or v.longitude is None:
                continue
            dist = haversine_m(f.lat, f.lng, v.latitude, v.longitude)
            if dist > f.radius_m:
                continue
        out.append((v, spaces, dist))
    return out


async def _active_featured(db: AsyncSession, state: str | None) -> list[FeaturedSlot]:
    now = utcnow()
    q = select(FeaturedSlot).where(FeaturedSlot.status == "active", FeaturedSlot.week_start <= now,
                                   FeaturedSlot.ends_at > now)
    if state:
        q = q.where(FeaturedSlot.state == state)
    return list((await db.execute(q)).scalars().all())


def _area_slot_matches(slot: FeaturedSlot, venue: Venue, f: _Filters, dist: float | None) -> bool:
    if f.area_ids:
        return slot.area_id in f.area_ids
    if f.radius_m:
        return dist is not None
    return False


@router.get("/api/venues")
async def search_venues(
    f: _Filters = Depends(_filters),
    sort: str = Query("recommended", pattern="^(recommended|rating|distance|price|newest)$"),
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Venues matching the filters. Featured venues that match are pinned first (state-wide
    above area); then Pro venues get a boost; then the chosen sort."""
    results = await _search(db, f)
    slots = await _active_featured(db, f.state)
    state_featured = {s.venue_id for s in slots if s.scope == "state"}
    pinned: dict[str, str] = {}
    for v, _, dist in results:
        if v.id in state_featured:
            pinned[v.id] = "state"
        else:
            for s in slots:
                if s.scope == "area" and s.venue_id == v.id and _area_slot_matches(s, v, f, dist):
                    pinned[v.id] = "area"
    order = {"state": 0, "area": 1}

    def key(item):
        v, spaces, dist = item
        base = [order.get(pinned.get(v.id), 2), 0 if is_pro(v) else 1]
        if sort == "distance" and dist is not None:
            base.append(dist)
        elif sort == "price":
            base.append(min([s.price_from_kobo or 10**15 for s in spaces] or [10**15]))
        elif sort == "newest":
            base.append(-(v.went_live_at or v.created_at).timestamp())
        else:
            base.append(-((v.rating_organizers or 0) * 2 + (v.rating_guests or 0) + v.followers_count / 1000))
        return base

    results.sort(key=key)
    page = results[offset:offset + limit]
    return {"total": len(results),
            "items": [await venue_card(db, v, pinned.get(v.id), spaces, dist) for v, spaces, dist in page]}


@router.get("/api/venues/featured")
async def featured_strip(f: _Filters = Depends(_filters), db: AsyncSession = Depends(get_db)):
    """The Featured venues strip (spec 4.10): area slots for the chosen areas / near-me radius
    first, then the state's state-wide slots. Order within each group rotates per load."""
    if not f.state:
        return []
    slots = await _active_featured(db, f.state)
    venues = {v.id: v for v in (await db.execute(select(Venue).where(
        Venue.id.in_({s.venue_id for s in slots}), Venue.status == "live"))).scalars().all()} if slots else {}
    area_group, state_group = [], []
    for s in slots:
        v = venues.get(s.venue_id)
        if not v:
            continue
        if s.scope == "state":
            state_group.append(v)
        elif f.area_ids and s.area_id in f.area_ids:
            area_group.append(v)
        elif f.radius_m and v.latitude is not None and haversine_m(f.lat, f.lng, v.latitude, v.longitude) <= f.radius_m:
            area_group.append(v)
    random.shuffle(area_group)
    random.shuffle(state_group)
    seen, out = set(), []
    for label, group in (("area", area_group), ("state", state_group)):
        for v in group:
            if v.id not in seen:
                seen.add(v.id)
                out.append(await venue_card(db, v, label))
    return out


# ── Venue page ──────────────────────────────────────────────────────────────────

async def _public_venue(db: AsyncSession, slug_or_id: str) -> Venue:
    v = (await db.execute(select(Venue).where(or_(Venue.slug == slug_or_id, Venue.id == slug_or_id)))).scalar_one_or_none()
    if not v or v.status not in PUBLIC_STATUSES:
        raise HTTPException(404, "Venue not found")
    return v


@router.get("/api/venues/{slug}")
async def get_venue(slug: str, db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)):
    v = await _public_venue(db, slug)
    spaces = list((await db.execute(select(VenueSpace).where(
        VenueSpace.venue_id == v.id, VenueSpace.is_active == True).order_by(VenueSpace.sort_order))).scalars().all())  # noqa: E712
    following = bool(user and (await db.execute(select(VenueFollow.id).where(
        VenueFollow.venue_id == v.id, VenueFollow.user_id == user.id))).first())
    now = utcnow()
    cancellations = (await db.execute(select(func.count()).select_from(VenueBooking).where(
        VenueBooking.venue_id == v.id, VenueBooking.status == "cancelled_by_venue",
        VenueBooking.cancelled_at >= now - timedelta(days=365)))).scalar_one()
    deals = (await db.execute(select(Deal).where(Deal.venue_id == v.id, Deal.is_active == True, or_(  # noqa: E712
        Deal.valid_to.is_(None), Deal.valid_to > now)))).scalars().all()
    slots = await _active_featured(db, v.state)
    featured = next((s.scope for s in slots if s.venue_id == v.id), None)
    v.views_count = (v.views_count or 0) + 1
    return {
        **(await venue_card(db, v, featured, spaces)),
        "description": v.description, "address": v.address, "amenities": _json_list(v.amenities),
        "rules": v.rules, "status": v.status,
        "accepting_enquiries": v.status == "live", "deposits_enabled": v.deposits_enabled,
        "refund_preset": v.refund_preset, "refund_policy": PRESET_LABELS.get(v.refund_preset),
        "deposit_type": v.deposit_type, "deposit_value": v.deposit_value, "balance_due_days": v.balance_due_days,
        "spaces": [space_out(s) for s in spaces], "media": await media_for(db, v, include_hidden=False),
        "is_following": following, "cancellations_last_year": cancellations,
        "strikes_last_year": await strikes_last_year(db, v.id),
        "deals": [{"id": d.id, "title": d.title, "description": d.description, "kind": d.kind,
                   "valid_to": d.valid_to} for d in deals],
        "viewer_is_plus": is_plus(user),
    }


@router.get("/api/venues/{slug}/availability")
async def availability(slug: str, start: str, end: str, space_id: str | None = None,
                       db: AsyncSession = Depends(get_db)):
    """Busy ranges only (no booking details), for the calendar on the venue page."""
    v = await _public_venue(db, slug)
    try:
        a = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) if "T" not in start else datetime.fromisoformat(start)
        b = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if "T" not in end else datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "start and end must be dates")
    if (b - a).days > 400:
        raise HTTPException(400, "Range too long")
    bq = select(VenueBooking.space_id, VenueBooking.starts_at, VenueBooking.ends_at).where(
        VenueBooking.venue_id == v.id, VenueBooking.status.in_(PAID_BOOKING + ("pending_payment",)),
        VenueBooking.starts_at < b, VenueBooking.ends_at > a)
    if space_id:
        bq = bq.where(VenueBooking.space_id == space_id)
    busy = [{"space_id": s, "starts_at": x, "ends_at": y} for s, x, y in (await db.execute(bq)).all()]
    blq = select(VenueBlock.space_id, VenueBlock.starts_at, VenueBlock.ends_at).where(
        VenueBlock.venue_id == v.id, VenueBlock.starts_at < b, VenueBlock.ends_at > a)
    for s, x, y in (await db.execute(blq)).all():
        if not space_id or s in (None, space_id):
            busy.append({"space_id": s, "starts_at": x, "ends_at": y})
    return {"busy": busy}


@router.get("/api/venues/{slug}/reviews")
async def venue_reviews(slug: str, kind: str | None = Query(None, pattern="^(organizer|guest)$"),
                        db: AsyncSession = Depends(get_db)):
    v = await _public_venue(db, slug)
    q = select(VenueReview, User).join(User, User.id == VenueReview.author_id).where(
        VenueReview.venue_id == v.id, VenueReview.is_hidden == False)  # noqa: E712
    if kind:
        q = q.where(VenueReview.kind == kind)
    rows = (await db.execute(q.order_by(VenueReview.created_at.desc()).limit(100))).all()
    return [{"id": r.id, "kind": r.kind, "rating": r.rating, "body": r.body, "venue_reply": r.venue_reply,
             "venue_reply_at": r.venue_reply_at, "created_at": r.created_at,
             "author": user_brief(u) | {"is_plus": is_plus(u) and u.show_plus_badge}} for r, u in rows]


@router.get("/api/venues/{slug}/events")
async def venue_events(slug: str, db: AsyncSession = Depends(get_db)):
    v = await _public_venue(db, slug)
    rows = (await db.execute(select(Event).where(
        or_(Event.venue_id == v.id, Event.host_venue_id == v.id), Event.status == "published",
        Event.review_status == "approved", Event.end_date >= utcnow(),
    ).order_by(Event.start_date).limit(50))).scalars().all()
    return [{"id": e.id, "slug": e.slug, "title": e.title, "cover_image": e.cover_image,
             "start_date": e.start_date, "is_free": e.is_free, "price_min": e.price_min,
             "hosted_by_venue": e.host_venue_id == v.id, "members_only": e.members_only} for e in rows]


@router.post("/api/venues/{slug}/follow")
async def follow_venue(slug: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v = await _public_venue(db, slug)
    existing = (await db.execute(select(VenueFollow).where(
        VenueFollow.venue_id == v.id, VenueFollow.user_id == user.id))).scalar_one_or_none()
    if not existing:
        db.add(VenueFollow(venue_id=v.id, user_id=user.id))
        v.followers_count = (v.followers_count or 0) + 1
    return {"following": True, "followers_count": v.followers_count}


@router.delete("/api/venues/{slug}/follow")
async def unfollow_venue(slug: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v = await _public_venue(db, slug)
    existing = (await db.execute(select(VenueFollow).where(
        VenueFollow.venue_id == v.id, VenueFollow.user_id == user.id))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        from sqlalchemy import update
        await db.execute(update(Venue).where(Venue.id == v.id).values(
            followers_count=decrement_to_zero(Venue.followers_count)))
    await db.flush()
    await db.refresh(v)
    return {"following": False, "followers_count": v.followers_count}


@router.get("/api/me/following-venues")
async def my_followed_venues(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Venue).join(VenueFollow, VenueFollow.venue_id == Venue.id).where(
        VenueFollow.user_id == user.id, Venue.status.in_(PUBLIC_STATUSES)).order_by(VenueFollow.created_at.desc()))).scalars().all()
    return [await venue_card(db, v) for v in rows]
