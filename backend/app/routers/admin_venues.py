"""Admin: venue verification, agents, disputes, refunds, ledgers, strikes, suspensions,
reports, chargebacks, areas, prices, featured slots, KYC access log, review moderation."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_admin, get_current_moderator
from app.models.user import User
from app.models.venue import (
    Agent, AgentVisit, Area, Chargeback, FeaturedSlot, KycAccessLog, OffPlatformReport, RefundRequest,
    SubscriptionPlan, Venue, VenueBooking, VenueDispute, VenueDocument, VenueLedgerEntry, VenueReview,
    VenueStrike,
)
from app.routers.agents import docs_with_links
from app.schemas.venue import (
    AgentIn, AreaIn, AreaUpdate, AssignIn, ChargebackDecision, DisputeDecision, DocumentDecision,
    LedgerAdjustIn, StrikeIn, SuspendIn, VerificationDecision,
)
from app.services.places import normalize_state, slugify
from app.services.settings import get_platform_settings
from app.services.venue_access import agent_states, notify, notify_venue_team
from app.services.venue_booking import decide_dispute
from app.services.venue_money import (
    add_strike, ledger_balance, restore_venue_if_clear, strikes_last_year, utcnow,
)
from app.services.venue_views import area_name, booking_out, refund_request_out, user_brief, venue_card

router = APIRouter(prefix="/api/admin", tags=["admin: venues"])


# ── Venues and verification ────────────────────────────────────────────────────

@router.get("/venues")
async def list_venues(status: str | None = None, verification: str | None = None, q: str | None = None,
                      db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    query = select(Venue)
    if status:
        query = query.where(Venue.status == status)
    if verification:
        query = query.where(Venue.verification_status == verification)
    if q:
        query = query.where(func.lower(Venue.name).like(f"%{q.lower()}%"))
    rows = (await db.execute(query.order_by(Venue.updated_at.desc()).limit(300))).scalars().all()
    return [{**(await venue_card(db, v)), "status": v.status, "verification_status": v.verification_status,
             "pause_reason": v.pause_reason, "area_other": v.area_other, "created_at": v.created_at} for v in rows]


@router.get("/venues/{venue_id}")
async def venue_detail(venue_id: str, request: Request, db: AsyncSession = Depends(get_db),
                       admin: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Venue not found")
    db.add(KycAccessLog(venue_id=v.id, user_id=admin.id, action="view",
                        ip=request.client.host if request.client else None))
    visits = (await db.execute(select(AgentVisit, User).join(User, User.id == AgentVisit.agent_id).where(
        AgentVisit.venue_id == v.id).order_by(AgentVisit.created_at.desc()))).all()
    strikes = (await db.execute(select(VenueStrike).where(VenueStrike.venue_id == v.id).order_by(
        VenueStrike.created_at.desc()))).scalars().all()
    rrs = (await db.execute(select(RefundRequest).where(RefundRequest.venue_id == v.id).order_by(
        RefundRequest.created_at.desc()))).scalars().all()
    from app.models.venue import VenueMember
    owners = (await db.execute(select(User).join(VenueMember, VenueMember.user_id == User.id).where(
        VenueMember.venue_id == v.id, VenueMember.role == "owner"))).scalars().all()
    return {
        **(await venue_card(db, v)), "status": v.status, "pause_reason": v.pause_reason,
        "verification_status": v.verification_status, "verification_note": v.verification_note,
        "deposits_enabled": v.deposits_enabled, "address": v.address, "description": v.description,
        "area_other": v.area_other, "legal_name": v.legal_name, "cac_number": v.cac_number,
        "registered_address": v.registered_address, "phone": v.phone, "email": v.email,
        "owners": [user_brief(o) | {"full_name": o.full_name, "email": o.email} for o in owners],
        "bank": {"bank_name": v.bank_name, "account_last4": v.bank_account_last4,
                 "account_name": v.bank_account_name, "name_match": v.bank_name_match,
                 "subaccount": v.paystack_subaccount_code},
        "documents": await docs_with_links(db, v.id, admin, request),
        "visits": [{"id": vi.id, "status": vi.status, "agent": user_brief(a), "scheduled_for": vi.scheduled_for,
                    "checked_in_at": vi.checked_in_at, "distance_from_venue_m": vi.distance_from_venue_m,
                    "distance_note": vi.distance_note, "checklist": json.loads(vi.checklist or "{}"),
                    "notes": vi.notes, "photos": len(json.loads(vi.photo_keys or "[]"))} for vi, a in visits],
        "strikes": [{"id": s.id, "reason": s.reason, "note": s.note, "created_at": s.created_at} for s in strikes],
        "strikes_last_year": await strikes_last_year(db, v.id),
        "balance_kobo": await ledger_balance(db, v.id),
        "refund_requests": [refund_request_out(r) for r in rrs],
    }


@router.post("/venues/{venue_id}/documents/{doc_id}")
async def decide_document(venue_id: str, doc_id: str, payload: DocumentDecision, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(get_current_admin)):
    d = (await db.execute(select(VenueDocument).where(
        VenueDocument.id == doc_id, VenueDocument.venue_id == venue_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    d.status = payload.status
    d.rejection_reason = payload.reason if payload.status == "rejected" else None
    d.reviewed_by_id = admin.id
    d.reviewed_at = utcnow()
    return {"ok": True}


@router.post("/venues/{venue_id}/verification")
async def decide_verification(venue_id: str, payload: VerificationDecision, db: AsyncSession = Depends(get_db),
                              admin: User = Depends(get_current_admin)):
    """Document review: approve = the listing goes live (deposits stay off until the visit)."""
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Venue not found")
    if v.verification_status != "documents_submitted":
        raise HTTPException(409, "This venue isn't waiting for document review.")
    v.verification_note = payload.note
    if payload.approve:
        v.verification_status = "documents_approved"
        v.status = "live"
        v.went_live_at = utcnow()
        await db.execute(update(VenueDocument).where(
            VenueDocument.venue_id == v.id, VenueDocument.status == "pending").values(
            status="approved", reviewed_by_id=admin.id, reviewed_at=utcnow()))
        await notify_venue_team(db, v.id, "venue_live", f"{v.name} is live on Turnup",
                                "Organizers can now enquire. Deposits open after Turnup's visit.",
                                reference_id=v.id, reference_type="venue", minimum="viewer")
        await _auto_assign(db, v, admin)
    else:
        v.verification_status = "rejected"
        v.status = "draft"
        await notify_venue_team(db, v.id, "venue_rejected", f"{v.name} needs changes before it can go live",
                                payload.note, reference_id=v.id, reference_type="venue", minimum="viewer")
    return {"status": v.status, "verification_status": v.verification_status}


async def _auto_assign(db: AsyncSession, v: Venue, admin: User) -> None:
    """Assign the active agent covering the venue's state with the fewest open visits."""
    agents = (await db.execute(select(Agent).where(Agent.is_active == True))).scalars().all()  # noqa: E712
    candidates = [a for a in agents if v.state in agent_states(a)]
    if not candidates:
        return
    loads = dict((await db.execute(select(AgentVisit.agent_id, func.count()).where(
        AgentVisit.status.in_(["assigned", "scheduled"])).group_by(AgentVisit.agent_id))).all())
    best = min(candidates, key=lambda a: loads.get(a.user_id, 0))
    db.add(AgentVisit(venue_id=v.id, agent_id=best.user_id, assigned_by_id=admin.id))
    notify(db, best.user_id, "agent_visit_assigned", f"New venue to visit: {v.name}", reference_id=v.id,
           reference_type="venue")


