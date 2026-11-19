"""Venue portal (web only): listing setup, verification documents, bank/payouts, team,
calendar, media, deals, Pro, featured placement, analytics, venue-hosted events
(docs/venues-spec.md 4.1, 4.6, 4.9, 4.10, section 5)."""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.event import Event
from app.models.user import User
from app.models.venue import (
    Area, Deal, DealRedemption, EnquiryMessage, FeaturedSlot, KycAccessLog, Subscription,
    SubscriptionPlan, Venue, VenueBlock, VenueBooking, VenueDocument, VenueEnquiry,
    VenueFollow, VenueInvite, VenueLedgerEntry, VenueMedia, VenueMember, VenueReview,
    VenueSpace,
)
from app.schemas.event import EventCreate
from app.schemas.venue import (
    BankIn, BlockIn, DealIn, FeaturedIn, InviteIn, MediaAdd, MediaOrder, MemberRoleIn,
    PayIn, RedeemIn, ReplyIn, SpaceIn, SubscribeIn, VenueCreate, VenueUpdate,
)
from app.services import kyc_store
from app.services.places import normalize_state, slugify
from app.services.plus import cancel_subscription, is_plus, is_pro, start_subscription
from app.services.settings import get_platform_settings
from app.services.venue_access import (
    ROLE_RANK, get_membership, notify, notify_venue_team, require_venue_role,
)
from app.services.venue_money import (
    PAID_BOOKING, ACTIVE_BOOKING, is_blocked, late_refund_requests, ledger_balance, naira,
    new_reference, start_turnup_payment, strikes_last_year,
)
from app.services.venue_policy import PRESET_LABELS
from app.services.venue_views import (
    _json_list, area_name, media_for, media_limits, space_out, user_brief, venue_card,
)

router = APIRouter(prefix="/api/venue-portal", tags=["venue portal"])

REQUIRED_DOCS = {"cac": "CAC certificate", "owner_id": "owner or manager ID"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _venue_private(db: AsyncSession, v: Venue, member: VenueMember) -> dict:
    spaces = list((await db.execute(select(VenueSpace).where(VenueSpace.venue_id == v.id).order_by(
        VenueSpace.sort_order))).scalars().all())
    docs = (await db.execute(select(VenueDocument).where(VenueDocument.venue_id == v.id).order_by(
        VenueDocument.created_at))).scalars().all()
    from app.models.venue import AgentVisit
    visit = (await db.execute(select(AgentVisit).where(AgentVisit.venue_id == v.id).order_by(
        AgentVisit.created_at.desc()))).scalars().first()
    pro_sub = (await db.execute(select(Subscription).where(
        Subscription.venue_id == v.id, Subscription.product == "venue_pro",
        Subscription.status.in_(["active", "non_renewing", "past_due"])))).scalars().first()
    return {
        **(await venue_card(db, v, None, spaces)),
        "my_role": member.role, "status": v.status, "pause_reason": v.pause_reason,
        "verification_status": v.verification_status, "verification_note": v.verification_note,
        "deposits_enabled": v.deposits_enabled, "description": v.description, "address": v.address,
        "area_other": v.area_other, "amenities": _json_list(v.amenities), "rules": v.rules,
        "phone": v.phone, "email": v.email, "price_display": v.price_display,
        "refund_preset": v.refund_preset, "refund_policy": PRESET_LABELS.get(v.refund_preset),
        "deposit_type": v.deposit_type, "deposit_value": v.deposit_value,
        "balance_due_days": v.balance_due_days,
        "legal_name": v.legal_name if member.role == "owner" else None,
        "cac_number": v.cac_number if member.role == "owner" else None,
        "registered_address": v.registered_address if member.role == "owner" else None,
        "bank": {"bank_name": v.bank_name, "account_last4": v.bank_account_last4,
                 "account_name": v.bank_account_name, "name_match": v.bank_name_match,
                 "ready": bool(v.paystack_subaccount_code)},
        "spaces": [space_out(s) for s in spaces],
        "media": await media_for(db, v, include_hidden=True), "limits": await media_limits(db, v),
        "documents": [{"id": d.id, "kind": d.kind, "status": d.status, "original_filename": d.original_filename,
                       "rejection_reason": d.rejection_reason, "created_at": d.created_at} for d in docs],
        "visit": {"status": visit.status, "scheduled_for": visit.scheduled_for} if visit else None,
        "pro": {"active": is_pro(v), "until": v.pro_until,
                "status": pro_sub.status if pro_sub else None, "plan_code": pro_sub.plan_code if pro_sub else None},
        "balance_kobo": await ledger_balance(db, v.id),
        "late_refunds": len(await late_refund_requests(db, v.id)),
        "strikes_last_year": await strikes_last_year(db, v.id),
        "checklist": await _submission_checklist(db, v),
    }


async def _submission_checklist(db: AsyncSession, v: Venue) -> list[dict]:
    spaces = (await db.execute(select(func.count()).select_from(VenueSpace).where(
        VenueSpace.venue_id == v.id, VenueSpace.is_active == True))).scalar_one()  # noqa: E712
    photos = (await db.execute(select(func.count()).select_from(VenueMedia).where(
        VenueMedia.venue_id == v.id, VenueMedia.kind == "photo"))).scalar_one()
    kinds = set((await db.execute(select(VenueDocument.kind).where(
        VenueDocument.venue_id == v.id, VenueDocument.status != "rejected"))).scalars().all())
    return [
        {"id": "details", "label": "Venue details and map pin", "done": bool(v.latitude and v.address)},
        {"id": "spaces", "label": "At least one space", "done": spaces > 0},
        {"id": "photos", "label": "At least one photo", "done": photos > 0},
        {"id": "legal", "label": "Registered business name and CAC number", "done": bool(v.legal_name and v.cac_number)},
        {"id": "cac", "label": "CAC certificate uploaded", "done": "cac" in kinds},
        {"id": "owner_id", "label": "Owner or manager ID uploaded", "done": "owner_id" in kinds},
        {"id": "site", "label": "Site photos or video uploaded", "done": bool(kinds & {"site_photo", "site_video"})},
        {"id": "bank", "label": "Payout bank account", "done": bool(v.paystack_subaccount_code)},
    ]


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)[:100] or "venue"
    slug = base
    while (await db.execute(select(Venue.id).where(Venue.slug == slug))).first():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


