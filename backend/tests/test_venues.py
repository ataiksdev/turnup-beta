"""Venue marketplace (docs/venues-spec.md): onboarding and verification, agents, search and
featured placement, enquiries/quotes/bookings with split payments, venue-funded refunds and
the unpaid-refund penalties, disputes, chargebacks, and KYC access."""
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select, update

from app.middleware.rate_limit import limiter
from app.models.auth_tokens import UserSession
from app.models.user import User
from app.models.venue import (
    Area, BlockedIdentity, Chargeback, FeaturedSlot, RefundRequest, Venue, VenueBooking,
    VenueLedgerEntry, VenuePayment, VenueStrike,
)
from app.services.auth import create_access_token
from app.services.places import ensure_areas
from app.services.plus import ensure_plans


def utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _no_rate_limits():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


@pytest_asyncio.fixture
async def seeded(db):
    await ensure_areas(db)
    await ensure_plans(db)
    await db.commit()


async def make_user(db, role="attendee", **extra):
    uid, jti, u = str(uuid.uuid4()), str(uuid.uuid4()), uuid.uuid4().hex[:8]
    db.add(User(id=uid, username=f"{role}_{u}", email=f"{role}_{u}@example.com",
                full_name=extra.pop("full_name", f"Ada {u.upper()}"), role=role, **extra))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=utcnow() + timedelta(hours=2)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}, uid


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 80, 20)).save(out, format="PNG")
    return out.getvalue()


async def area_id(db, state="FCT", name="Wuse"):
    return (await db.execute(select(Area.id).where(Area.state == state, Area.name == name))).scalar_one()


async def live_venue(client, db, *, visit=True, state="FCT", area="Wuse", lat=9.0765, lng=7.4683):
    """Owner creates a complete listing, submits it; admin approves documents; optionally an
    agent passes the visit (deposits on)."""
    owner_h, owner_id = await make_user(db)
    admin_h, _ = await make_user(db, "admin")
    r = await client.post("/api/venue-portal/venues", headers=owner_h, json={
        "name": f"Hall {uuid.uuid4().hex[:5]}", "type": "hall", "state": state,
        "area_id": await area_id(db, state, area), "address": "12 Example Crescent",
        "latitude": lat, "longitude": lng, "description": "A big hall"})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    base = f"/api/venue-portal/venues/{vid}"
    r = await client.post(f"{base}/submit", headers=owner_h)
    assert r.status_code == 400 and "Still needed" in r.json()["detail"]
    space = (await client.post(f"{base}/spaces", headers=owner_h, json={
        "name": "Main hall", "capacity_seated": 300, "capacity_standing": 500,
        "price_from_kobo": 50_000_000})).json()
    assert (await client.post(f"{base}/media", headers=owner_h, json={
        "kind": "photo", "url": "https://img.example.com/a.jpg"})).status_code == 201
    r = await client.patch(base, headers=owner_h, json={"legal_name": "Example Halls Ltd", "cac_number": f"RC{uuid.uuid4().int % 10**7}",
                                                         "registered_address": "1 Registry Road", "phone": "08031234567"})
    assert r.status_code == 200, r.text
    for kind in ("cac", "owner_id", "site_photo"):
        r = await client.post(f"{base}/documents", headers=owner_h, data={"kind": kind},
                              files={"file": ("doc.png", png(), "image/png")})
        assert r.status_code == 201, r.text
    r = await client.put(f"{base}/bank", headers=owner_h, json={"bank_code": "058", "account_number": "0123456789"})
    assert r.status_code == 200, r.text
    assert r.json()["bank"]["ready"]
    r = await client.post(f"{base}/submit", headers=owner_h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_review"
    r = await client.post(f"/api/admin/venues/{vid}/verification", headers=admin_h, json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "live"
    if visit:
        await db.execute(update(Venue).where(Venue.id == vid).values(
            verification_status="visit_passed", deposits_enabled=True))
        await db.commit()
    return {"id": vid, "owner_h": owner_h, "owner_id": owner_id, "admin_h": admin_h, "space": space,
            "slug": r.json() and (await client.get(f"/api/venue-portal/venues/{vid}", headers=owner_h)).json()["slug"]}


async def book(client, db, venue, *, days_ahead=45, total=100_000_000, organizer=None):
    """Organizer enquires, venue quotes, organizer accepts and pays the deposit (mock Paystack)."""
    org_h, org_id = organizer or await make_user(db, "organizer")
    start = utcnow() + timedelta(days=days_ahead)
    r = await client.post(f"/api/venues/{venue['slug']}/enquiries", headers=org_h, json={
        "space_id": venue["space"]["id"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=6)).isoformat(), "guest_count": 200, "message": "Is the hall free?"})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await client.post(f"/api/venue-portal/venues/{venue['id']}/enquiries/{eid}/quotes", headers=venue["owner_h"], json={
        "space_id": venue["space"]["id"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=6)).isoformat(), "total_kobo": total})
    assert r.status_code == 201, r.text
    quote = [m for m in r.json()["messages"] if m["quote"]][-1]["quote"]
    assert quote["deposit_kobo"] == total * 30 // 100  # default 30% deposit
    r = await client.post(f"/api/quotes/{quote['id']}/accept", headers=org_h, json={})
    assert r.status_code == 200, r.text
    acc = r.json()
    r = await client.post(f"/api/venue-payments/verify?reference={acc['reference']}", headers=org_h)
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    return {"booking_id": acc["booking_id"], "org_h": org_h, "org_id": org_id, "enquiry_id": eid,
            "quote": quote, "start": start}