@router.post("/venues/{venue_id}/assign")
async def assign_agent(venue_id: str, payload: AssignIn, db: AsyncSession = Depends(get_db),
                       admin: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    agent = (await db.execute(select(Agent).where(Agent.user_id == payload.agent_id, Agent.is_active == True))).scalar_one_or_none()  # noqa: E712
    if not v or not agent:
        raise HTTPException(404, "Venue or agent not found")
    await db.execute(update(AgentVisit).where(
        AgentVisit.venue_id == v.id, AgentVisit.status.in_(["assigned", "scheduled"])).values(status="cancelled"))
    db.add(AgentVisit(venue_id=v.id, agent_id=agent.user_id, assigned_by_id=admin.id))
    notify(db, agent.user_id, "agent_visit_assigned", f"New venue to visit: {v.name}", reference_id=v.id,
           reference_type="venue")
    return {"ok": True}


@router.post("/venues/{venue_id}/suspend")
async def suspend_venue(venue_id: str, payload: SuspendIn, db: AsyncSession = Depends(get_db),
                        admin: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Venue not found")
    if payload.suspend:
        v.status = "suspended"
        v.pause_reason = "admin"
        await notify_venue_team(db, v.id, "venue_suspended", f"{v.name} is suspended", payload.note,
                                reference_id=v.id, reference_type="venue", minimum="viewer")
    else:
        v.status = "live" if v.verification_status in ("documents_approved", "visit_passed") else "draft"
        v.pause_reason = None
        await notify_venue_team(db, v.id, "venue_restored", f"{v.name} is live again", payload.note,
                                reference_id=v.id, reference_type="venue", minimum="viewer")
    return {"status": v.status}


@router.post("/venues/{venue_id}/strikes")
async def strike(venue_id: str, payload: StrikeIn, db: AsyncSession = Depends(get_db),
                 admin: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Venue not found")
    count = await add_strike(db, v, "admin", note=payload.reason, by=admin.id)
    return {"strikes_last_year": count, "status": v.status}


@router.post("/venues/{venue_id}/ledger")
async def adjust_ledger(venue_id: str, payload: LedgerAdjustIn, db: AsyncSession = Depends(get_db),
                        admin: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Venue not found")
    db.add(VenueLedgerEntry(venue_id=v.id, kind="adjustment", amount_kobo=payload.amount_kobo, note=payload.note,
                            created_by_id=admin.id))
    await db.flush()
    await restore_venue_if_clear(db, v)
    return {"balance_kobo": await ledger_balance(db, v.id)}


@router.put("/venues/{venue_id}/area")
async def map_area(venue_id: str, area_id: str = Query(...), db: AsyncSession = Depends(get_db),
                   _: User = Depends(get_current_admin)):
    v = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    a = (await db.execute(select(Area).where(Area.id == area_id))).scalar_one_or_none()
    if not v or not a or a.state != v.state:
        raise HTTPException(404, "Venue or area not found (the area must be in the venue's state)")
    v.area_id, v.area_other = a.id, None
    return {"ok": True}


# ── Agents ─────────────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(Agent, User).join(User, User.id == Agent.user_id))).all()
    loads = dict((await db.execute(select(AgentVisit.agent_id, func.count()).where(
        AgentVisit.status.in_(["assigned", "scheduled"])).group_by(AgentVisit.agent_id))).all())
    done = dict((await db.execute(select(AgentVisit.agent_id, func.count()).where(
        AgentVisit.status.in_(["passed", "failed"])).group_by(AgentVisit.agent_id))).all())
    return [{"user": user_brief(u) | {"email": u.email}, "states": agent_states(a), "phone": a.phone,
             "is_active": a.is_active, "open_visits": loads.get(a.user_id, 0),
             "completed_visits": done.get(a.user_id, 0)} for a, u in rows]


@router.put("/agents")
async def upsert_agent(payload: AgentIn, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = (await db.execute(select(User).where(User.id == payload.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    states = []
    for s in payload.states:
        st = normalize_state(s)
        if not st:
            raise HTTPException(400, f"Unknown state: {s}")
        states.append(st)
    a = (await db.execute(select(Agent).where(Agent.user_id == user.id))).scalar_one_or_none()
    if not a:
        a = Agent(user_id=user.id, created_by_id=admin.id)
        db.add(a)
    a.states, a.phone, a.is_active = json.dumps(sorted(set(states))), payload.phone, payload.is_active
    return {"ok": True}


# ── Disputes, refunds, reports, chargebacks ────────────────────────────────────

@router.get("/venue-disputes")
async def list_disputes(status: str = "open", db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(VenueDispute).where(VenueDispute.status == status).order_by(
        VenueDispute.created_at))).scalars().all()
    out = []
    for d in rows:
        b = (await db.execute(select(VenueBooking).where(VenueBooking.id == d.booking_id))).scalar_one()
        out.append({"id": d.id, "side": d.side, "reason": d.reason, "description": d.description,
                    "evidence": json.loads(d.evidence or "[]"), "status": d.status, "resolution": d.resolution,
                    "refund_kobo": d.refund_kobo, "decision_note": d.decision_note, "created_at": d.created_at,
                    "booking": await booking_out(db, b, "venue")})
    return out


@router.get("/venue-disputes/{dispute_id}/thread")
async def dispute_thread(dispute_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    from app.models.venue import VenueEnquiry
    from app.services.venue_views import enquiry_out
    d = (await db.execute(select(VenueDispute).where(VenueDispute.id == dispute_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    b = (await db.execute(select(VenueBooking).where(VenueBooking.id == d.booking_id))).scalar_one()
    e = (await db.execute(select(VenueEnquiry).where(VenueEnquiry.id == b.enquiry_id))).scalar_one()
    return await enquiry_out(db, e, "venue", with_messages=True)


@router.post("/venue-disputes/{dispute_id}/decide")
async def decide(dispute_id: str, payload: DisputeDecision, db: AsyncSession = Depends(get_db),
                 admin: User = Depends(get_current_admin)):
    d = (await db.execute(select(VenueDispute).where(VenueDispute.id == dispute_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    d = await decide_dispute(db, d, admin, payload)
    return {"status": d.status, "resolution": d.resolution, "refund_kobo": d.refund_kobo}


@router.get("/refund-requests")
async def list_refund_requests(status: str | None = None, db: AsyncSession = Depends(get_db),
                               _: User = Depends(get_current_admin)):
    q = select(RefundRequest, Venue).join(Venue, Venue.id == RefundRequest.venue_id)
    if status:
        q = q.where(RefundRequest.status == status)
    rows = (await db.execute(q.order_by(RefundRequest.created_at.desc()).limit(300))).all()
    return [refund_request_out(r) | {"venue": {"id": v.id, "name": v.name}} for r, v in rows]


@router.get("/off-platform-reports")
async def list_reports(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(OffPlatformReport, Venue).join(Venue, Venue.id == OffPlatformReport.venue_id).order_by(
        OffPlatformReport.created_at.desc()).limit(200))).all()
    return [{"id": r.id, "status": r.status, "details": r.details, "enquiry_id": r.enquiry_id,
             "message_id": r.message_id, "created_at": r.created_at, "venue": {"id": v.id, "name": v.name}}
            for r, v in rows]


class ReportDecision(BaseModel):
    upheld: bool
    note: str | None = Field(default=None, max_length=1000)


@router.post("/off-platform-reports/{report_id}")
async def decide_report(report_id: str, payload: ReportDecision, db: AsyncSession = Depends(get_db),
                        admin: User = Depends(get_current_admin)):
    r = (await db.execute(select(OffPlatformReport).where(OffPlatformReport.id == report_id))).scalar_one_or_none()
    if not r or r.status != "open":
        raise HTTPException(404, "No open report")
    r.status = "upheld" if payload.upheld else "dismissed"
    r.decided_by_id = admin.id
    if payload.upheld:
        v = (await db.execute(select(Venue).where(Venue.id == r.venue_id))).scalar_one()
        await add_strike(db, v, "off_platform", note=payload.note, by=admin.id)
    return {"status": r.status}


@router.get("/chargebacks")
async def list_chargebacks(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(Chargeback).order_by(Chargeback.created_at.desc()).limit(200))).scalars().all()
    return [{"id": c.id, "venue_id": c.venue_id, "reference": c.reference, "amount_kobo": c.amount_kobo,
             "status": c.status, "created_at": c.created_at, "resolved_at": c.resolved_at} for c in rows]


@router.post("/chargebacks/{cb_id}")
async def decide_chargeback(cb_id: str, payload: ChargebackDecision, db: AsyncSession = Depends(get_db),
                            _: User = Depends(get_current_admin)):
    from app.services.chargebacks import resolve_chargeback
    c = (await db.execute(select(Chargeback).where(Chargeback.id == cb_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await resolve_chargeback(db, c, payload.status)
    return {"status": c.status}


# ── Areas, prices, featured, access log, reviews ───────────────────────────────

@router.get("/areas")
async def all_areas(state: str | None = None, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    q = select(Area)
    if state:
        q = q.where(Area.state == (normalize_state(state) or state))
    rows = (await db.execute(q.order_by(Area.state, Area.sort_order, Area.name))).scalars().all()
    others = (await db.execute(select(Venue.id, Venue.name, Venue.state, Venue.area_other).where(
        Venue.area_id.is_(None), Venue.area_other.is_not(None)))).all()
    return {"areas": [{"id": a.id, "state": a.state, "name": a.name, "kind": a.kind, "is_active": a.is_active,
                       "latitude": a.latitude, "longitude": a.longitude} for a in rows],
            "unmapped": [{"venue_id": i, "venue": n, "state": s, "typed": t} for i, n, s, t in others]}


@router.post("/areas", status_code=201)
async def add_area(payload: AreaIn, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    st = normalize_state(payload.state)
    if not st:
        raise HTTPException(400, "Unknown state")
    slug = slugify(payload.name)
    if (await db.execute(select(Area.id).where(Area.state == st, Area.slug == slug))).first():
        raise HTTPException(409, "That area already exists")
    a = Area(state=st, name=payload.name.strip(), slug=slug, kind=payload.kind, latitude=payload.latitude,
             longitude=payload.longitude, sort_order=999)
    db.add(a)
    await db.flush()
    return {"id": a.id}


@router.patch("/areas/{area_id}")
async def edit_area(area_id: str, payload: AreaUpdate, db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_admin)):
    a = (await db.execute(select(Area).where(Area.id == area_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Not found")
    for k, val in payload.model_dump(exclude_unset=True).items():
        setattr(a, k, val)
    return {"ok": True}


class MarketplaceSettings(BaseModel):
    venue_commission_percent: float | None = Field(default=None, ge=0, le=50)
    featured_state_week_kobo: int | None = Field(default=None, ge=0)
    featured_area_week_kobo: int | None = Field(default=None, ge=0)
    featured_max_per_state: int | None = Field(default=None, ge=1, le=50)
    featured_max_per_area: int | None = Field(default=None, ge=1, le=50)
    max_recovery_percent: int | None = Field(default=None, ge=0, le=100)
    refund_funding_hours: int | None = Field(default=None, ge=1, le=720)
    refund_suspend_days: int | None = Field(default=None, ge=1, le=365)
    refund_referral_days: int | None = Field(default=None, ge=1, le=730)
    venue_debt_pause_days: int | None = Field(default=None, ge=1, le=365)
    strike_suspend_count: int | None = Field(default=None, ge=1, le=20)
    dispute_window_hours: int | None = Field(default=None, ge=1, le=720)
    free_photo_limit: int | None = Field(default=None, ge=1, le=100)
    pro_photo_limit: int | None = Field(default=None, ge=1, le=200)
    free_video_limit: int | None = Field(default=None, ge=0, le=50)
    pro_video_limit: int | None = Field(default=None, ge=0, le=100)
    free_team_seats: int | None = Field(default=None, ge=1, le=100)
    pro_team_seats: int | None = Field(default=None, ge=1, le=500)
    plus_early_alert_hours: int | None = Field(default=None, ge=0, le=168)
    subscription_grace_days: int | None = Field(default=None, ge=0, le=30)


@router.get("/marketplace-settings")
async def get_marketplace_settings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    ps = await get_platform_settings(db)
    plans = (await db.execute(select(SubscriptionPlan))).scalars().all()
    return {**{k: getattr(ps, k) for k in MarketplaceSettings.model_fields},
            "plans": [{"code": p.code, "name": p.name, "amount_kobo": p.amount_kobo, "interval": p.interval,
                       "is_active": p.is_active} for p in plans]}


@router.put("/marketplace-settings")
async def put_marketplace_settings(payload: MarketplaceSettings, db: AsyncSession = Depends(get_db),
                                   _: User = Depends(get_current_admin)):
    ps = await get_platform_settings(db)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(ps, k, v)
    return await get_marketplace_settings(db, _)


class PlanPrice(BaseModel):
    amount_kobo: int = Field(gt=0)
    is_active: bool = True


@router.put("/plans/{code}")
async def set_plan_price(code: str, payload: PlanPrice, db: AsyncSession = Depends(get_db),
                         _: User = Depends(get_current_admin)):
    """A new price applies to new subscribers (a new Paystack plan is created on next use);
    existing subscribers keep the price they signed up at."""
    p = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == code))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    if payload.amount_kobo != p.amount_kobo:
        p.amount_kobo = payload.amount_kobo
        p.paystack_plan_code = None
    p.is_active = payload.is_active
    return {"ok": True}


@router.get("/featured-slots")
async def featured_slots(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    rows = (await db.execute(select(FeaturedSlot, Venue).join(Venue, Venue.id == FeaturedSlot.venue_id).where(
        FeaturedSlot.status.in_(["active", "pending"])).order_by(FeaturedSlot.week_start))).all()
    out = []
    for s, v in rows:
        area = (await db.execute(select(Area.name).where(Area.id == s.area_id))).scalar_one_or_none() if s.area_id else None
        out.append({"id": s.id, "scope": s.scope, "state": s.state, "area": area, "week_start": s.week_start,
                    "status": s.status, "amount_kobo": s.amount_kobo, "venue": {"id": v.id, "name": v.name}})
    return out


@router.get("/kyc-access-log")
async def access_log(venue_id: str | None = None, db: AsyncSession = Depends(get_db),
                     _: User = Depends(get_current_admin)):
    q = select(KycAccessLog, User).join(User, User.id == KycAccessLog.user_id)
    if venue_id:
        q = q.where(KycAccessLog.venue_id == venue_id)
    rows = (await db.execute(q.order_by(KycAccessLog.at.desc()).limit(500))).all()
    return [{"at": e.at, "action": e.action, "venue_id": e.venue_id, "document_id": e.document_id, "ip": e.ip,
             "user": user_brief(u)} for e, u in rows]


class HideIn(BaseModel):
    is_hidden: bool


@router.patch("/venue-reviews/{review_id}")
async def moderate_review(review_id: str, payload: HideIn, db: AsyncSession = Depends(get_db),
                          _: User = Depends(get_current_moderator)):
    from app.services.venue_booking import _recompute_ratings
    r = (await db.execute(select(VenueReview).where(VenueReview.id == review_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Not found")
    r.is_hidden = payload.is_hidden
    await db.flush()
    await _recompute_ratings(db, r.venue_id)
    return {"ok": True}


@router.get("/marketplace-overview")
async def overview(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    async def count(model, *conds):
        return (await db.execute(select(func.count()).select_from(model).where(*conds))).scalar_one()
    return {
        "venues_to_review": await count(Venue, Venue.verification_status == "documents_submitted"),
        "visits_open": await count(AgentVisit, AgentVisit.status.in_(["assigned", "scheduled"])),
        "disputes_open": await count(VenueDispute, VenueDispute.status == "open"),
        "refunds_late": await count(RefundRequest, RefundRequest.status.in_(["overdue", "suspended"])),
        "reports_open": await count(OffPlatformReport, OffPlatformReport.status == "open"),
        "chargebacks_open": await count(Chargeback, Chargeback.status == "open"),
        "unmapped_areas": await count(Venue, Venue.area_id.is_(None), Venue.area_other.is_not(None)),
        "live_venues": await count(Venue, Venue.status == "live"),
    }