async def _check_area(db: AsyncSession, state: str, area_id: str | None) -> None:
    if area_id:
        area = (await db.execute(select(Area).where(Area.id == area_id))).scalar_one_or_none()
        if not area or area.state != state:
            raise HTTPException(400, "That area isn't in the chosen state.")


# ── My venues ───────────────────────────────────────────────────────────────────

@router.get("/venues")
async def my_venues(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Venue, VenueMember.role).join(VenueMember, VenueMember.venue_id == Venue.id).where(
        VenueMember.user_id == user.id, Venue.status != "closed").order_by(Venue.created_at))).all()
    return [{**(await venue_card(db, v)), "my_role": role, "status": v.status,
             "verification_status": v.verification_status} for v, role in rows]


@router.post("/venues", status_code=201)
@limiter.limit("10/hour")
async def create_venue(request: Request, payload: VenueCreate, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    if await is_blocked(db, user_id=user.id):
        raise HTTPException(403, "This account can't list venues while a referred refund is unpaid.")
    state = normalize_state(payload.state)
    if not state:
        raise HTTPException(400, "Unknown state")
    await _check_area(db, state, payload.area_id)
    v = Venue(slug=await _unique_slug(db, payload.name), name=payload.name.strip(), type=payload.type,
              description=payload.description, state=state, area_id=payload.area_id,
              area_other=None if payload.area_id else (payload.area_other or "").strip(),
              address=payload.address, latitude=payload.latitude, longitude=payload.longitude,
              created_by_id=user.id)
    db.add(v)
    await db.flush()
    member = VenueMember(venue_id=v.id, user_id=user.id, role="owner")
    db.add(member)
    await db.flush()
    return await _venue_private(db, v, member)


@router.get("/venues/{venue_id}")
async def get_my_venue(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, member = await require_venue_role(db, venue_id, user, "viewer")
    return await _venue_private(db, v, member)


@router.patch("/venues/{venue_id}")
async def update_venue(venue_id: str, payload: VenueUpdate, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, member = await require_venue_role(db, venue_id, user, "manager")
    changes = payload.model_dump(exclude_unset=True)
    legal = {"legal_name", "cac_number", "registered_address"} & changes.keys()
    if legal and member.role != "owner":
        raise HTTPException(403, "Only the Owner can change the legal details.")
    if legal and v.verification_status in ("documents_approved", "visit_passed"):
        raise HTTPException(409, "Legal details are locked after verification. Contact Turnup support to change them.")
    if "cac_number" in changes and changes["cac_number"] and await is_blocked(db, cac=changes["cac_number"]):
        raise HTTPException(403, "This business can't list venues while a referred refund is unpaid.")
    if "state" in changes:
        st = normalize_state(changes["state"] or "")
        if not st:
            raise HTTPException(400, "Unknown state")
        changes["state"] = st
    state = changes.get("state", v.state)
    if "area_id" in changes or "state" in changes:
        await _check_area(db, state, changes.get("area_id", v.area_id))
    if "amenities" in changes:
        changes["amenities"] = json.dumps(changes["amenities"] or [])
    if changes.get("area_id"):
        changes["area_other"] = None
    for k, val in changes.items():
        setattr(v, k, val)
    await db.flush()
    return await _venue_private(db, v, member)


@router.delete("/venues/{venue_id}", status_code=204)
async def close_venue(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    upcoming = (await db.execute(select(VenueBooking.id).where(
        VenueBooking.venue_id == v.id, VenueBooking.status.in_(ACTIVE_BOOKING),
        VenueBooking.ends_at > utcnow()))).first()
    if upcoming:
        raise HTTPException(409, "This venue has upcoming bookings. Complete or cancel them first.")
    if await late_refund_requests(db, v.id) or await ledger_balance(db, v.id) > 0:
        raise HTTPException(409, "Clear the venue's unpaid refunds and balance first.")
    v.status = "closed"
    v.closed_at = utcnow()
    # KYC files are kept 12 months after closing, then deleted by the worker (spec 8.2).
    await db.execute(update(VenueDocument).where(VenueDocument.venue_id == v.id).values(
        delete_after=utcnow() + timedelta(days=365)))


# ── Spaces ──────────────────────────────────────────────────────────────────────

@router.post("/venues/{venue_id}/spaces", status_code=201)
async def add_space(venue_id: str, payload: SpaceIn, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    s = VenueSpace(venue_id=v.id, **payload.model_dump())
    db.add(s)
    await db.flush()
    return space_out(s)


async def _space(db: AsyncSession, venue_id: str, space_id: str) -> VenueSpace:
    s = (await db.execute(select(VenueSpace).where(VenueSpace.id == space_id, VenueSpace.venue_id == venue_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Space not found")
    return s


@router.put("/venues/{venue_id}/spaces/{space_id}")
async def update_space(venue_id: str, space_id: str, payload: SpaceIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    await require_venue_role(db, venue_id, user, "manager")
    s = await _space(db, venue_id, space_id)
    for k, val in payload.model_dump().items():
        setattr(s, k, val)
    await db.flush()
    return space_out(s)


@router.delete("/venues/{venue_id}/spaces/{space_id}", status_code=204)
async def delete_space(venue_id: str, space_id: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    await require_venue_role(db, venue_id, user, "manager")
    s = await _space(db, venue_id, space_id)
    used = (await db.execute(select(VenueBooking.id).where(VenueBooking.space_id == s.id))).first()
    if used:
        s.is_active = False  # keep booking history intact
    else:
        await db.delete(s)


# ── Media ───────────────────────────────────────────────────────────────────────

@router.post("/venues/{venue_id}/media", status_code=201)
async def add_media(venue_id: str, payload: MediaAdd, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    limits = await media_limits(db, v)
    count = (await db.execute(select(func.count()).select_from(VenueMedia).where(
        VenueMedia.venue_id == v.id, VenueMedia.kind == payload.kind))).scalar_one()
    limit = limits["photos" if payload.kind == "photo" else "videos"]
    if count >= limit:
        extra = "" if is_pro(v) else " Venue Pro raises the limit."
        raise HTTPException(409, f"Your plan allows {limit} {payload.kind}s.{extra}")
    if payload.space_id:
        await _space(db, v.id, payload.space_id)
    if payload.kind == "video" and payload.duration_s and payload.duration_s > settings.venue_video_max_seconds:
        raise HTTPException(400, f"Videos can be up to {settings.venue_video_max_seconds} seconds.")
    top = (await db.execute(select(func.max(VenueMedia.sort_order)).where(VenueMedia.venue_id == v.id))).scalar() or 0
    m = VenueMedia(venue_id=v.id, sort_order=top + 1, **payload.model_dump())
    db.add(m)
    if payload.kind == "photo" and not v.cover_image:
        v.cover_image = payload.url
    await db.flush()
    return await media_for(db, v, include_hidden=True)


@router.put("/venues/{venue_id}/media/order")
async def reorder_media(venue_id: str, payload: MediaOrder, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    rows = {m.id: m for m in (await db.execute(select(VenueMedia).where(VenueMedia.venue_id == v.id))).scalars().all()}
    for i, mid in enumerate(payload.ids):
        if mid in rows:
            rows[mid].sort_order = i
    await db.flush()
    return await media_for(db, v, include_hidden=True)


@router.delete("/venues/{venue_id}/media/{media_id}")
async def delete_media(venue_id: str, media_id: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    m = (await db.execute(select(VenueMedia).where(VenueMedia.id == media_id, VenueMedia.venue_id == v.id))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Not found")
    await db.delete(m)
    if v.cover_image == m.url:
        v.cover_image = None
    await db.flush()
    return await media_for(db, v, include_hidden=True)


# ── Verification documents (private store) ──────────────────────────────────────

@router.post("/venues/{venue_id}/documents", status_code=201)
@limiter.limit("30/hour")
async def upload_document(request: Request, venue_id: str, kind: str = Form(...), file: UploadFile = File(...),
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    if kind not in ("cac", "owner_id", "site_photo", "site_video", "other"):
        raise HTTPException(400, "Unknown document type")
    limit = settings.venue_video_max_mb * 1024 * 1024 if kind == "site_video" else kyc_store.MAX_DOC_BYTES
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, "That file is too large.")
    data, ctype, ext = kyc_store.prepare(raw, allow_pdf=kind in ("cac", "owner_id", "other"),
                                         allow_video=kind == "site_video")
    if kind == "site_video" and not ctype.startswith("video/"):
        raise HTTPException(415, "Upload an MP4, MOV or WebM video.")
    key = kyc_store.save(data, ext)
    doc = VenueDocument(venue_id=v.id, kind=kind, storage_key=key, original_filename=(file.filename or "")[:200],
                        content_type=ctype, size_bytes=len(data), uploaded_by_id=user.id)
    db.add(doc)
    await db.flush()
    return {"id": doc.id, "kind": doc.kind, "status": doc.status, "original_filename": doc.original_filename,
            "created_at": doc.created_at}


@router.delete("/venues/{venue_id}/documents/{doc_id}", status_code=204)
async def delete_document(venue_id: str, doc_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    doc = (await db.execute(select(VenueDocument).where(VenueDocument.id == doc_id, VenueDocument.venue_id == v.id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Not found")
    if doc.status == "approved":
        raise HTTPException(409, "Approved documents can't be removed.")
    kyc_store.delete(doc.storage_key)
    await db.delete(doc)


# ── Bank account / Paystack subaccount ──────────────────────────────────────────

@router.get("/banks")
async def banks(user: User = Depends(get_current_user)):
    from app.services.paystack import PaystackConfigError, list_banks
    try:
        return await list_banks()
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))


def _name_tokens(name: str | None) -> set[str]:
    stop = {"ltd", "limited", "plc", "nig", "nigeria", "enterprise", "enterprises", "ventures", "and", "the", "co"}
    return {t for t in "".join(c if c.isalnum() else " " for c in (name or "").lower()).split() if t not in stop and len(t) > 1}


@router.put("/venues/{venue_id}/bank")
@limiter.limit("10/hour")
async def set_bank(request: Request, venue_id: str, payload: BankIn, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    from app.services.paystack import PaystackConfigError, create_subaccount, list_banks, resolve_account
    v, member = await require_venue_role(db, venue_id, user, "owner")
    if await is_blocked(db, bank_account=payload.account_number):
        raise HTTPException(403, "This bank account can't receive venue payouts while a referred refund is unpaid.")
    try:
        account_name = await resolve_account(payload.account_number, payload.bank_code)
        bank_list = await list_banks()
        code = await create_subaccount(v.legal_name or v.name, payload.bank_code, payload.account_number,
                                       v.paystack_subaccount_code)
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(400, "We couldn't verify that account number with the bank. Check it and try again.")
    names = _name_tokens(account_name)
    match = bool(names & (_name_tokens(v.legal_name) | _name_tokens(user.full_name)))
    v.bank_code = payload.bank_code
    v.bank_name = next((b["name"] for b in bank_list if b["code"] == payload.bank_code), payload.bank_code)
    v.bank_account_last4 = payload.account_number[-4:]
    v.bank_account_name = account_name
    v.bank_account_hash = kyc_store.identity_hash(payload.account_number)
    v.bank_name_match = match
    v.paystack_subaccount_code = code
    await db.flush()
    return await _venue_private(db, v, member)


@router.post("/venues/{venue_id}/submit")
async def submit_for_review(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, member = await require_venue_role(db, venue_id, user, "owner")
    if v.status not in ("draft", "in_review") or v.verification_status not in ("none", "rejected", "documents_submitted"):
        raise HTTPException(409, "This venue has already been reviewed.")
    missing = [c["label"] for c in await _submission_checklist(db, v) if not c["done"]]
    if missing:
        raise HTTPException(400, "Still needed: " + "; ".join(missing))
    if await is_blocked(db, cac=v.cac_number, user_id=user.id):
        raise HTTPException(403, "This business can't list venues while a referred refund is unpaid.")
    v.status = "in_review"
    v.verification_status = "documents_submitted"
    v.verification_note = None
    admins = (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all()
    for aid in admins:
        notify(db, aid, "venue_review_needed", f"New venue to verify: {v.name}", reference_id=v.id,
               reference_type="venue")
    await db.flush()
    return await _venue_private(db, v, member)


# ── Team ────────────────────────────────────────────────────────────────────────

@router.get("/venues/{venue_id}/members")
async def list_members(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, member = await require_venue_role(db, venue_id, user, "viewer")
    rows = (await db.execute(select(VenueMember, User).join(User, User.id == VenueMember.user_id).where(
        VenueMember.venue_id == v.id).order_by(VenueMember.created_at))).all()
    invites = []
    if member.role == "owner":
        invites = (await db.execute(select(VenueInvite).where(
            VenueInvite.venue_id == v.id, VenueInvite.accepted_at.is_(None),
            VenueInvite.expires_at > utcnow()))).scalars().all()
    return {"members": [{"user": user_brief(u), "role": m.role, "created_at": m.created_at} for m, u in rows],
            "invites": [{"id": i.id, "email": i.email, "role": i.role, "expires_at": i.expires_at} for i in invites],
            "seats": (await media_limits(db, v))["team_seats"]}


@router.post("/venues/{venue_id}/invites", status_code=201)
@limiter.limit("30/hour")
async def invite_member(request: Request, venue_id: str, payload: InviteIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from app.services.email import _esc, send_email
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    seats = (await media_limits(db, v))["team_seats"]
    used = (await db.execute(select(func.count()).select_from(VenueMember).where(VenueMember.venue_id == v.id))).scalar_one()
    pending = (await db.execute(select(func.count()).select_from(VenueInvite).where(
        VenueInvite.venue_id == v.id, VenueInvite.accepted_at.is_(None), VenueInvite.expires_at > utcnow()))).scalar_one()
    if used + pending >= seats:
        raise HTTPException(409, f"Your plan has {seats} team seats." + ("" if is_pro(v) else " Venue Pro adds more."))
    token = secrets.token_urlsafe(32)
    inv = VenueInvite(venue_id=v.id, email=payload.email.strip().lower(), role=payload.role,
                      token_hash=hashlib.sha256(token.encode()).hexdigest(), invited_by_id=user.id,
                      expires_at=utcnow() + timedelta(days=7))
    db.add(inv)
    await db.flush()
    link = f"{settings.frontend_url.rstrip('/')}/venue/invite?token={token}"
    try:
        await send_email(inv.email, f"Join {v.name} on Turnup",
                         f"<p>{_esc(user.display_name or user.username)} invited you to help manage "
                         f"<strong>{_esc(v.name)}</strong> on Turnup as a {payload.role}.</p>"
                         f'<p><a href="{link}">Accept the invitation</a> (valid for 7 days).</p>')
    except Exception:
        pass
    return {"id": inv.id, "email": inv.email, "role": inv.role, "expires_at": inv.expires_at,
            "link": link if settings.debug else None}


@router.post("/invites/accept")
async def accept_invite(token: str = Query(..., min_length=10), db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    inv = (await db.execute(select(VenueInvite).where(
        VenueInvite.token_hash == hashlib.sha256(token.encode()).hexdigest()))).scalar_one_or_none()
    if not inv or inv.accepted_at or _utc(inv.expires_at) < utcnow():
        raise HTTPException(400, "This invitation is invalid or has expired.")
    if (user.email or "").lower() != inv.email:
        raise HTTPException(403, "This invitation was sent to a different email address.")
    if not await get_membership(db, inv.venue_id, user.id):
        db.add(VenueMember(venue_id=inv.venue_id, user_id=user.id, role=inv.role, invited_by_id=inv.invited_by_id))
    inv.accepted_at = utcnow()
    await db.flush()
    return {"venue_id": inv.venue_id}


@router.delete("/venues/{venue_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(venue_id: str, invite_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    inv = (await db.execute(select(VenueInvite).where(VenueInvite.id == invite_id, VenueInvite.venue_id == v.id))).scalar_one_or_none()
    if inv:
        await db.delete(inv)


@router.patch("/venues/{venue_id}/members/{user_id}")
async def change_role(venue_id: str, user_id: str, payload: MemberRoleIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    v, me = await require_venue_role(db, venue_id, user, "owner")
    target = await get_membership(db, v.id, user_id)
    if not target:
        raise HTTPException(404, "Not on this team")
    if payload.role == "owner":
        # Transfer ownership: exactly one Owner.
        if target.role != "manager":
            raise HTTPException(400, "Ownership can only be transferred to a Manager.")
        target.role = "owner"
        me.role = "manager"
        notify(db, user_id, "venue_ownership", f"You're now the Owner of {v.name}", reference_id=v.id,
               reference_type="venue")
    else:
        if target.user_id == user.id:
            raise HTTPException(400, "Transfer ownership first.")
        target.role = payload.role
    await db.flush()
    return {"ok": True}


@router.delete("/venues/{venue_id}/members/{user_id}", status_code=204)
async def remove_member(venue_id: str, user_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, me = await require_venue_role(db, venue_id, user, "viewer")
    target = await get_membership(db, v.id, user_id)
    if not target:
        raise HTTPException(404, "Not on this team")
    if target.role == "owner":
        raise HTTPException(400, "The Owner can't be removed. Transfer ownership first.")
    if user_id != user.id and me.role != "owner":
        raise HTTPException(403, "Only the Owner can remove team members.")
    await db.delete(target)


# ── Calendar ────────────────────────────────────────────────────────────────────

def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/venues/{venue_id}/calendar")
async def calendar(venue_id: str, start: datetime, end: datetime, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    bookings = (await db.execute(select(VenueBooking, User).join(User, User.id == VenueBooking.organizer_id).where(
        VenueBooking.venue_id == v.id, VenueBooking.status.in_(ACTIVE_BOOKING + ("completed",)),
        VenueBooking.starts_at < end, VenueBooking.ends_at > start))).all()
    blocks = (await db.execute(select(VenueBlock).where(
        VenueBlock.venue_id == v.id, VenueBlock.starts_at < end, VenueBlock.ends_at > start))).scalars().all()
    return {
        "bookings": [{"id": b.id, "space_id": b.space_id, "starts_at": b.starts_at, "ends_at": b.ends_at,
                      "status": b.status, "organizer": user_brief(u)} for b, u in bookings],
        "blocks": [{"id": b.id, "space_id": b.space_id, "starts_at": b.starts_at, "ends_at": b.ends_at,
                    "note": b.note} for b in blocks],
    }


@router.post("/venues/{venue_id}/blocks", status_code=201)
async def add_block(venue_id: str, payload: BlockIn, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    if payload.space_id:
        await _space(db, v.id, payload.space_id)
    b = VenueBlock(venue_id=v.id, created_by_id=user.id, **payload.model_dump())
    db.add(b)
    await db.flush()
    return {"id": b.id, "space_id": b.space_id, "starts_at": b.starts_at, "ends_at": b.ends_at, "note": b.note}


@router.delete("/venues/{venue_id}/blocks/{block_id}", status_code=204)
async def delete_block(venue_id: str, block_id: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    b = (await db.execute(select(VenueBlock).where(VenueBlock.id == block_id, VenueBlock.venue_id == v.id))).scalar_one_or_none()
    if b:
        await db.delete(b)


# ── Reviews ─────────────────────────────────────────────────────────────────────

@router.get("/venues/{venue_id}/reviews")
async def portal_reviews(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    rows = (await db.execute(select(VenueReview, User).join(User, User.id == VenueReview.author_id).where(
        VenueReview.venue_id == v.id).order_by(VenueReview.created_at.desc()))).all()
    return [{"id": r.id, "kind": r.kind, "rating": r.rating, "body": r.body, "venue_reply": r.venue_reply,
             "is_hidden": r.is_hidden, "created_at": r.created_at, "author": user_brief(u)} for r, u in rows]


@router.put("/venues/{venue_id}/reviews/{review_id}/reply")
async def reply_review(venue_id: str, review_id: str, payload: ReplyIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    r = (await db.execute(select(VenueReview).where(VenueReview.id == review_id, VenueReview.venue_id == v.id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Not found")
    r.venue_reply = payload.body
    r.venue_reply_at = utcnow()
    await db.flush()
    return {"ok": True}


# ── Balance (money owed to Turnup) ──────────────────────────────────────────────

@router.get("/venues/{venue_id}/ledger")
async def ledger(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    rows = (await db.execute(select(VenueLedgerEntry).where(VenueLedgerEntry.venue_id == v.id).order_by(
        VenueLedgerEntry.created_at.desc()))).scalars().all()
    return {"balance_kobo": await ledger_balance(db, v.id),
            "entries": [{"id": e.id, "kind": e.kind, "amount_kobo": e.amount_kobo, "note": e.note,
                         "booking_id": e.booking_id, "refund_request_id": e.refund_request_id,
                         "created_at": e.created_at} for e in rows]}


@router.post("/venues/{venue_id}/ledger/pay")
async def pay_balance(venue_id: str, payload: PayIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    owed = await ledger_balance(db, v.id)
    if owed <= 0:
        raise HTTPException(409, "Nothing is owed.")
    amount = min(payload.amount_kobo or owed, owed)
    payment, url = await start_turnup_payment(db, venue=v, payer=user, kind="debt_payment", amount_kobo=amount,
                                              prefix="vd", callback_url=payload.callback_url)
    return {"reference": payment.reference, "authorization_url": url, "amount_kobo": amount}


# ── Deals (Turnup+) ─────────────────────────────────────────────────────────────

def deal_out(d: Deal, redemptions: int = 0) -> dict:
    return {"id": d.id, "title": d.title, "description": d.description, "kind": d.kind,
            "valid_from": d.valid_from, "valid_to": d.valid_to, "max_per_member": d.max_per_member,
            "is_active": d.is_active, "redemptions": redemptions, "venue_id": d.venue_id, "event_id": d.event_id}


@router.get("/venues/{venue_id}/deals")
async def list_deals(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    rows = (await db.execute(select(Deal).where(Deal.venue_id == v.id).order_by(Deal.created_at.desc()))).scalars().all()
    counts = dict((await db.execute(select(DealRedemption.deal_id, func.count()).where(
        DealRedemption.deal_id.in_([d.id for d in rows]), DealRedemption.redeemed_at.is_not(None)).group_by(
        DealRedemption.deal_id))).all()) if rows else {}
    return [deal_out(d, counts.get(d.id, 0)) for d in rows]


@router.post("/venues/{venue_id}/deals", status_code=201)
async def create_deal(venue_id: str, payload: DealIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    d = Deal(venue_id=v.id, created_by_id=user.id, **payload.model_dump())
    db.add(d)
    await db.flush()
    return deal_out(d)


@router.put("/venues/{venue_id}/deals/{deal_id}")
async def update_deal(venue_id: str, deal_id: str, payload: DealIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    d = (await db.execute(select(Deal).where(Deal.id == deal_id, Deal.venue_id == v.id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    for k, val in payload.model_dump().items():
        setattr(d, k, val)
    await db.flush()
    return deal_out(d)


@router.post("/venues/{venue_id}/deals/redeem")
async def redeem_deal(venue_id: str, payload: RedeemIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Door check of a member's deal code (any team member can scan)."""
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    from app.services.deals import redeem_code
    return await redeem_code(db, payload.code, user, venue_id=v.id)


# ── Venue Pro ───────────────────────────────────────────────────────────────────

@router.get("/plans")
async def plans(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active == True))).scalars().all()  # noqa: E712
    return [{"code": p.code, "product": p.product, "name": p.name, "amount_kobo": p.amount_kobo,
             "interval": p.interval} for p in rows]


@router.post("/venues/{venue_id}/pro")
async def subscribe_pro(venue_id: str, payload: SubscribeIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    sub, url = await start_subscription(db, user=user, plan_code=payload.plan_code, venue=v,
                                        callback_url=payload.callback_url)
    return {"reference": sub.reference, "authorization_url": url}


@router.delete("/venues/{venue_id}/pro")
async def cancel_pro(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "owner")
    sub = (await db.execute(select(Subscription).where(
        Subscription.venue_id == v.id, Subscription.product == "venue_pro",
        Subscription.status.in_(["active", "past_due"])))).scalars().first()
    if not sub:
        raise HTTPException(404, "No active Venue Pro subscription.")
    await cancel_subscription(db, sub)
    return {"status": sub.status, "until": v.pro_until}


# ── Featured placement ──────────────────────────────────────────────────────────

def _monday(d: datetime) -> datetime:
    d = d.astimezone(timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(days=d.weekday())


async def _slots_taken(db: AsyncSession, scope: str, state: str, area_id: str | None, week: datetime) -> int:
    q = select(func.count()).select_from(FeaturedSlot).where(
        FeaturedSlot.scope == scope, FeaturedSlot.state == state, FeaturedSlot.week_start == week,
        or_(FeaturedSlot.status == "active",
            (FeaturedSlot.status == "pending") & (FeaturedSlot.created_at > utcnow() - timedelta(minutes=30))))
    if scope == "area":
        q = q.where(FeaturedSlot.area_id == area_id)
    return (await db.execute(q)).scalar_one()


@router.get("/venues/{venue_id}/featured")
async def featured_options(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    ps = await get_platform_settings(db)
    start = _monday(utcnow()) + timedelta(days=7)
    weeks = []
    for i in range(12):
        wk = start + timedelta(days=7 * i)
        weeks.append({
            "week_start": wk.date().isoformat(),
            "state_left": max(ps.featured_max_per_state - await _slots_taken(db, "state", v.state, None, wk), 0),
            "area_left": max(ps.featured_max_per_area - await _slots_taken(db, "area", v.state, v.area_id, wk), 0)
            if v.area_id else 0,
        })
    mine = (await db.execute(select(FeaturedSlot).where(FeaturedSlot.venue_id == v.id, FeaturedSlot.status.in_(
        ["active", "pending"])).order_by(FeaturedSlot.week_start))).scalars().all()
    return {"state": v.state, "area": await area_name(db, v), "area_available": bool(v.area_id),
            "price_state_kobo": ps.featured_state_week_kobo, "price_area_kobo": ps.featured_area_week_kobo,
            "weeks": weeks,
            "mine": [{"id": s.id, "scope": s.scope, "week_start": s.week_start, "status": s.status} for s in mine]}


@router.post("/venues/{venue_id}/featured")
async def buy_featured(venue_id: str, payload: FeaturedIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    if v.status != "live":
        raise HTTPException(409, "Only live venues can be featured.")
    if payload.scope == "area" and not v.area_id:
        raise HTTPException(409, "Area placement needs a listed area. Ask support to add yours.")
    ps = await get_platform_settings(db)
    cap = ps.featured_max_per_state if payload.scope == "state" else ps.featured_max_per_area
    price = ps.featured_state_week_kobo if payload.scope == "state" else ps.featured_area_week_kobo
    earliest = _monday(utcnow())
    weeks = []
    for w in sorted(set(payload.weeks)):
        try:
            wk = datetime.fromisoformat(w).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, f"Bad week: {w}")
        if wk.weekday() != 0 or wk < earliest:
            raise HTTPException(400, f"{w} isn't an upcoming Monday.")
        if await _slots_taken(db, payload.scope, v.state, v.area_id if payload.scope == "area" else None, wk) >= cap:
            raise HTTPException(409, f"The week of {w} is full.")
        dup = (await db.execute(select(FeaturedSlot.id).where(
            FeaturedSlot.venue_id == v.id, FeaturedSlot.scope == payload.scope, FeaturedSlot.week_start == wk,
            FeaturedSlot.status.in_(["active", "pending"])))).first()
        if dup:
            raise HTTPException(409, f"You already have the week of {w}.")
        weeks.append(wk)
    payment, url = await start_turnup_payment(db, venue=v, payer=user, kind="featured",
                                              amount_kobo=price * len(weeks), prefix="vf",
                                              callback_url=payload.callback_url)
    for wk in weeks:
        db.add(FeaturedSlot(venue_id=v.id, scope=payload.scope, state=v.state,
                            area_id=v.area_id if payload.scope == "area" else None, week_start=wk,
                            ends_at=wk + timedelta(days=7), amount_kobo=price, payment_reference=payment.reference))
    await db.flush()
    return {"reference": payment.reference, "authorization_url": url, "amount_kobo": price * len(weeks)}


# ── Analytics (Venue Pro) ───────────────────────────────────────────────────────

@router.get("/venues/{venue_id}/analytics")
async def analytics(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    if not is_pro(v):
        raise HTTPException(402, "Analytics are part of Venue Pro.")
    since = utcnow() - timedelta(days=90)
    enquiries = (await db.execute(select(func.count()).select_from(VenueEnquiry).where(
        VenueEnquiry.venue_id == v.id, VenueEnquiry.created_at >= since))).scalar_one()
    booked = (await db.execute(select(func.count()).select_from(VenueBooking).where(
        VenueBooking.venue_id == v.id, VenueBooking.created_at >= since,
        VenueBooking.status.in_(PAID_BOOKING + ("completed",))))).scalar_one()
    follows = (await db.execute(select(func.count()).select_from(VenueFollow).where(
        VenueFollow.venue_id == v.id, VenueFollow.created_at >= since))).scalar_one()
    revenue = (await db.execute(select(func.coalesce(func.sum(VenueBooking.paid_kobo), 0)).where(
        VenueBooking.venue_id == v.id, VenueBooking.created_at >= since,
        VenueBooking.status.in_(PAID_BOOKING + ("completed",))))).scalar_one()
    replies = (await db.execute(select(func.count()).select_from(EnquiryMessage).join(
        VenueEnquiry, VenueEnquiry.id == EnquiryMessage.enquiry_id).where(
        VenueEnquiry.venue_id == v.id, EnquiryMessage.sender_side == "venue",
        EnquiryMessage.created_at >= since))).scalar_one()
    return {"period_days": 90, "profile_views": v.views_count, "enquiries": enquiries, "bookings": booked,
            "conversion": round(booked / enquiries, 3) if enquiries else None, "new_followers": follows,
            "followers": v.followers_count, "booking_value_kobo": int(revenue), "venue_replies": replies}


# ── Venue-hosted events ─────────────────────────────────────────────────────────

@router.get("/venues/{venue_id}/events")
async def venue_hosted_events(venue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    v, _ = await require_venue_role(db, venue_id, user, "viewer")
    rows = (await db.execute(select(Event).where(Event.host_venue_id == v.id).order_by(Event.start_date.desc()))).scalars().all()
    return [{"id": e.id, "slug": e.slug, "title": e.title, "start_date": e.start_date, "status": e.status,
             "review_status": e.review_status, "attendees_count": e.attendees_count,
             "members_only": e.members_only} for e in rows]


@router.post("/venues/{venue_id}/events", status_code=201)
async def create_venue_event(venue_id: str, payload: EventCreate, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """The venue is the host; the member who created it is kept as host_id for audit.
    Goes through the normal approval queue like any organizer event."""
    from app.routers.events import _slugify
    v, _ = await require_venue_role(db, venue_id, user, "manager")
    if v.status != "live":
        raise HTTPException(409, "Only live venues can publish events.")
    data = payload.model_dump()
    data.pop("template_id", None)
    data.update(venue_name=v.name, address=v.address, city=(await area_name(db, v)) or v.state,
                latitude=v.latitude, longitude=v.longitude, country="NG")
    if user.role == "admin":
        data["review_status"] = "approved"
    else:
        data["review_status"] = "pending"
        data["status"] = "draft"
    eid = str(uuid.uuid4())
    event = Event(id=eid, slug=_slugify(payload.title, eid), host_id=user.id, host_venue_id=v.id,
                  venue_id=v.id, **data)
    db.add(event)
    await db.flush()
    if event.status == "published" and event.review_status == "approved":
        from app.services.alerts import announce_event
        await announce_event(db, event)
    return {"id": event.id, "slug": event.slug, "status": event.status, "review_status": event.review_status}