# ── Onboarding, verification, agents ───────────────────────────────────────────

async def test_onboarding_verification_and_search(client, db, seeded):
    v = await live_venue(client, db, visit=False)
    page = (await client.get(f"/api/venues/{v['slug']}")).json()
    assert page["accepting_enquiries"] and not page["deposits_enabled"]
    assert page["price"] == {"display": "from", "from_kobo": 50_000_000}
    # Contact details stay hidden publicly.
    assert "phone" not in page
    found = (await client.get("/api/venues", params={"state": "abuja", "area_ids": await area_id(db)})).json()
    assert v["id"] in [x["id"] for x in found["items"]]
    other = (await client.get("/api/venues", params={"state": "FCT", "area_ids": await area_id(db, "FCT", "Maitama")})).json()
    assert v["id"] not in [x["id"] for x in other["items"]]
    near = (await client.get("/api/venues", params={"state": "FCT", "lat": 9.077, "lng": 7.469, "radius_km": 5})).json()
    assert v["id"] in [x["id"] for x in near["items"]]
    assert near["items"][0]["distance_m"] is not None
    far = (await client.get("/api/venues", params={"state": "FCT", "lat": 8.94, "lng": 7.08, "radius_km": 5})).json()
    assert v["id"] not in [x["id"] for x in far["items"]]
    big = (await client.get("/api/venues", params={"state": "FCT", "min_capacity": 1000})).json()
    assert v["id"] not in [x["id"] for x in big["items"]]

    # Deposits are blocked until the agent visit passes.
    org_h, _ = await make_user(db, "organizer")
    start = utcnow() + timedelta(days=40)
    e = (await client.post(f"/api/venues/{v['slug']}/enquiries", headers=org_h, json={
        "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=4)).isoformat(),
        "guest_count": 50, "message": "Hi"})).json()
    q = await client.post(f"/api/venue-portal/venues/{v['id']}/enquiries/{e['id']}/quotes", headers=v["owner_h"], json={
        "space_id": v["space"]["id"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=4)).isoformat(), "total_kobo": 10_000_000})
    quote_id = [m for m in q.json()["messages"] if m["quote"]][-1]["quote"]["id"]
    r = await client.post(f"/api/quotes/{quote_id}/accept", headers=org_h, json={})
    assert r.status_code == 409 and "visited" in r.json()["detail"]


