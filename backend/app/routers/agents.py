"""Agent portal (web): assigned venues, documents, visit scheduling, GPS check-in, report
(docs/venues-spec.md 4.1). Also serves private KYC files through signed links."""
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.models.venue import AgentVisit, KycAccessLog, Venue, VenueDocument, VenueMedia, VenueSpace
from app.schemas.venue import CheckInIn, ScheduleIn, VisitReportIn
from app.services import kyc_store
from app.services.places import haversine_m
from app.services.venue_access import agent_states, get_agent, notify, notify_venue_team
from app.services.venue_money import utcnow
from app.services.venue_views import area_name, space_out

router = APIRouter(tags=["agents"])

CHECKIN_RADIUS_M = 300
CHECKLIST = [
    ("capacity", "Capacity matches the listing"),
    ("photos", "Photos match what's there"),
    ("exits", "Fire exits are clear and marked"),
    ("power", "Power and generator backup work"),
    ("toilets", "Toilets are adequate and clean"),
    ("parking", "Parking matches the listing"),
    ("access", "Access and security are as described"),
    ("owner_met", "Met the owner or manager in person"),
]


async def _agent(db: AsyncSession, user: User):
    agent = await get_agent(db, user)
    if not agent:
        raise HTTPException(403, "Agent access required.")
    return agent


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def docs_with_links(db: AsyncSession, venue_id: str, viewer: User, request: Request) -> list[dict]:
    rows = (await db.execute(select(VenueDocument).where(VenueDocument.venue_id == venue_id).order_by(
        VenueDocument.created_at))).scalars().all()
    return [{"id": d.id, "kind": d.kind, "status": d.status, "content_type": d.content_type,
             "original_filename": d.original_filename, "rejection_reason": d.rejection_reason,
             "created_at": d.created_at, "url": kyc_store.signed_url(d.storage_key, viewer.id)} for d in rows]


