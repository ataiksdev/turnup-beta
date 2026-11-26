"""Agent connections: outside bots submit events with an API key; every event waits for admin
approval, and the review outcome is POSTed back to the bot's callback URL, signed.

The DB is session-scoped (shared across tests), so each test makes its own connection and
asserts only on rows it created.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.models.agent import AgentConnection, AgentSubmission
from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.user import User
from app.services import agent_intake, ai_agent
from app.services.auth import create_access_token


@pytest_asyncio.fixture
async def bot_user(db):
    existing = (await db.execute(select(User).where(User.username == settings.scout_bot_username))).scalar_one_or_none()
    if existing:
        return existing.id
    uid = str(uuid.uuid4())
    db.add(User(id=uid, username=settings.scout_bot_username, full_name="Turnup Scout",
                role="moderator", is_active=True, is_deleted=False))
    await db.commit()
    return uid


async def _user_auth(db, role: str) -> dict:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=uid, username=f"{role}_{uid[:8]}", full_name=role.title(), role=role,
                is_active=True, is_deleted=False))
    db.add(UserSession(id=str(uuid.uuid4()), user_id=uid, jti=jti, is_active=True,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=2)))
    await db.commit()
    token, _ = create_access_token(uid, jti)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin(db):
    return await _user_auth(db, "admin")


async def _connect(client, admin, **body) -> dict:
    resp = await client.post("/api/admin/integrations", headers=admin,
                             json={"name": f"Bot {uuid.uuid4().hex[:6]}", **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _key(conn: dict) -> dict:
    return {"Authorization": f"Bearer {conn['api_key']}"}


def _event_body(**overrides) -> dict:
    u = uuid.uuid4().hex[:8]
    start = datetime.now(timezone.utc) + timedelta(days=7)
    body = dict(
        title=f"Rooftop Jazz {u}", description="An evening of live jazz on the rooftop with friends.",
        start_date=start.isoformat(), venue_name=f"Sky Bar {u}", address="1 Marina Rd", city="Lagos",
        is_free=False, price_min=5000, price_max=15000, tags=["jazz", "live music"],
        cover_image="https://cdn.example.com/poster.jpg", submitted_by="+2348030000000",
    )
    body.update(overrides)
    return body


def _ai_draft(**overrides) -> dict:
    u = uuid.uuid4().hex[:8]
    start = datetime.now(timezone.utc) + timedelta(days=3)
    base = dict(
        title=f"Poster Party {u}", description="A party read off a poster, with DJs all night.",
        venue_name=f"Hall {u}", address="2 Allen Ave", city="Ikeja", country="Nigeria",
        start_date=start.isoformat(), end_date="", is_free=True, currency="NGN",
        event_type="physical", category_guess="", tags="party", confidence_notes="",
        cover_image=None,
    )
    base.update(overrides)
    return base


# ── Admin management ─────────────────────────────────────────────────────────

async def test_create_shows_key_once_and_stores_only_its_hash(client, admin, db):
    conn = await _connect(client, admin)
    assert conn["api_key"].startswith("tuk_") and conn["callback_secret"].startswith("whsec_")
    assert conn["api_key_prefix"] == conn["api_key"][:12]

    listed = (await client.get("/api/admin/integrations", headers=admin)).json()
    row = next(c for c in listed if c["id"] == conn["id"])
    assert "api_key" not in row and "callback_secret" not in row

    stored = await db.get(AgentConnection, conn["id"])
    assert stored.api_key_hash == hashlib.sha256(conn["api_key"].encode()).hexdigest()
    assert conn["callback_secret"] not in (stored.callback_secret_encrypted or "")


async def test_admin_only(client, db):
    mod = await _user_auth(db, "moderator")
    assert (await client.get("/api/admin/integrations", headers=mod)).status_code == 403
    assert (await client.post("/api/admin/integrations", headers=mod, json={"name": "x" * 3})).status_code == 403


async def test_callback_url_must_be_public(client, admin):
    resp = await client.post("/api/admin/integrations", headers=admin,
                             json={"name": "Internal", "callback_url": "http://127.0.0.1:8080/hook"})
    assert resp.status_code == 422


async def test_rotate_key_revokes_old_one(client, admin):
    conn = await _connect(client, admin)
    assert (await client.get("/api/integrations/v1/me", headers=_key(conn))).status_code == 200
    rotated = (await client.post(f"/api/admin/integrations/{conn['id']}/rotate-key", headers=admin)).json()
    assert rotated["api_key"] != conn["api_key"]
    assert (await client.get("/api/integrations/v1/me", headers=_key(conn))).status_code == 401
    assert (await client.get("/api/integrations/v1/me", headers=_key(rotated))).status_code == 200


# ── Agent API auth ───────────────────────────────────────────────────────────

async def test_bad_missing_and_paused_keys(client, admin):
    assert (await client.get("/api/integrations/v1/me")).status_code == 401
    assert (await client.get("/api/integrations/v1/me", headers={"X-API-Key": "tuk_nope"})).status_code == 401
    conn = await _connect(client, admin)
    assert (await client.get("/api/integrations/v1/me", headers={"X-API-Key": conn["api_key"]})).status_code == 200
    await client.patch(f"/api/admin/integrations/{conn['id']}", headers=admin, json={"is_active": False})
    resp = await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())
    assert resp.status_code == 403


# ── Submitting ───────────────────────────────────────────────────────────────

async def test_structured_event_waits_for_approval(client, admin, db, bot_user):
    conn = await _connect(client, admin)
    body = _event_body()
    resp = await client.post("/api/integrations/v1/events", headers=_key(conn), json=body)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["status"] == "created" and out["review_status"] == "pending" and out["event_url"] is None
    assert out["submitted_by"] == "+2348030000000"

    ev = await db.get(Event, out["event_id"])
    await db.refresh(ev)
    assert (ev.status, ev.review_status, ev.created_via, ev.host_id) == ("draft", "pending", "agent_api", bot_user)
    assert ev.tags == "jazz,live music" and ev.price_min == 5000

    # Not public until approved.
    assert (await client.get(f"/api/events/{ev.slug}")).status_code in (403, 404)

    queue = (await client.get("/api/admin/events", headers=admin, params={"review_status": "pending", "q": body["title"]})).json()
    assert queue[0]["agent_source"] == conn["name"]


async def test_events_hosted_by_chosen_account(client, admin, db):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, username=f"org_{uid[:8]}", role="organizer", is_active=True, is_deleted=False))
    await db.commit()
    conn = await _connect(client, admin, host_username=f"@org_{uid[:8]}")
    out = (await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())).json()
    ev = await db.get(Event, out["event_id"])
    assert ev.host_id == uid


async def test_naive_dates_rejected(client, admin):
    conn = await _connect(client, admin)
    resp = await client.post("/api/integrations/v1/events", headers=_key(conn),
                             json=_event_body(start_date="2026-12-24T19:00:00"))
    assert resp.status_code == 422


async def test_external_id_makes_resubmits_harmless(client, admin, db, bot_user):
    conn = await _connect(client, admin)
    body = _event_body(external_id="msg-123")
    first = await client.post("/api/integrations/v1/events", headers=_key(conn), json=body)
    again = await client.post("/api/integrations/v1/events", headers=_key(conn), json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["repeated"] is True and again.json()["event_id"] == first.json()["event_id"]
    count = len((await db.execute(select(AgentSubmission).where(
        AgentSubmission.connection_id == conn["id"]))).scalars().all())
    assert count == 1


async def test_duplicate_event_not_added_twice(client, admin, bot_user):
    a, b = await _connect(client, admin), await _connect(client, admin)
    body = _event_body()
    assert (await client.post("/api/integrations/v1/events", headers=_key(a), json=body)).status_code == 201
    resp = await client.post("/api/integrations/v1/events", headers=_key(b), json=body)
    assert resp.status_code == 409 and resp.json()["status"] == "skipped_duplicate"
    assert resp.json()["review_status"] is None  # not this bot's event to report on


async def test_poster_is_read_by_ai(client, admin, db, bot_user):
    conn = await _connect(client, admin)
    draft = _ai_draft()
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=draft)) as mock:
        resp = await client.post(
            "/api/integrations/v1/drafts", headers=_key(conn),
            data={"text": "this saturday!", "submitted_by": "chat:42", "external_id": "tg-1"},
            files={"image": ("poster.jpg", b"\xff\xd8fakejpeg", "image/jpeg")},
        )
    assert resp.status_code == 201, resp.text
    kwargs = mock.call_args.kwargs
    assert kwargs["image_bytes"] == b"\xff\xd8fakejpeg" and kwargs["image_media_type"] == "image/jpeg"
    assert kwargs["text"] == "this saturday!"
    ev = await db.get(Event, resp.json()["event_id"])
    assert ev.title == draft["title"] and ev.review_status == "pending"


async def test_raw_submission_validation(client, admin):
    conn = await _connect(client, admin)
    assert (await client.post("/api/integrations/v1/drafts", headers=_key(conn), data={"text": "  "})).status_code == 422
    resp = await client.post("/api/integrations/v1/drafts", headers=_key(conn),
                             files={"image": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert resp.status_code == 415


async def test_not_an_event_and_ai_failure(client, admin, bot_user):
    conn = await _connect(client, admin)
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=_ai_draft(start_date=""))):
        resp = await client.post("/api/integrations/v1/drafts", headers=_key(conn), data={"text": "hello"})
    assert resp.status_code == 422 and resp.json()["status"] == "skipped_no_event"
    with patch.object(ai_agent, "draft_event", AsyncMock(side_effect=ai_agent.AIAgentError("boom"))):
        resp = await client.post("/api/integrations/v1/drafts", headers=_key(conn), data={"text": "hello"})
    assert resp.status_code == 422 and resp.json()["status"] == "failed"
    assert "boom" not in resp.json()["message"]  # internal errors stay in the admin log

    log = (await client.get("/api/admin/integrations/submissions", headers=admin,
                            params={"connection_id": conn["id"]})).json()
    assert {r["status"] for r in log} == {"skipped_no_event", "failed"}
    assert any(r["error_note"] == "boom" for r in log)


async def test_daily_limit(client, admin, bot_user):
    conn = await _connect(client, admin, daily_limit=2)
    for _ in range(2):
        assert (await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())).status_code == 201
    resp = await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())
    assert resp.status_code == 429 and resp.json()["status"] == "over_limit"
    me = (await client.get("/api/integrations/v1/me", headers=_key(conn))).json()
    assert me == {"name": conn["name"], "daily_limit": 2, "used_today": 2}


async def test_cannot_read_another_connections_submissions(client, admin, bot_user):
    a, b = await _connect(client, admin), await _connect(client, admin)
    out = (await client.post("/api/integrations/v1/events", headers=_key(a), json=_event_body())).json()
    assert (await client.get(f"/api/integrations/v1/submissions/{out['submission_id']}", headers=_key(b))).status_code == 404
    assert (await client.get("/api/integrations/v1/submissions", headers=_key(b))).json() == []


# ── Review outcome back to the bot ───────────────────────────────────────────

async def test_approval_is_polled_and_called_back(client, admin, db, bot_user):
    conn = await _connect(client, admin, callback_url="https://bot.example.com/turnup")
    out = (await client.post("/api/integrations/v1/events", headers=_key(conn),
                             json=_event_body(external_id="wa-77"))).json()

    sent = []

    async def fake_post(url, body, *, timeout, headers):
        sent.append((url, body, headers))
        return type("R", (), {"status_code": 200})()

    with patch.object(agent_intake, "post_json_safely", fake_post):
        assert (await client.post(f"/api/admin/events/{out['event_id']}/approve", headers=admin)).status_code == 200

    assert len(sent) == 1
    url, body, headers = sent[0]
    payload = json.loads(body)
    assert url == "https://bot.example.com/turnup"
    assert payload["type"] == "event.approved" and payload["external_id"] == "wa-77"
    assert payload["submitted_by"] == "+2348030000000" and payload["event_url"].startswith(settings.frontend_url.rstrip("/") + "/events/")
    expected = hmac.new(conn["callback_secret"].encode(),
                        headers["X-Turnup-Timestamp"].encode() + b"." + body, hashlib.sha256).hexdigest()
    assert headers["X-Turnup-Signature"] == f"sha256={expected}"

    status = (await client.get(f"/api/integrations/v1/submissions/{out['submission_id']}", headers=_key(conn))).json()
    assert status["review_status"] == "approved" and status["event_url"]


async def test_rejection_note_reaches_the_bot_once(client, admin, bot_user):
    conn = await _connect(client, admin, callback_url="https://bot.example.com/turnup")
    out = (await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())).json()
    post = AsyncMock(return_value=type("R", (), {"status_code": 200})())
    with patch.object(agent_intake, "post_json_safely", post):
        await client.post(f"/api/admin/events/{out['event_id']}/reject", headers=admin, json={"note": "Wrong date on poster"})
        await client.post(f"/api/admin/events/{out['event_id']}/reject", headers=admin, json={"note": "Wrong date on poster"})
    assert post.await_count == 1
    payload = json.loads(post.call_args.args[1])
    assert payload["type"] == "event.rejected" and payload["review_note"] == "Wrong date on poster"
    status = (await client.get(f"/api/integrations/v1/submissions/{out['submission_id']}", headers=_key(conn))).json()
    assert status["review_status"] == "rejected" and "Wrong date on poster" in status["message"]


async def test_no_callback_without_url_and_failures_dont_block_review(client, admin, bot_user):
    quiet = await _connect(client, admin)
    out = (await client.post("/api/integrations/v1/events", headers=_key(quiet), json=_event_body())).json()
    post = AsyncMock()
    with patch.object(agent_intake, "post_json_safely", post):
        assert (await client.post(f"/api/admin/events/{out['event_id']}/approve", headers=admin)).status_code == 200
    post.assert_not_awaited()

    loud = await _connect(client, admin, callback_url="https://bot.example.com/down")
    out = (await client.post("/api/integrations/v1/events", headers=_key(loud), json=_event_body())).json()
    with patch.object(agent_intake, "post_json_safely", AsyncMock(side_effect=OSError("refused"))):
        assert (await client.post(f"/api/admin/events/{out['event_id']}/approve", headers=admin)).status_code == 200


async def test_delete_connection_keeps_its_events(client, admin, db, bot_user):
    conn = await _connect(client, admin)
    out = (await client.post("/api/integrations/v1/events", headers=_key(conn), json=_event_body())).json()
    assert (await client.delete(f"/api/admin/integrations/{conn['id']}", headers=admin)).status_code == 204
    assert (await client.get("/api/integrations/v1/me", headers=_key(conn))).status_code == 401
    db.expire_all()
    assert await db.get(Event, out["event_id"]) is not None