async def test_agent_visit_turns_on_deposits(client, db, seeded):
    agent_h, agent_id = await make_user(db)
    admin_h, _ = await make_user(db, "admin")
    assert (await client.put("/api/admin/agents", headers=admin_h,
                             json={"user_id": agent_id, "states": ["Lagos"]})).status_code == 200
    v = await live_venue(client, db, visit=False, state="Lagos", area="Lekki", lat=6.4698, lng=3.5852)
    visits = (await client.get("/api/agent/visits", headers=agent_h)).json()
    visit = next(x for x in visits if x["venue"]["id"] == v["id"])  # auto-assigned by state
    detail = (await client.get(f"/api/agent/visits/{visit['id']}", headers=agent_h)).json()
    assert len(detail["documents"]) == 3
    # The signed link works for the agent; a tampered one doesn't.
    url = detail["documents"][0]["url"]
    assert (await client.get(url)).status_code == 200
    assert (await client.get(url.replace("sig=", "sig=00"))).status_code == 403
    # The venue's own team can't reach the agent portal.
    assert (await client.get("/api/agent/visits", headers=v["owner_h"])).status_code == 403

    r = await client.post(f"/api/agent/visits/{visit['id']}/check-in", headers=agent_h,
                          json={"latitude": 6.60, "longitude": 3.35})
    assert r.status_code == 400 and "from the venue" in r.json()["detail"]
    r = await client.post(f"/api/agent/visits/{visit['id']}/check-in", headers=agent_h,
                          json={"latitude": 6.4699, "longitude": 3.5853})
    assert r.status_code == 200 and r.json()["distance_from_venue_m"] < 50
    assert (await client.post(f"/api/agent/visits/{visit['id']}/report", headers=agent_h, json={
        "checklist": {"capacity": True}, "notes": "All good", "outcome": "passed"})).status_code == 400  # no photo
    await client.post(f"/api/agent/visits/{visit['id']}/photos", headers=agent_h,
                      files={"file": ("p.png", png(), "image/png")})
    r = await client.post(f"/api/agent/visits/{visit['id']}/report", headers=agent_h, json={
        "checklist": {"capacity": True, "exits": True}, "notes": "All good", "outcome": "passed"})
    assert r.status_code == 200
    page = (await client.get(f"/api/venues/{v['slug']}")).json()
    assert page["deposits_enabled"] and page["is_verified"]
    log = (await client.get("/api/admin/kyc-access-log", headers=admin_h, params={"venue_id": v["id"]})).json()
    assert any(e["action"] == "download" for e in log)


async def test_media_limit_and_team_roles(client, db, seeded):
    v = await live_venue(client, db)
    base = f"/api/venue-portal/venues/{v['id']}"
    for i in range(5):
        assert (await client.post(f"{base}/media", headers=v["owner_h"], json={
            "kind": "photo", "url": f"https://img.example.com/{i}.jpg"})).status_code == 201
    r = await client.post(f"{base}/media", headers=v["owner_h"], json={"kind": "photo", "url": "https://img.example.com/x.jpg"})
    assert r.status_code == 409 and "Venue Pro" in r.json()["detail"]  # free plan: 6 photos

    viewer_h, viewer_id = await make_user(db)
    viewer_email = (await db.execute(select(User.email).where(User.id == viewer_id))).scalar_one()
    inv = (await client.post(f"{base}/invites", headers=v["owner_h"], json={"email": viewer_email, "role": "viewer"})).json()
    token = inv["link"].split("token=")[1]
    assert (await client.post(f"/api/venue-portal/invites/accept?token={token}", headers=viewer_h)).status_code == 200
    assert (await client.get(base, headers=viewer_h)).status_code == 200
    r = await client.patch(base, headers=viewer_h, json={"description": "changed"})
    assert r.status_code == 403
    assert (await client.put(f"{base}/bank", headers=viewer_h,
                             json={"bank_code": "058", "account_number": "0123456789"})).status_code == 403


