"""Tests for the moderator/organizer event approval workflow and admin bypass."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.auth_tokens import UserSession
from app.models.user import User
from app.services.auth import create_access_token


@pytest_asyncio.fixture
async def role_auth(db):
    """Factory fixture: insert a fresh user with a given role + session; return auth headers."""
    async def _make(role: str):
        user_id = str(uuid.uuid4())
        jti = str(uuid.uuid4())
        db.add(User(
            id=user_id, username=f"{role}_{user_id[:8]}", role=role,
            full_name=f"{role.title()} User", is_active=True, is_deleted=False,
        ))
        db.add(UserSession(
            id=str(uuid.uuid4()), user_id=user_id, jti=jti, is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        ))
        await db.commit()
        token, _ = create_access_token(user_id, jti)
        return {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}
    return _make


def _event_payload(**overrides) -> dict:
    start = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "title": "Test Event Title",
        "description": "A sufficiently long description of the test event.",
        "venue_name": "Test Venue",
        "address": "123 Test Street",
        "city": "Lagos",
        "country": "Nigeria",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(hours=3)).isoformat(),
        "status": "published",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_organizer_event_requires_approval(client, role_auth):
    organizer = await role_auth("organizer")
    resp = await client.post("/api/events", json=_event_payload(), headers=organizer["headers"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["review_status"] == "pending"


@pytest.mark.asyncio
async def test_moderator_event_requires_approval(client, role_auth):
    moderator = await role_auth("moderator")
    resp = await client.post("/api/events", json=_event_payload(title="Mod Event Title"), headers=moderator["headers"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["review_status"] == "pending"


@pytest.mark.asyncio
async def test_admin_event_bypasses_approval(client, role_auth):
    admin = await role_auth("admin")
    resp = await client.post("/api/events", json=_event_payload(title="Admin Event Title"), headers=admin["headers"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "published"
    assert data["review_status"] == "approved"


@pytest.mark.asyncio
async def test_attendee_cannot_create_event(client, role_auth):
    attendee = await role_auth("attendee")
    resp = await client.post("/api/events", json=_event_payload(), headers=attendee["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_approve_publishes_pending_event(client, role_auth):
    organizer = await role_auth("organizer")
    admin = await role_auth("admin")

    create_resp = await client.post("/api/events", json=_event_payload(title="Needs Approval"), headers=organizer["headers"])
    event_id = create_resp.json()["id"]

    # Not visible publicly while pending
    list_resp = await client.get("/api/events")
    assert event_id not in [e["id"] for e in list_resp.json()]

    approve_resp = await client.post(f"/api/admin/events/{event_id}/approve", headers=admin["headers"])
    assert approve_resp.status_code == 200
    approved = approve_resp.json()
    assert approved["status"] == "published"
    assert approved["review_status"] == "approved"

    list_resp = await client.get("/api/events")
    assert event_id in [e["id"] for e in list_resp.json()]


@pytest.mark.asyncio
async def test_admin_reject_with_note(client, role_auth):
    organizer = await role_auth("organizer")
    admin = await role_auth("admin")

    create_resp = await client.post("/api/events", json=_event_payload(title="Reject Me"), headers=organizer["headers"])
    event_id = create_resp.json()["id"]

    reject_resp = await client.post(
        f"/api/admin/events/{event_id}/reject",
        json={"note": "Missing venue details, please clarify."},
        headers=admin["headers"],
    )
    assert reject_resp.status_code == 200
    rejected = reject_resp.json()
    assert rejected["review_status"] == "rejected"
    assert rejected["review_note"] == "Missing venue details, please clarify."


@pytest.mark.asyncio
async def test_organizer_cannot_self_publish_pending_event(client, role_auth):
    organizer = await role_auth("organizer")
    create_resp = await client.post("/api/events", json=_event_payload(title="Sneaky Publish"), headers=organizer["headers"])
    event_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/events/{event_id}", json={"status": "published"}, headers=organizer["headers"],
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_editing_rejected_event_resubmits_for_review(client, role_auth):
    organizer = await role_auth("organizer")
    admin = await role_auth("admin")

    create_resp = await client.post("/api/events", json=_event_payload(title="Fix And Resubmit"), headers=organizer["headers"])
    event_id = create_resp.json()["id"]

    await client.post(
        f"/api/admin/events/{event_id}/reject",
        json={"note": "Fix the address"}, headers=admin["headers"],
    )

    patch_resp = await client.patch(
        f"/api/events/{event_id}", json={"address": "456 Fixed Ave"}, headers=organizer["headers"],
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["review_status"] == "pending"
    assert data["review_note"] is None