@router.get("/api/agent/me")
async def agent_me(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    agent = await _agent(db, user)
    return {"user_id": agent.user_id, "states": agent_states(agent), "phone": agent.phone,
            "checklist": [{"id": k, "label": v} for k, v in CHECKLIST]}


@router.get("/api/agent/visits")
async def my_visits(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _agent(db, user)
    rows = (await db.execute(select(AgentVisit, Venue).join(Venue, Venue.id == AgentVisit.venue_id).where(
        AgentVisit.agent_id == user.id).order_by(AgentVisit.created_at.desc()))).all()
    return [{"id": vi.id, "status": vi.status, "scheduled_for": vi.scheduled_for, "checked_in_at": vi.checked_in_at,
             "venue": {"id": v.id, "name": v.name, "address": v.address, "state": v.state,
                       "area": await area_name(db, v), "latitude": v.latitude, "longitude": v.longitude,
                       "phone": v.phone}} for vi, v in rows]


async def _visit(db: AsyncSession, visit_id: str, user: User) -> tuple[AgentVisit, Venue]:
    await _agent(db, user)
    row = (await db.execute(select(AgentVisit, Venue).join(Venue, Venue.id == AgentVisit.venue_id).where(
        AgentVisit.id == visit_id, AgentVisit.agent_id == user.id))).first()
    if not row:
        raise HTTPException(404, "Visit not found")
    return row[0], row[1]


@router.get("/api/agent/visits/{visit_id}")
async def visit_detail(visit_id: str, request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    visit, v = await _visit(db, visit_id, user)
    spaces = (await db.execute(select(VenueSpace).where(VenueSpace.venue_id == v.id))).scalars().all()
    media = (await db.execute(select(VenueMedia).where(VenueMedia.venue_id == v.id).order_by(VenueMedia.sort_order))).scalars().all()
    db.add(KycAccessLog(venue_id=v.id, user_id=user.id, action="view", ip=_ip(request)))
    photos = []
    for key in json.loads(visit.photo_keys or "[]"):
        photos.append(kyc_store.signed_url(key, user.id))
    return {
        "id": visit.id, "status": visit.status, "scheduled_for": visit.scheduled_for,
        "checked_in_at": visit.checked_in_at, "distance_from_venue_m": visit.distance_from_venue_m,
        "checklist": json.loads(visit.checklist or "{}"), "notes": visit.notes, "photos": photos,
        "venue": {"id": v.id, "name": v.name, "type": v.type, "address": v.address, "state": v.state,
                  "area": await area_name(db, v), "latitude": v.latitude, "longitude": v.longitude,
                  "phone": v.phone, "legal_name": v.legal_name, "cac_number": v.cac_number,
                  "description": v.description, "spaces": [space_out(s) for s in spaces],
                  "media": [{"kind": m.kind, "url": m.url} for m in media]},
        "documents": await docs_with_links(db, v.id, user, request),
    }


@router.post("/api/agent/visits/{visit_id}/schedule")
async def schedule_visit(visit_id: str, payload: ScheduleIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    visit, v = await _visit(db, visit_id, user)
    if visit.status not in ("assigned", "scheduled"):
        raise HTTPException(409, "This visit is closed.")
    visit.scheduled_for = payload.scheduled_for
    visit.status = "scheduled"
    await notify_venue_team(db, v.id, "venue_visit_scheduled",
                            f"Turnup's verification visit is booked for {payload.scheduled_for:%d %b %Y, %H:%M}",
                            reference_id=v.id, reference_type="venue")
    return {"ok": True}


@router.post("/api/agent/visits/{visit_id}/check-in")
async def check_in(visit_id: str, payload: CheckInIn, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    visit, v = await _visit(db, visit_id, user)
    if visit.status not in ("assigned", "scheduled"):
        raise HTTPException(409, "This visit is closed.")
    if v.latitude is None or v.longitude is None:
        raise HTTPException(409, "The venue has no map pin.")
    dist = int(haversine_m(payload.latitude, payload.longitude, v.latitude, v.longitude))
    if dist > CHECKIN_RADIUS_M and not (payload.note or "").strip():
        raise HTTPException(400, f"You're {dist} m from the venue's pin. Move closer, or explain why.")
    visit.checked_in_at = utcnow()
    visit.checkin_latitude, visit.checkin_longitude = payload.latitude, payload.longitude
    visit.distance_from_venue_m = dist
    visit.distance_note = payload.note
    return {"distance_from_venue_m": dist}


@router.post("/api/agent/visits/{visit_id}/photos", status_code=201)
@limiter.limit("60/hour")
async def visit_photo(request: Request, visit_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    visit, _ = await _visit(db, visit_id, user)
    raw = await file.read(kyc_store.MAX_DOC_BYTES + 1)
    data, _, ext = kyc_store.prepare(raw, allow_pdf=False)
    key = kyc_store.save(data, ext)
    keys = json.loads(visit.photo_keys or "[]") + [key]
    visit.photo_keys = json.dumps(keys)
    return {"count": len(keys)}


@router.post("/api/agent/visits/{visit_id}/report")
async def report(visit_id: str, payload: VisitReportIn, db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user)):
    visit, v = await _visit(db, visit_id, user)
    if visit.status not in ("assigned", "scheduled"):
        raise HTTPException(409, "This visit is already decided.")
    if not visit.checked_in_at:
        raise HTTPException(400, "Check in at the venue first.")
    if not visit.photo_keys or not json.loads(visit.photo_keys):
        raise HTTPException(400, "Add at least one photo from the visit.")
    visit.checklist = json.dumps(payload.checklist)
    visit.notes = payload.notes
    visit.status = payload.outcome
    visit.decided_at = utcnow()
    if payload.outcome == "passed":
        v.verification_status = "visit_passed"
        v.deposits_enabled = True
        await notify_venue_team(db, v.id, "venue_visit_passed",
                                f"{v.name} passed Turnup's visit: you can now take deposits",
                                reference_id=v.id, reference_type="venue", minimum="viewer")
    else:
        await notify_venue_team(db, v.id, "venue_visit_failed",
                                f"{v.name} didn't pass Turnup's visit", payload.notes[:300],
                                reference_id=v.id, reference_type="venue", minimum="viewer")
    for aid in (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all():
        notify(db, aid, "venue_visit_report", f"Visit report for {v.name}: {payload.outcome}",
               reference_id=v.id, reference_type="venue")
    return {"status": visit.status}


# ── Private files ──────────────────────────────────────────────────────────────

@router.get("/api/kyc/files/{key}")
async def kyc_file(key: str, request: Request, u: str = Query(...), exp: int = Query(...), sig: str = Query(...),
                   db: AsyncSession = Depends(get_db)):
    """Signed, short-lived link (the API checked access when it made the link). Logged."""
    if not kyc_store.check_signature(key, u, exp, sig):
        raise HTTPException(403, "This link has expired.")
    path = kyc_store.read_path(key)
    doc = (await db.execute(select(VenueDocument).where(VenueDocument.storage_key == key))).scalar_one_or_none()
    db.add(KycAccessLog(document_id=doc.id if doc else None, venue_id=doc.venue_id if doc else None,
                        user_id=u, action="download", ip=_ip(request)))
    ctype = doc.content_type if doc else ("image/webp" if key.endswith(".webp") else "application/octet-stream")
    return FileResponse(path, media_type=ctype, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox", "Content-Disposition": "inline"})