# ── Booking, payments, refunds ─────────────────────────────────────────────────

async def test_booking_split_commission_and_balance(client, db, seeded):
    v = await live_venue(client, db)
    b = await book(client, db, v)
    booking = (await client.get(f"/api/venue-bookings/{b['booking_id']}", headers=b["org_h"])).json()
    assert booking["status"] == "confirmed"
    assert booking["paid_kobo"] == 30_000_000
    assert booking["venue"]["phone"] == "08031234567"  # revealed once booked
    pay = (await db.execute(select(VenuePayment).where(VenuePayment.booking_id == b["booking_id"]))).scalar_one()
    assert pay.commission_kobo == 2_400_000 and pay.venue_share_kobo == 27_600_000  # 8%

    # Same space, overlapping time: the venue can't quote it again.
    org2 = await make_user(db, "organizer")
    start = b["start"] + timedelta(hours=2)
    e = (await client.post(f"/api/venues/{v['slug']}/enquiries", headers=org2[0], json={
        "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat(),
        "guest_count": 20, "message": "Free?"})).json()
    r = await client.post(f"/api/venue-portal/venues/{v['id']}/enquiries/{e['id']}/quotes", headers=v["owner_h"], json={
        "space_id": v["space"]["id"], "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=2)).isoformat(), "total_kobo": 5_000_000})
    assert r.status_code == 409

    # Balance in two parts.
    r = await client.post(f"/api/venue-bookings/{b['booking_id']}/pay", headers=b["org_h"], json={"amount_kobo": 20_000_000})
    assert r.status_code == 200
    await client.post(f"/api/venue-payments/verify?reference={r.json()['reference']}", headers=b["org_h"])
    r = await client.post(f"/api/venue-bookings/{b['booking_id']}/pay", headers=b["org_h"], json={})
    assert r.json()["amount_kobo"] == 50_000_000
    await client.post(f"/api/venue-payments/verify?reference={r.json()['reference']}", headers=b["org_h"])
    booking = (await client.get(f"/api/venue-bookings/{b['booking_id']}", headers=b["org_h"])).json()
    assert booking["status"] == "fully_paid" and booking["balance_kobo"] == 0


async def test_organizer_cancel_refund_is_funded_by_venue(client, db, seeded):
    v = await live_venue(client, db)
    b = await book(client, db, v, days_ahead=45)  # moderate preset: 30+ days = full refund
    url = f"/api/venue-bookings/{b['booking_id']}/cancel"
    preview = (await client.post(url, headers=b["org_h"], json={"preview": True})).json()
    assert preview == {"refund_percent": 100, "refund_kobo": 30_000_000, "paid_kobo": 30_000_000, "funded_by": "venue"}
    r = await client.post(url, headers=b["org_h"], json={"reason": "Plans changed"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled_by_organizer"
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b["booking_id"]))).scalar_one()
    assert rr.status == "awaiting_venue" and rr.amount_kobo == 30_000_000

    # Nothing is refunded until the venue pays it in.
    with patch("app.services.paystack.refund_transaction", new=AsyncMock(return_value={})) as refund:
        r = await client.post(f"/api/venue-portal/venues/{v['id']}/refunds/{rr.id}/fund", headers=v["owner_h"], json={})
        assert r.status_code == 200 and r.json()["amount_kobo"] == 30_000_000
        refund.assert_not_called()
        await client.post(f"/api/venue-payments/verify?reference={r.json()['reference']}", headers=v["owner_h"])
        refund.assert_awaited_once()
        deposit_ref = (await db.execute(select(VenuePayment.reference).where(
            VenuePayment.booking_id == b["booking_id"], VenuePayment.kind == "deposit"))).scalar_one()
        assert refund.await_args.args == (deposit_ref, 30_000_000)
    await db.refresh(rr)
    assert rr.status == "refunded"


async def test_venue_cancel_full_refund_and_strikes_suspend(client, db, seeded):
    v = await live_venue(client, db)
    for i in range(3):
        b = await book(client, db, v, days_ahead=10 + i)
        r = await client.post(f"/api/venue-portal/venues/{v['id']}/bookings/{b['booking_id']}/cancel",
                              headers=v["owner_h"], json={"preview": True})
        assert r.json()["refund_percent"] == 100 and r.json()["strike"]
        r = await client.post(f"/api/venue-portal/venues/{v['id']}/bookings/{b['booking_id']}/cancel",
                              headers=v["owner_h"], json={"reason": "Double booked"})
        assert r.status_code == 200, r.text
        rr = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b["booking_id"]))).scalar_one()
        assert rr.amount_kobo == 30_000_000  # all of it, commission included
    venue = (await db.execute(select(Venue).where(Venue.id == v["id"]))).scalar_one()
    await db.refresh(venue)
    assert venue.status == "suspended" and venue.pause_reason == "strikes"
    page = (await client.get(f"/api/venues/{v['slug']}")).json()
    assert page["cancellations_last_year"] == 3 and not page["accepting_enquiries"]


