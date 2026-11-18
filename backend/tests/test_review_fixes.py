"""Regression tests for the remaining bugs from the app review: RSVP rules, moderation of
edits, protecting sold events, community roles, email casing, input validation, privacy of
draft guest lists, email escaping and view de-duplication."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.middleware.rate_limit import limiter
from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.user import User
from app.services.auth import create_access_token, hash_password
from app.services.email import _ticket_html


@pytest.fixture(autouse=True)
def _no_rate_limits():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def _user(db, role="attendee", **fields) -> tuple[dict, str]:
    uid, jti, u = str(uuid.uuid4()), str(uuid.uuid4()), _u()
    db.add(User(id=uid, username=f"{role}_{u}", email=f"{role}_{u}@example.com",
                full_name=role.title(), role=role, **fields))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}, uid


async def _event(db, host_id, **fields) -> str:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    data = dict(id=eid, slug=f"e-{eid}", title=f"Event {_u()}", description="d" * 30,
                venue_name="Venue", address="1 Test Street", city="Lagos", country="NG",
                start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=3),
                host_id=host_id, status="published", review_status="approved")
    data.update(fields)
    db.add(Event(**data))
    await db.commit()
    return eid


async def _get(db, model, id_):
    db.expire_all()
    return (await db.execute(select(model).where(model.id == id_))).scalar_one()


# ── RSVP ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_switching_interested_to_going_respects_capacity(client, db):
    _, host = await _user(db, "organizer")
    eid = await _event(db, host, capacity=1)
    a, _ = await _user(db)
    b, _ = await _user(db)
    assert (await client.post(f"/api/events/{eid}/attend", json={"status": "going"}, headers=a)).status_code == 200
    assert (await client.post(f"/api/events/{eid}/attend", json={"status": "interested"}, headers=b)).status_code == 200
    r = await client.post(f"/api/events/{eid}/attend", json={"status": "going"}, headers=b)
    assert r.status_code == 409
    assert (await _get(db, Event, eid)).attendees_count == 1


@pytest.mark.asyncio
async def test_ticketed_event_needs_a_ticket_to_go(client, db):
    _, host = await _user(db, "organizer")
    eid = await _event(db, host, is_free=False)
    tid = str(uuid.uuid4())
    db.add(TicketTier(id=tid, event_id=eid, name="GA", price=5000.0, quantity=10))
    await db.commit()
    headers, uid = await _user(db)
    r = await client.post(f"/api/events/{eid}/attend", json={"status": "going"}, headers=headers)
    assert r.status_code == 409 and "ticket" in r.json()["detail"]
    # interested is always fine
    assert (await client.post(f"/api/events/{eid}/attend", json={"status": "interested"}, headers=headers)).status_code == 200
    db.add(TicketOrder(id=str(uuid.uuid4()), user_id=uid, event_id=eid, tier_id=tid, quantity=1,
                       unit_price=5000.0, total_price=5000.0, status="confirmed"))
    await db.commit()
    assert (await client.post(f"/api/events/{eid}/attend", json={"status": "going"}, headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_unrsvp_from_going_works_and_counters_balance(client, db):
    _, host = await _user(db, "organizer")
    eid = await _event(db, host)
    headers, uid = await _user(db)
    await client.post(f"/api/events/{eid}/attend", json={"status": "interested"}, headers=headers)
    assert (await _get(db, User, uid)).events_attended == 0  # interested isn't attending
    await client.post(f"/api/events/{eid}/attend", json={"status": "going"}, headers=headers)
    assert (await _get(db, User, uid)).events_attended == 1
    r = await client.delete(f"/api/events/{eid}/attend", headers=headers)
    assert r.status_code == 200, r.text  # used to crash: max() on a SQL expression
    ev = await _get(db, Event, eid)
    counts = (ev.attendees_count, ev.interested_count)
    assert counts == (0, 0)
    assert (await _get(db, User, uid)).events_attended == 0


# ── Moderation & protecting sold events ───────────────────────────────────────

@pytest.mark.asyncio
async def test_editing_approved_event_content_returns_it_to_review(client, db):
    headers, host = await _user(db, "organizer")
    eid = await _event(db, host)
    r = await client.patch(f"/api/events/{eid}", json={"title": "Something else entirely"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["review_status"] == "pending" and r.json()["status"] == "published"
    # non-content edits (capacity) don't
    eid2 = await _event(db, host)
    r2 = await client.patch(f"/api/events/{eid2}", json={"capacity": 50}, headers=headers)
    assert r2.json()["review_status"] == "approved"


@pytest.mark.asyncio
async def test_reapproving_a_live_event_does_not_double_count(client, db):
    headers, host = await _user(db, "organizer", events_hosted=1)
    admin, _ = await _user(db, "admin")
    eid = await _event(db, host)
    await client.patch(f"/api/events/{eid}", json={"description": "A brand new description here"}, headers=headers)
    assert (await client.post(f"/api/admin/events/{eid}/approve", headers=admin)).status_code == 200
    assert (await _get(db, User, host)).events_hosted == 1


@pytest.mark.asyncio
async def test_event_with_ticket_orders_cannot_be_deleted(client, db):
    headers, host = await _user(db, "organizer")
    eid = await _event(db, host)
    _, buyer = await _user(db)
    tid = str(uuid.uuid4())
    db.add(TicketTier(id=tid, event_id=eid, name="GA", price=100.0, quantity=5))
    db.add(TicketOrder(id=str(uuid.uuid4()), user_id=buyer, event_id=eid, tier_id=tid, quantity=1,
                       unit_price=100.0, total_price=100.0, status="confirmed"))
    await db.commit()
    assert (await client.delete(f"/api/events/{eid}", headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_tier_quantity_cannot_drop_below_sold(client, db):
    headers, host = await _user(db, "organizer")
    eid = await _event(db, host)
    tid = str(uuid.uuid4())
    db.add(TicketTier(id=tid, event_id=eid, name="GA", price=100.0, quantity=10, quantity_sold=4))
    await db.commit()
    r = await client.patch(f"/api/events/{eid}/tickets/{tid}", json={"quantity": 3}, headers=headers)
    assert r.status_code == 409


# ── Communities ───────────────────────────────────────────────────────────────

async def _community(client, owner_headers) -> str:
    r = await client.post("/api/communities", json={"name": f"Club {_u()}", "description": "x" * 20},
                          headers=owner_headers)
    return r.json()["slug"]


@pytest.mark.asyncio
async def test_moderator_cannot_promote_self_or_remove_admins(client, db):
    owner, owner_id = await _user(db)
    mod, mod_id = await _user(db)
    slug = await _community(client, owner)
    await client.post(f"/api/communities/{slug}/join", headers=mod)
    assert (await client.patch(f"/api/communities/{slug}/members/{mod_id}?role=moderator", headers=owner)).status_code == 200
    assert (await client.patch(f"/api/communities/{slug}/members/{mod_id}?role=admin", headers=mod)).status_code == 403
    assert (await client.delete(f"/api/communities/{slug}/members/{owner_id}", headers=mod)).status_code == 403


@pytest.mark.asyncio
async def test_last_admin_cannot_be_demoted_and_leaving_works(client, db):
    owner, owner_id = await _user(db)
    member, _ = await _user(db)
    slug = await _community(client, owner)
    assert (await client.patch(f"/api/communities/{slug}/members/{owner_id}?role=member", headers=owner)).status_code == 400
    await client.post(f"/api/communities/{slug}/join", headers=member)
    r = await client.delete(f"/api/communities/{slug}/leave", headers=member)
    assert r.status_code == 204, r.text  # used to crash on SQLite (no GREATEST())


# ── Accounts & validation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_emails_are_case_insensitive(client, db):
    u = _u()
    r1 = await client.post("/api/auth/register", json={
        "email": f"Ada.{u}@Example.com", "username": f"ada_{u}", "full_name": "Ada", "password": "password-123"})
    assert r1.status_code == 201
    r2 = await client.post("/api/auth/register", json={
        "email": f"ada.{u}@example.com", "username": f"ada2_{u}", "full_name": "Ada", "password": "password-123"})
    assert r2.status_code == 400
    login = await client.post("/api/auth/login", json={"identifier": f"ADA.{u}@EXAMPLE.COM", "password": "password-123"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_event_input_validation(client, db):
    admin, _ = await _user(db, "admin")
    now = datetime.now(timezone.utc)
    base = {"title": "Validation event", "description": "x" * 30, "venue_name": "Venue",
            "address": "1 Test Street", "city": "Lagos"}
    backwards = {**base, "start_date": (now + timedelta(days=2)).isoformat(), "end_date": (now + timedelta(days=1)).isoformat()}
    assert (await client.post("/api/events", json=backwards, headers=admin)).status_code == 422
    negative = {**base, "start_date": (now + timedelta(days=1)).isoformat(),
                "end_date": (now + timedelta(days=2)).isoformat(), "capacity": -5}
    assert (await client.post("/api/events", json=negative, headers=admin)).status_code == 422


@pytest.mark.asyncio
async def test_draft_guest_list_is_private(client, db):
    host_headers, host = await _user(db, "organizer")
    eid = await _event(db, host, status="draft", review_status="pending")
    assert (await client.get(f"/api/events/{eid}/attendees")).status_code == 404
    assert (await client.get(f"/api/events/{eid}/attendees", headers=host_headers)).status_code == 200


def test_ticket_email_escapes_organizer_text():
    html = _ticket_html('<a href="https://evil.example">Claim refund</a>', "Mon", "<b>Venue</b>", "",
                        "VIP", 1, 1000.0, "abcdef123456", "https://turnup.app/tickets/1")
    assert "<a href=\"https://evil.example\">" not in html
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in html


@pytest.mark.asyncio
async def test_repeat_views_are_counted_once(client, db):
    _, host = await _user(db, "organizer")
    eid = await _event(db, host)
    viewer, _ = await _user(db)
    for _ in range(3):
        assert (await client.post(f"/api/events/{eid}/views", headers=viewer)).status_code == 204
    assert (await _get(db, Event, eid)).views_count == 1
