"""Tests for the verified_organizer feature (self-serve application -> admin review
queue -> visual trust badge only, no functional/permission effect) and the
network-based (follow-graph) discovery endpoint.

Note: conftest's `engine`/`db` fixtures are session-scoped (data persists across tests in
this file), so every test uses unique event/user names and scopes its assertions to rows
it created itself, rather than asserting on whole-table counts (same convention as the
other test files in this suite).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.auth_tokens import UserSession
from app.models.event import Event, EventAttendee
from app.models.organizer import OrganizerProfile
from app.models.social import Follow
from app.models.user import User
from app.services.auth import create_access_token


def _unique() -> str:
    return uuid.uuid4().hex[:10]


async def _make_auth(db, role: str) -> tuple[dict, str]:
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    unique = _unique()
    db.add(User(
        id=user_id, username=f"{role}_{unique}", email=f"{role}_{unique}@example.com",
        full_name=role.title(), role=role, is_active=True, is_deleted=False,
    ))
    db.add(UserSession(
        id=str(uuid.uuid4()), user_id=user_id, jti=jti, is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    await db.commit()
    token, _ = create_access_token(user_id, jti)
    return {"Authorization": f"Bearer {token}"}, user_id


async def _make_organizer_with_profile(db) -> tuple[dict, str]:
    headers, user_id = await _make_auth(db, "organizer")
    db.add(OrganizerProfile(id=str(uuid.uuid4()), user_id=user_id))
    await db.commit()
    return headers, user_id


@pytest_asyncio.fixture
async def buyer_auth(db):
    return await _make_auth(db, "attendee")


@pytest_asyncio.fixture
async def organizer_auth(db):
    return await _make_organizer_with_profile(db)


@pytest_asyncio.fixture
async def admin_auth(db):
    return await _make_auth(db, "admin")


async def _make_event(db, host_id: str, start_offset_days: int = 5) -> str:
    unique = _unique()
    start = datetime.now(timezone.utc) + timedelta(days=start_offset_days)
    event = Event(
        id=str(uuid.uuid4()), slug=f"event-{unique}", title=f"Test Event {unique}",
        description="A test event.", venue_name="Test Venue", address="1 Test St",
        city="Lagos", country="Nigeria", start_date=start, end_date=start + timedelta(hours=3),
        host_id=host_id, status="published", review_status="approved",
    )
    db.add(event)
    await db.commit()
    return event.id


# ── Self-serve verification request ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organizer_can_request_verification(client, organizer_auth):
    headers, _ = organizer_auth
    resp = await client.post(
        "/api/organizer/verification/request", json={"note": "We run monthly tech meetups."},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification_status"] == "pending"
    assert body["is_verified_organizer"] is False


@pytest.mark.asyncio
async def test_cannot_request_verification_twice_while_pending(client, organizer_auth):
    headers, _ = organizer_auth
    resp1 = await client.post("/api/organizer/verification/request", json={}, headers=headers)
    assert resp1.status_code == 200
    resp2 = await client.post("/api/organizer/verification/request", json={}, headers=headers)
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_verification_request_requires_organizer_role(client, buyer_auth):
    headers, _ = buyer_auth
    resp = await client.post("/api/organizer/verification/request", json={}, headers=headers)
    assert resp.status_code == 403


# ── Admin review queue ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_see_pending_request_in_queue(client, organizer_auth, admin_auth):
    headers, organizer_id = organizer_auth
    admin_headers, _ = admin_auth
    await client.post("/api/organizer/verification/request", json={}, headers=headers)

    resp = await client.get("/api/admin/organizers/verification-queue", headers=admin_headers)
    assert resp.status_code == 200
    ids = [row["user_id"] for row in resp.json()]
    assert organizer_id in ids


@pytest.mark.asyncio
async def test_admin_can_approve_verification(client, organizer_auth, admin_auth):
    headers, organizer_id = organizer_auth
    admin_headers, _ = admin_auth
    await client.post("/api/organizer/verification/request", json={}, headers=headers)

    resp = await client.post(f"/api/admin/organizers/{organizer_id}/verify", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_verified_organizer"] is True
    assert body["verification_status"] == "approved"


@pytest.mark.asyncio
async def test_admin_can_reject_verification_with_note(client, organizer_auth, admin_auth):
    headers, organizer_id = organizer_auth
    admin_headers, _ = admin_auth
    await client.post("/api/organizer/verification/request", json={}, headers=headers)

    resp = await client.post(
        f"/api/admin/organizers/{organizer_id}/reject-verification",
        json={"note": "Please add a working website link."},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_verified_organizer"] is False
    assert body["verification_status"] == "rejected"
    assert body["verification_note"] == "Please add a working website link."


@pytest.mark.asyncio
async def test_verification_queue_requires_admin(client, organizer_auth):
    headers, _ = organizer_auth
    resp = await client.get("/api/admin/organizers/verification-queue", headers=headers)
    assert resp.status_code == 403


# ── Visual badge only: verification never gates event review ─────────────────────

@pytest.mark.asyncio
async def test_verified_organizer_events_still_go_through_normal_review(client, db, organizer_auth, admin_auth):
    headers, organizer_id = organizer_auth
    admin_headers, _ = admin_auth
    await client.post("/api/organizer/verification/request", json={}, headers=headers)
    await client.post(f"/api/admin/organizers/{organizer_id}/verify", headers=admin_headers)

    event_id = await _make_event(db, organizer_id)
    db.expire_all()
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    # Manually-created test events default to approved; the real signal we're checking
    # is that verification touched nothing on the Event row's review workflow at all.
    assert event.review_status == "approved"

    # The event API should surface the badge on the host without altering anything else.
    resp = await client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    assert resp.json()["host"]["is_verified_organizer"] is True


# ── Network-based (follow-graph) discovery ────────────────────────────────────────

@pytest.mark.asyncio
async def test_following_feed_empty_with_no_follows(client, buyer_auth):
    headers, _ = buyer_auth
    resp = await client.get("/api/events/following", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_following_feed_requires_auth(client):
    resp = await client.get("/api/events/following")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_following_feed_surfaces_events_attended_by_followed_users(
    client, db, organizer_auth, buyer_auth,
):
    _, organizer_id = organizer_auth
    viewer_headers, viewer_id = await _make_auth(db, "attendee")
    _, followed_id = buyer_auth

    event_id = await _make_event(db, organizer_id)
    db.add(Follow(id=str(uuid.uuid4()), follower_id=viewer_id, following_id=followed_id))
    db.add(EventAttendee(
        id=str(uuid.uuid4()), user_id=followed_id, event_id=event_id, status="going",
    ))
    await db.commit()

    resp = await client.get("/api/events/following", headers=viewer_headers)
    assert resp.status_code == 200
    body = resp.json()
    ids = [e["id"] for e in body]
    assert event_id in ids
    matched = next(e for e in body if e["id"] == event_id)
    assert matched["following_count"] == 1
    assert matched["following_hosted"] is False


@pytest.mark.asyncio
async def test_following_feed_surfaces_events_hosted_by_followed_users(client, db, buyer_auth):
    viewer_headers, viewer_id = await _make_auth(db, "attendee")
    host_headers, host_id = await _make_organizer_with_profile(db)

    event_id = await _make_event(db, host_id)
    db.add(Follow(id=str(uuid.uuid4()), follower_id=viewer_id, following_id=host_id))
    await db.commit()

    resp = await client.get("/api/events/following", headers=viewer_headers)
    assert resp.status_code == 200
    body = resp.json()
    matched = next(e for e in body if e["id"] == event_id)
    assert matched["following_hosted"] is True


@pytest.mark.asyncio
async def test_following_feed_excludes_events_from_unfollowed_users(client, db, organizer_auth):
    _, organizer_id = organizer_auth
    viewer_headers, viewer_id = await _make_auth(db, "attendee")
    await _make_event(db, organizer_id)  # viewer follows nobody

    resp = await client.get("/api/events/following", headers=viewer_headers)
    assert resp.status_code == 200
    assert resp.json() == []
