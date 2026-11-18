"""Account flows behind the new settings / login screens: 2FA at login and via magic link,
sessions, password change, logout, account deletion, and phone-only accounts."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pyotp
import pytest
from sqlalchemy import select

from app.middleware.rate_limit import limiter
from app.models.auth_tokens import MagicLink, UserSession
from app.models.user import User
from app.routers import auth as auth_router
from app.services.auth import create_access_token, hash_password


@pytest.fixture(autouse=True)
def _no_rate_limits():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def _password_user(db, password="correct-horse-1"):
    uid, u = str(uuid.uuid4()), _u()
    db.add(User(id=uid, username=f"user_{u}", email=f"user_{u}@example.com", full_name="Pat",
                hashed_password=hash_password(password)))
    await db.commit()
    return uid, f"user_{u}", f"user_{u}@example.com", password


async def _login(client, identifier, password) -> dict:
    r = await client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _enable_2fa(client, token: str) -> str:
    setup = await client.post("/api/auth/2fa/setup", headers=_bearer(token))
    secret = setup.json()["secret"]
    r = await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert len(r.json()["backup_codes"]) == 10
    return secret


@pytest.mark.asyncio
async def test_login_with_2fa_requires_code(client, db):
    _, username, _, pw = await _password_user(db)
    token = (await _login(client, username, pw))["access_token"]
    secret = await _enable_2fa(client, token)

    challenge = await _login(client, username, pw)
    assert challenge.get("requires_2fa") is True and "access_token" not in challenge

    bad = await client.post("/api/auth/2fa/verify", json={"token": challenge["temp_token"], "code": "000000"})
    assert bad.status_code == 401
    good = await client.post("/api/auth/2fa/verify",
                             json={"token": challenge["temp_token"], "code": pyotp.TOTP(secret).now()})
    assert good.status_code == 200, good.text
    me = await client.get("/api/auth/me", headers=_bearer(good.json()["access_token"]))
    assert me.json()["two_factor_enabled"] is True and me.json()["has_password"] is True


@pytest.mark.asyncio
async def test_magic_link_does_not_bypass_2fa(client, db):
    _, username, email, pw = await _password_user(db)
    token = (await _login(client, username, pw))["access_token"]
    await _enable_2fa(client, token)

    with patch.object(auth_router, "send_magic_link_email", new=AsyncMock()):
        await client.post("/api/auth/magic-link", json={"email": email})
    db.expire_all()
    link = (await db.execute(select(MagicLink.token).where(MagicLink.email == email))).scalar_one()
    r = await client.get(f"/api/auth/magic-link/verify?token={link}")
    assert r.status_code == 200
    assert r.json().get("requires_2fa") is True and "access_token" not in r.json()


@pytest.mark.asyncio
async def test_magic_link_send_failure_is_not_a_500(client, db):
    with patch.object(auth_router, "send_magic_link_email", new=AsyncMock(side_effect=OSError("smtp down"))):
        r = await client.post("/api/auth/magic-link", json={"email": f"x_{_u()}@example.com"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_change_password_signs_out_other_devices_only(client, db):
    _, username, _, pw = await _password_user(db)
    phone = (await _login(client, username, pw))["access_token"]
    laptop = (await _login(client, username, pw))["access_token"]

    r = await client.post("/api/auth/change-password",
                          json={"current_password": pw, "new_password": "a-much-better-one"},
                          headers=_bearer(laptop))
    assert r.status_code == 200, r.text
    assert (await client.get("/api/auth/me", headers=_bearer(laptop))).status_code == 200
    assert (await client.get("/api/auth/me", headers=_bearer(phone))).status_code == 401


@pytest.mark.asyncio
async def test_sessions_flag_current_and_revoke_others(client, db):
    _, username, _, pw = await _password_user(db)
    a = (await _login(client, username, pw))["access_token"]
    await _login(client, username, pw)
    sessions = (await client.get("/api/auth/sessions", headers=_bearer(a))).json()
    assert len(sessions) == 2
    assert sum(s["is_current"] for s in sessions) == 1

    r = await client.delete("/api/auth/sessions", headers=_bearer(a))
    assert r.json()["message"] == "Signed out of 1 other device"
    assert len((await client.get("/api/auth/sessions", headers=_bearer(a))).json()) == 1


@pytest.mark.asyncio
async def test_logout_invalidates_token_on_server(client, db):
    _, username, _, pw = await _password_user(db)
    token = (await _login(client, username, pw))["access_token"]
    assert (await client.post("/api/auth/logout", headers=_bearer(token))).status_code == 200
    assert (await client.get("/api/auth/me", headers=_bearer(token))).status_code == 401


@pytest.mark.asyncio
async def test_new_passwords_need_eight_characters(client, db):
    u = _u()
    r = await client.post("/api/auth/register", json={
        "email": f"n_{u}@example.com", "username": f"n_{u}", "full_name": "New", "password": "short7!"})
    assert r.status_code == 422


# ── Phone-only accounts (no email, no name, no password) ───────────────────────

async def _phone_user(db) -> tuple[dict, str, str]:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    username = f"user{_u()}"
    db.add(User(id=uid, username=username, phone_number="+234" + str(uuid.uuid4().int)[:10]))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return _bearer(create_access_token(uid, jti)[0]), uid, username


@pytest.mark.asyncio
async def test_phone_only_user_can_load_their_account(client, db):
    headers, _, _ = await _phone_user(db)
    r = await client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["email"] is None and r.json()["full_name"] == "" and r.json()["has_password"] is False


@pytest.mark.asyncio
async def test_passwordless_user_can_delete_account_by_typing_username(client, db):
    headers, uid, username = await _phone_user(db)
    wrong = await client.request("DELETE", "/api/auth/account", json={"confirm_username": "nope"}, headers=headers)
    assert wrong.status_code == 400
    ok = await client.request("DELETE", "/api/auth/account", json={"confirm_username": f"@{username}"}, headers=headers)
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert (await db.execute(select(User.is_deleted).where(User.id == uid))).scalar_one() is True