async def test_unpaid_refund_penalty_timeline(client, db, seeded):
    from app.services.venue_money import run_refund_penalties
    v = await live_venue(client, db)
    b = await book(client, db, v, days_ahead=50)
    await client.post(f"/api/venue-bookings/{b['booking_id']}/cancel", headers=b["org_h"], json={"reason": "x"})
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b["booking_id"]))).scalar_one()

    # Day 3: overdue -> paused, debt on the ledger.
    await db.execute(update(RefundRequest).where(RefundRequest.id == rr.id).values(due_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
    await run_refund_penalties(db)
    await db.refresh(rr)
    venue = (await db.execute(select(Venue).where(Venue.id == v["id"]))).scalar_one()
    await db.refresh(venue)
    assert rr.status == "overdue" and venue.status == "paused" and venue.pause_reason == "unpaid_refund"
    owed = (await db.execute(select(VenueLedgerEntry).where(VenueLedgerEntry.refund_request_id == rr.id))).scalar_one()
    assert owed.kind == "refund_owed" and owed.amount_kobo == 30_000_000
    hidden = (await client.get("/api/venues", params={"state": "FCT"})).json()
    assert v["id"] not in [x["id"] for x in hidden["items"]]

    # Day 30: suspended + strike. Day 60: referred, identities blocked, claim pack available.
    await db.execute(update(RefundRequest).where(RefundRequest.id == rr.id).values(created_at=utcnow() - timedelta(days=31)))
    await db.commit()
    await run_refund_penalties(db)
    await db.refresh(rr)
    await db.refresh(venue)
    assert rr.status == "suspended" and venue.status == "suspended"
    assert (await db.execute(select(VenueStrike).where(VenueStrike.venue_id == v["id"]))).scalars().first()
    r = await client.get(f"/api/refund-requests/{rr.id}/claim-pack", headers=b["org_h"])
    assert r.status_code == 409
    await db.execute(update(RefundRequest).where(RefundRequest.id == rr.id).values(created_at=utcnow() - timedelta(days=61)))
    await db.commit()
    await run_refund_penalties(db)
    await db.refresh(rr)
    assert rr.status == "referred"
    blocks = (await db.execute(select(BlockedIdentity).where(BlockedIdentity.refund_request_id == rr.id))).scalars().all()
    assert {x.kind for x in blocks} == {"cac", "bank_account", "user"}
    r = await client.get(f"/api/refund-requests/{rr.id}/claim-pack", headers=b["org_h"])
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    stranger_h, _ = await make_user(db)
    assert (await client.get(f"/api/refund-requests/{rr.id}/claim-pack", headers=stranger_h)).status_code == 404
    # The owner can't list another venue while it's unpaid.
    r = await client.post("/api/venue-portal/venues", headers=v["owner_h"], json={
        "name": "New Place", "type": "lounge", "state": "FCT", "area_other": "Somewhere",
        "address": "1 New Street", "latitude": 9.0, "longitude": 7.4})
    assert r.status_code == 403

    # Both sides confirm it was settled directly: blocks lift, the venue is restored.
    await client.post(f"/api/venue-portal/venues/{v['id']}/refunds/{rr.id}/settled", headers=v["owner_h"])
    r = await client.post(f"/api/refund-requests/{rr.id}/settled", headers=b["org_h"])
    assert r.json()["status"] == "settled_directly"
    await db.refresh(venue)
    assert venue.status == "live"
    assert all(x.lifted_at for x in (await db.execute(select(BlockedIdentity).where(
        BlockedIdentity.refund_request_id == rr.id).execution_options(populate_existing=True))).scalars().all())


async def test_overdue_refund_recovered_from_next_booking(client, db, seeded):
    from app.services.venue_money import run_refund_penalties
    v = await live_venue(client, db)
    b1 = await book(client, db, v, days_ahead=60)
    await client.post(f"/api/venue-bookings/{b1['booking_id']}/cancel", headers=b1["org_h"], json={})
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b1["booking_id"]))).scalar_one()
    await db.execute(update(RefundRequest).where(RefundRequest.id == rr.id).values(due_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
    await run_refund_penalties(db)
    # Admin un-pauses so the venue can take another booking (e.g. it promised to pay).
    await db.execute(update(Venue).where(Venue.id == v["id"]).values(status="live", pause_reason=None))
    await db.commit()
    with patch("app.services.paystack.refund_transaction", new=AsyncMock(return_value={})) as refund:
        b2 = await book(client, db, v, days_ahead=90, total=200_000_000)  # deposit 60m
        pay = (await db.execute(select(VenuePayment).where(VenuePayment.booking_id == b2["booking_id"]))).scalar_one()
        # Cap lifted while a refund is overdue: the venue's whole share goes to the organizer.
        assert pay.commission_kobo == 4_800_000
        assert pay.recovery_kobo == 30_000_000 and pay.venue_share_kobo == 60_000_000 - 4_800_000 - 30_000_000
        refund.assert_awaited()
    await db.refresh(rr)
    assert rr.status == "refunded" and rr.refunded_kobo == 30_000_000


async def test_dispute_partial_refund(client, db, seeded):
    v = await live_venue(client, db)
    b = await book(client, db, v, days_ahead=5)
    r = await client.post(f"/api/venue-bookings/{b['booking_id']}/disputes", headers=b["org_h"], json={
        "reason": "not_as_listed", "description": "The hall was half the size shown."})
    assert r.status_code == 201
    disputes = (await client.get("/api/admin/venue-disputes", headers=v["admin_h"])).json()
    d = next(x for x in disputes if x["booking"]["id"] == b["booking_id"])
    r = await client.post(f"/api/admin/venue-disputes/{d['id']}/decide", headers=v["admin_h"], json={
        "resolution": "partial", "refund_kobo": 10_000_000, "note": "Smaller than listed"})
    assert r.status_code == 200 and r.json()["refund_kobo"] == 10_000_000
    rr = (await db.execute(select(RefundRequest).where(RefundRequest.booking_id == b["booking_id"]))).scalar_one()
    assert rr.reason == "dispute" and rr.amount_kobo == 10_000_000 and rr.status == "awaiting_venue"


async def test_lost_chargeback_goes_on_venue_ledger(client, db, seeded):
    from app.services.chargebacks import record_dispute_event
    from app.services.venue_money import ledger_balance
    v = await live_venue(client, db)
    b = await book(client, db, v)
    ref = (await db.execute(select(VenuePayment.reference).where(VenuePayment.booking_id == b["booking_id"]))).scalar_one()
    await record_dispute_event(db, "charge.dispute.create", {"id": 991, "transaction": {"reference": ref, "amount": 30_000_000}})
    await record_dispute_event(db, "charge.dispute.resolve", {"id": 991, "resolution": "merchant-accepted",
                                                              "transaction": {"reference": ref}})
    await db.commit()
    cb = (await db.execute(select(Chargeback).where(Chargeback.paystack_dispute_id == "991"))).scalar_one()
    assert cb.status == "lost" and cb.venue_id == v["id"]
    assert await ledger_balance(db, v["id"]) == 30_000_000


# ── Featured placement ─────────────────────────────────────────────────────────

async def test_featured_strip_and_pinning(client, db, seeded):
    a = await live_venue(client, db, area="Wuse")
    b = await live_venue(client, db, area="Maitama", lat=9.0882, lng=7.4934)
    wuse, maitama = await area_id(db, "FCT", "Wuse"), await area_id(db, "FCT", "Maitama")
    monday = utcnow() - timedelta(days=1)
    db.add(FeaturedSlot(venue_id=a["id"], scope="area", state="FCT", area_id=wuse, week_start=monday,
                        ends_at=monday + timedelta(days=7), amount_kobo=1_500_000, payment_reference="t1", status="active"))
    db.add(FeaturedSlot(venue_id=b["id"], scope="state", state="FCT", week_start=monday,
                        ends_at=monday + timedelta(days=7), amount_kobo=5_000_000, payment_reference="t2", status="active"))
    await db.commit()
    whole_state = (await client.get("/api/venues/featured", params={"state": "FCT"})).json()
    assert [x["id"] for x in whole_state if x["id"] in (a["id"], b["id"])] == [b["id"]]  # area slot not shown
    in_wuse = (await client.get("/api/venues/featured", params={"state": "FCT", "area_ids": wuse})).json()
    ids = [x["id"] for x in in_wuse]
    assert ids.index(a["id"]) < ids.index(b["id"])  # area slots first
    results = (await client.get("/api/venues", params={"state": "FCT", "area_ids": f"{wuse},{maitama}"})).json()["items"]
    order = [x["id"] for x in results]
    assert order.index(b["id"]) < order.index(a["id"])  # state-wide pinned above area
    assert {x["id"]: x["featured"] for x in results}[a["id"]] == "area"
    # Not pinned when it doesn't match the search.
    big = (await client.get("/api/venues", params={"state": "FCT", "min_capacity": 10_000})).json()["items"]
    assert b["id"] not in [x["id"] for x in big]


async def test_buy_featured_weeks(client, db, seeded):
    v = await live_venue(client, db)
    opts = (await client.get(f"/api/venue-portal/venues/{v['id']}/featured", headers=v["owner_h"])).json()
    assert opts["price_state_kobo"] == 5_000_000 and opts["price_area_kobo"] == 1_500_000
    week = opts["weeks"][0]["week_start"]
    r = await client.post(f"/api/venue-portal/venues/{v['id']}/featured", headers=v["owner_h"],
                          json={"scope": "area", "weeks": [week]})
    assert r.status_code == 200 and r.json()["amount_kobo"] == 1_500_000
    await client.post(f"/api/venue-payments/verify?reference={r.json()['reference']}", headers=v["owner_h"])
    slot = (await db.execute(select(FeaturedSlot).where(FeaturedSlot.venue_id == v["id"]))).scalar_one()
    assert slot.status == "active" and slot.scope == "area"
    r = await client.post(f"/api/venue-portal/venues/{v['id']}/featured", headers=v["owner_h"],
                          json={"scope": "area", "weeks": [week]})
    assert r.status_code == 409  # already have it
