"""The Turnup-hosted Telegram bot: allowlisted senders DM a poster, link or details; it becomes
a pending event; the bot replies, and again once an admin reviews it. Also: admins can edit
bot-hosted events. Telegram and the AI drafter are mocked.

The DB is session-scoped (shared across tests), so every test makes its own connection.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent import AgentConnection, AgentSubmission
from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.user import User
from app.routers import telegram_bot
from app.services import agent_intake, ai_agent, telegram
from app.services.auth import create_access_token

MY_ID = "111222333"
STRANGER_ID = "999888777"


@pytest.fixture(autouse=True)
def _public_base(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://turnup.test")


@pytest.fixture(autouse=True)
def _background_sessions(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(telegram_bot, "session_factory", factory)


@pytest.fixture
def tg(monkeypatch):
    """Fake Telegram API: records what the bot sends."""
    sent: list[tuple[str, str]] = []

    async def send_message(token, chat_id, text):
        sent.append((chat_id, text))

    fake = type("TG", (), {})()
    fake.sent = sent
    fake.download_image = AsyncMock(return_value=b"\xff\xd8poster-bytes")
    fake.get_me = AsyncMock(return_value={"username": "turnup_events_bot"})
    fake.set_webhook = AsyncMock()
    fake.delete_webhook = AsyncMock()
    monkeypatch.setattr(telegram, "send_message", send_message)
    monkeypatch.setattr(telegram, "send_typing", AsyncMock())
    for name in ("download_image", "get_me", "set_webhook", "delete_webhook"):
        monkeypatch.setattr(telegram, name, getattr(fake, name))
    return fake


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


async def _auth(db, role: str) -> tuple[str, dict]:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=uid, username=f"{role}_{uid[:8]}", full_name=role.title(), role=role,
                is_active=True, is_deleted=False))
    db.add(UserSession(id=str(uuid.uuid4()), user_id=uid, jti=jti, is_active=True,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=2)))
    await db.commit()
    token, _ = create_access_token(uid, jti)
    return uid, {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin(db):
    return (await _auth(db, "admin"))[1]


async def _bot(client, admin, db, tg, *, connect=True, **body) -> tuple[dict, str]:
    """A Telegram connection allowing MY_ID, connected; returns (connection, webhook secret)."""
    resp = await client.post("/api/admin/integrations", headers=admin, json={
        "name": f"TG {uuid.uuid4().hex[:6]}", "kind": "telegram",
        "telegram_bot_token": "123:ABC", "allowed_senders": MY_ID, **body,
    })
    assert resp.status_code == 201, resp.text
    conn = resp.json()
    if connect:
        resp = await client.post(f"/api/admin/integrations/{conn['id']}/telegram/connect", headers=admin)
        assert resp.status_code == 200, resp.text
        conn = resp.json()
    stored = await db.get(AgentConnection, conn["id"])
    await db.refresh(stored)
    return conn, agent_intake.connection_secrets(stored).get("webhook_secret", "")


_msg_ids = iter(range(1000, 10**6))


def _update(sender: str = MY_ID, *, text: str | None = None, photo: bool = False, message_id: int | None = None) -> dict:
    msg = {"message_id": message_id or next(_msg_ids), "chat": {"id": int(sender), "type": "private"},
           "from": {"id": int(sender), "first_name": "Ada", "username": "ada"}}
    if text is not None:
        msg["caption" if photo else "text"] = text
    if photo:
        msg["photo"] = [{"file_id": "small"}, {"file_id": "large"}]
    return {"update_id": next(_msg_ids), "message": msg}


async def _post(client, conn, secret, update) -> int:
    resp = await client.post(f"/api/integrations/telegram/{conn['id']}", json=update,
                             headers={"X-Telegram-Bot-Api-Secret-Token": secret})
    return resp.status_code


def _draft(**overrides) -> dict:
    u = uuid.uuid4().hex[:8]
    start = datetime.now(timezone.utc) + timedelta(days=6)
    d = dict(title=f"Afro Night {u}", description="Afrobeats all night with live DJs.",
             venue_name=f"Club {u}", address="3 Bourdillon", city="Lagos", country="Nigeria",
             start_date=start.isoformat(), end_date="", is_free=True, currency="NGN",
             event_type="physical", category_guess="", tags="", confidence_notes="", cover_image=None)
    d.update(overrides)
    return d


# ── Setting up ───────────────────────────────────────────────────────────────

async def test_create_and_connect(client, admin, db, tg):
    conn, secret = await _bot(client, admin, db, tg)
    assert conn["kind"] == "telegram" and conn["telegram_connected"] is True
    assert conn["telegram_bot_username"] == "turnup_events_bot" and conn["has_bot_token"] is True
    assert conn["allowed_senders"] == MY_ID and conn["api_key_prefix"] is None
    assert "123:ABC" not in str(conn)
    url, sent_secret = tg.set_webhook.call_args.args[1:]
    assert url == f"https://turnup.test/api/integrations/telegram/{conn['id']}" and sent_secret == secret

    stored = await db.get(AgentConnection, conn["id"])
    assert "123:ABC" not in stored.secrets_encrypted


async def test_create_validation(client, admin, tg):
    base = {"name": "Bot", "kind": "telegram"}
    assert (await client.post("/api/admin/integrations", headers=admin, json=base)).status_code == 422
    resp = await client.post("/api/admin/integrations", headers=admin,
                             json={**base, "telegram_bot_token": "1:A", "allowed_senders": "@ada"})
    assert resp.status_code == 422 and "/whoami" in resp.json()["detail"]


async def test_connect_needs_public_https(client, admin, db, tg, monkeypatch):
    conn, _ = await _bot(client, admin, db, tg, connect=False)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")
    resp = await client.post(f"/api/admin/integrations/{conn['id']}/telegram/connect", headers=admin)
    assert resp.status_code == 400 and "PUBLIC_BASE_URL" in resp.json()["detail"]


async def test_bad_token_reported(client, admin, db, tg):
    conn, _ = await _bot(client, admin, db, tg, connect=False)
    tg.get_me.side_effect = telegram.TelegramError("Unauthorized")
    resp = await client.post(f"/api/admin/integrations/{conn['id']}/telegram/connect", headers=admin)
    assert resp.status_code == 422 and "Unauthorized" in resp.json()["detail"]


async def test_telegram_connections_have_no_api_access(client, admin, db, tg):
    conn, _ = await _bot(client, admin, db, tg)
    assert (await client.post(f"/api/admin/integrations/{conn['id']}/rotate-key", headers=admin)).status_code == 400


# ── The webhook ──────────────────────────────────────────────────────────────

async def test_webhook_requires_the_secret(client, admin, db, tg):
    conn, secret = await _bot(client, admin, db, tg)
    assert await _post(client, conn, "wrong", _update(text="/help")) == 401
    resp = await client.post(f"/api/integrations/telegram/{conn['id']}", json=_update(text="/help"))
    assert resp.status_code == 401
    assert await _post(client, {"id": str(uuid.uuid4())}, secret, _update(text="/help")) == 404
    assert tg.sent == []


async def test_whoami_and_help(client, admin, db, tg):
    conn, secret = await _bot(client, admin, db, tg)
    await _post(client, conn, secret, _update(STRANGER_ID, text="/whoami"))
    await _post(client, conn, secret, _update(MY_ID, text="/start"))
    await _post(client, conn, secret, _update(STRANGER_ID, text="/help"))
    assert tg.sent[0] == (STRANGER_ID, f"Your Telegram id is {STRANGER_ID}")
    assert tg.sent[1][0] == MY_ID and "poster" in tg.sent[1][1]
    assert tg.sent[2] == (STRANGER_ID, agent_intake.TELEGRAM_NOT_OPEN)


async def test_strangers_are_told_not_open_yet(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=_draft())) as ai:
        assert await _post(client, conn, secret, _update(STRANGER_ID, text="party", photo=True)) == 200
    ai.assert_not_awaited()
    tg.download_image.assert_not_awaited()
    assert tg.sent == [(STRANGER_ID, agent_intake.TELEGRAM_NOT_OPEN)]
    log = (await db.execute(select(AgentSubmission).where(AgentSubmission.connection_id == conn["id"]))).scalars().all()
    assert [s.status for s in log] == ["sender_not_allowed"]
    listed = (await client.get("/api/admin/integrations", headers=admin)).json()
    assert next(c for c in listed if c["id"] == conn["id"])["used_today"] == 0


async def test_poster_becomes_a_pending_event(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    draft = _draft()
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=draft)) as ai:
        assert await _post(client, conn, secret, _update(text="Free before 10pm", photo=True)) == 200
    tg.download_image.assert_awaited_once_with("123:ABC", "large")
    kwargs = ai.call_args.kwargs
    assert kwargs["image_bytes"] == b"\xff\xd8poster-bytes" and kwargs["text"] == "Free before 10pm"

    ev = (await db.execute(select(Event).where(Event.title == draft["title"]))).scalar_one()
    assert (ev.status, ev.review_status, ev.created_via, ev.host_id) == ("draft", "pending", "telegram", bot_user)
    assert tg.sent[-1][0] == MY_ID and draft["title"] in tg.sent[-1][1] and "approval queue" in tg.sent[-1][1]

    queue = (await client.get("/api/admin/events", headers=admin, params={"q": draft["title"]})).json()
    assert queue[0]["agent_source"] == conn["name"] and queue[0]["created_via"] == "telegram"


async def test_link_is_read_as_a_page(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=_draft())) as ai:
        await _post(client, conn, secret, _update(text="check this https://tix.example.com/e/42 !"))
    assert ai.call_args.kwargs["url"] == "https://tix.example.com/e/42"
    assert ai.call_args.kwargs["text"] == "check this  !"  # the rest of the message, link removed


async def test_telegram_retries_are_harmless(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    update = _update(text="details here")
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=_draft())) as ai:
        await _post(client, conn, secret, update)
        await _post(client, conn, secret, update)
    assert ai.await_count == 1 and len(tg.sent) == 1


async def test_not_an_event_reply(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=_draft(start_date=""))):
        await _post(client, conn, secret, _update(text="hi"))
    assert "couldn't find an event" in tg.sent[-1][1]


async def test_paused_bot_does_nothing(client, admin, db, tg, bot_user):
    conn, secret = await _bot(client, admin, db, tg)
    await client.patch(f"/api/admin/integrations/{conn['id']}", headers=admin, json={"is_active": False})
    assert await _post(client, conn, secret, _update(text="/help")) == 200
    assert tg.sent == []


# ── Review outcome in the chat ───────────────────────────────────────────────

async def _submitted_event(client, admin, db, tg) -> Event:
    conn, secret = await _bot(client, admin, db, tg)
    draft = _draft()
    with patch.object(ai_agent, "draft_event", AsyncMock(return_value=draft)):
        await _post(client, conn, secret, _update(text="details"))
    tg.sent.clear()
    return (await db.execute(select(Event).where(Event.title == draft["title"]))).scalar_one()


async def test_approval_message(client, admin, db, tg, bot_user):
    ev = await _submitted_event(client, admin, db, tg)
    assert (await client.post(f"/api/admin/events/{ev.id}/approve", headers=admin)).status_code == 200
    assert len(tg.sent) == 1
    chat, text = tg.sent[0]
    assert chat == MY_ID and "Approved" in text and f"/events/{ev.slug}" in text


async def test_rejection_message_sent_once(client, admin, db, tg, bot_user):
    ev = await _submitted_event(client, admin, db, tg)
    for _ in range(2):
        await client.post(f"/api/admin/events/{ev.id}/reject", headers=admin, json={"note": "Date is wrong"})
    assert tg.sent == [(MY_ID, f"“{ev.title}” wasn't approved.\nNote: Date is wrong")]


# ── Admins edit bot-hosted events ────────────────────────────────────────────

async def test_admin_can_open_and_edit_bot_events(client, admin, db, tg, bot_user):
    ev = await _submitted_event(client, admin, db, tg)
    detail = await client.get(f"/api/events/{ev.id}", headers=admin)
    assert detail.status_code == 200 and detail.json()["can_admin_edit"] is True

    resp = await client.patch(f"/api/events/{ev.id}", headers=admin, json={"title": "Afro Night (fixed)"})
    assert resp.status_code == 200, resp.text
    await db.refresh(ev)
    assert ev.title == "Afro Night (fixed)" and ev.review_status == "pending"

    # Publishing goes through Approve, so the sender hears about it.
    resp = await client.patch(f"/api/events/{ev.id}", headers=admin, json={"status": "published"})
    assert resp.status_code == 409


async def test_admin_edit_is_limited_to_bot_events(client, admin, db, tg, bot_user):
    org_id, org = await _auth(db, "organizer")
    resp = await client.post("/api/events", headers=org, json={
        "title": "Organizer draft", "description": "Someone else's event entirely.",
        "venue_name": "Some Hall", "address": "12 Admiralty Way", "city": "Lagos",
        "start_date": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=9, hours=2)).isoformat(),
    })
    assert resp.status_code in (200, 201), resp.text
    eid = resp.json()["id"]
    assert (await client.patch(f"/api/events/{eid}", headers=admin, json={"title": "Hijack"})).status_code == 403

    ev = await _submitted_event(client, admin, db, tg)
    _, mod = await _auth(db, "moderator")
    assert (await client.get(f"/api/events/{ev.id}", headers=mod)).status_code == 404
    assert (await client.patch(f"/api/events/{ev.id}", headers=mod, json={"title": "x" * 5})).status_code == 403
