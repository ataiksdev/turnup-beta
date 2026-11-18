"""Regression tests for the five critical findings fixed together:

1. OAuth account takeover (Instagram email step linking to an existing account; Google
   linking on an unverified email; disabled accounts logging in through OAuth).
2. Payments confirmed without checking the amount/currency Paystack actually collected.
3. Stored XSS through user-supplied URLs (javascript: hrefs).
4. Phone-OTP attempt counter rolled back on every wrong guess (unlimited brute force).
5. Refunds marked as refunded without any money being returned through Paystack.

Same conventions as test_tickets.py: unique names per test, plain-id variables, and
db.expire_all() before re-reading rows a request mutated.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.middleware.rate_limit import limiter
from app.models.auth_tokens import OAuthAccount, PhoneOTP, UserSession
from app.models.event import Event
from app.models.organizer import EventTemplate, TicketOrder, TicketTier
from app.models.user import User
from app.routers import auth as auth_router
from app.routers import events as events_router
from app.schemas.types import normalize_web_url, safe_web_url_or_none
from app.services import paystack, tickets
from app.services.auth import create_access_token, create_partial_oauth_token


@pytest.fixture(autouse=True)
def _no_rate_limits():
    # These tests deliberately repeat auth calls; rate limiting has its own tests.
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def _make_user(db, role="attendee", **fields) -> tuple[dict, str]:
    uid, jti, u = str(uuid.uuid4()), str(uuid.uuid4()), _u()
    db.add(User(id=uid, username=fields.pop("username", f"{role}_{u}"),
                email=fields.pop("email", f"{role}_{u}@example.com"),
                full_name=role.title(), role=role, **fields))
    db.add(UserSession(user_id=uid, jti=jti,
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}, uid


async def _make_event(db, host_id: str) -> str:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title=f"Event {_u()}", description="d" * 30,
                 venue_name="Venue", address="1 Test Street", city="Lagos", country="NG",
                 start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=3),
                 host_id=host_id, status="published", review_status="approved", is_free=False))
    await db.commit()
    return eid


async def _make_tier(db, event_id: str, price: float) -> str:
    tid = str(uuid.uuid4())
    db.add(TicketTier(id=tid, event_id=event_id, name=f"Tier {_u()}", price=price,
                      quantity=10, max_per_order=10, is_active=True))
    await db.commit()
    return tid


# ── 1. OAuth ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instagram_email_step_cannot_take_over_existing_account(client, db):
    victim_email = f"victim_{_u()}@example.com"
    _, victim_id = await _make_user(db, "admin", email=victim_email)
    partial = create_partial_oauth_token("instagram", f"ig-{_u()}", "attacker")

    resp = await client.post("/api/auth/oauth/complete",
                             json={"partial_token": partial, "email": victim_email})
    assert resp.status_code == 409
    assert "access_token" not in resp.json()

    db.expire_all()
    links = (await db.execute(select(OAuthAccount).where(OAuthAccount.user_id == victim_id))).scalars().all()
    assert links == []


@pytest.mark.asyncio
async def test_instagram_email_step_creates_unverified_account(client, db):
    email = f"new_{_u()}@example.com"
    partial = create_partial_oauth_token("instagram", f"ig-{_u()}", f"insta_{_u()}")
    with patch.object(auth_router, "send_verification_email", new=AsyncMock()) as sent:
        resp = await client.post("/api/auth/oauth/complete",
                                 json={"partial_token": partial, "email": email})
    assert resp.status_code == 200, resp.text
    sent.assert_awaited_once()

    db.expire_all()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert user.email_verified is False


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _fake_provider(userinfo: dict):
    """Stand-in for httpx.AsyncClient during the OAuth code exchange."""
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):
            return _FakeResp({"access_token": "provider-token"})

        async def get(self, *a, **kw):
            return _FakeResp(userinfo)

    return _Client


@pytest.mark.asyncio
async def test_google_unverified_email_cannot_link_to_existing_account(client, db):
    victim_email = f"victim_{_u()}@example.com"
    await _make_user(db, email=victim_email)
    userinfo = {"sub": f"g-{_u()}", "email": victim_email, "email_verified": False, "name": "Mallory"}
    with patch.object(auth_router.httpx, "AsyncClient", _fake_provider(userinfo)):
        resp = await client.get("/api/auth/oauth/google/callback?code=abc")
    assert resp.status_code == 400
    assert not resp.json().get("access_token")


@pytest.mark.asyncio
async def test_google_verified_email_still_logs_in(client, db):
    email = f"g_{_u()}@example.com"
    userinfo = {"sub": f"g-{_u()}", "email": email, "email_verified": True, "name": "Real User"}
    with patch.object(auth_router.httpx, "AsyncClient", _fake_provider(userinfo)):
        resp = await client.get("/api/auth/oauth/google/callback?code=abc")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_disabled_account_cannot_log_in_through_oauth(client, db):
    _, uid = await _make_user(db, is_active=False)
    sub = f"g-{_u()}"
    db.add(OAuthAccount(user_id=uid, provider="google", provider_user_id=sub))
    await db.commit()
    with patch.object(auth_router.httpx, "AsyncClient", _fake_provider({"sub": sub})):
        resp = await client.get("/api/auth/oauth/google/callback?code=abc")
    assert resp.status_code == 403


# ── 2. Payment amount ─────────────────────────────────────────────────────────

async def _paid_checkout(client, db, price: float) -> tuple[dict, str, str]:
    headers, _ = await _make_user(db)
    _, host_id = await _make_user(db, "organizer")
    event_id = await _make_event(db, host_id)
    tier_id = await _make_tier(db, event_id, price)
    with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value={})):
        resp = await client.post(f"/api/events/{event_id}/tickets/checkout",
                                 json={"items": [{"tier_id": tier_id, "quantity": 1}]}, headers=headers)
    assert resp.status_code == 200, resp.text
    return headers, event_id, resp.json()["payment_reference"]


async def _order_status(db, reference: str) -> str:
    db.expire_all()
    return (await db.execute(select(TicketOrder.status).where(
        TicketOrder.payment_reference == reference))).scalar_one()


@pytest.mark.asyncio
async def test_underpayment_is_not_confirmed(client, db):
    headers, event_id, ref = await _paid_checkout(client, db, price=50000.0)
    paid_one_naira = {"status": True, "data": {"status": "success", "amount": 100, "currency": "NGN"}}
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=paid_one_naira)):
        resp = await client.post(f"/api/events/{event_id}/tickets/verify-payment",
                                 json={"reference": ref}, headers=headers)
    assert resp.status_code == 402
    assert await _order_status(db, ref) == "pending"


@pytest.mark.asyncio
async def test_wrong_currency_is_not_confirmed(client, db):
    headers, event_id, ref = await _paid_checkout(client, db, price=100.0)
    usd = {"status": True, "data": {"status": "success", "amount": 10000, "currency": "USD"}}
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=usd)):
        resp = await client.post(f"/api/events/{event_id}/tickets/verify-payment",
                                 json={"reference": ref}, headers=headers)
    assert resp.status_code == 402
    assert await _order_status(db, ref) == "pending"


@pytest.mark.asyncio
async def test_exact_payment_is_confirmed(client, db):
    headers, event_id, ref = await _paid_checkout(client, db, price=19.99)  # float-rounding case
    exact = {"status": True, "data": {"status": "success", "amount": 1999, "currency": "NGN"}}
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=exact)):
        resp = await client.post(f"/api/events/{event_id}/tickets/verify-payment",
                                 json={"reference": ref}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert await _order_status(db, ref) == "confirmed"


@pytest.mark.asyncio
async def test_webhook_ignores_underpayment(client, db):
    import hashlib
    import hmac
    with patch.object(settings, "paystack_secret_key", "test_secret"):
        _, _, ref = await _paid_checkout(client, db, price=5000.0)
        body = json.dumps({"event": "charge.success", "data": {
            "reference": ref, "amount": 100, "currency": "NGN"}}).encode()
        sig = hmac.new(b"test_secret", body, hashlib.sha512).hexdigest()
        resp = await client.post("/api/events/webhooks/paystack", content=body,
                                 headers={"x-paystack-signature": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "amount_mismatch"
    assert await _order_status(db, ref) == "pending"


def test_to_kobo_rounds_instead_of_truncating():
    assert tickets.to_kobo(19.99) == 1999
    assert tickets.to_kobo(0.29) == 29


# ── 3. URL validation (XSS) ───────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>", "vbscript:x", "https://", "http://exa mple.com",
])
def test_normalize_web_url_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        normalize_web_url(bad)


def test_normalize_web_url_accepts_and_normalizes():
    assert normalize_web_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert normalize_web_url("mysite.com") == "https://mysite.com"
    assert normalize_web_url("") == ""
    assert safe_web_url_or_none("javascript:alert(1)") is None


@pytest.mark.asyncio
async def test_profile_website_rejects_javascript_url(client, db):
    headers, _ = await _make_user(db)
    resp = await client.patch("/api/auth/me", json={"website": "javascript:alert(document.cookie)"},
                              headers=headers)
    assert resp.status_code == 422
    ok = await client.patch("/api/auth/me", json={"website": "mysite.com"}, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["website"] == "https://mysite.com"


@pytest.mark.asyncio
async def test_community_social_link_rejects_javascript_url(client, db):
    headers, _ = await _make_user(db)
    resp = await client.post("/api/communities", headers=headers, json={
        "name": f"Club {_u()}", "description": "A community for testing links",
        "social_links": {"website": "javascript:alert(1)"},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_event_template_cannot_smuggle_unsafe_url(client, db):
    headers, host_id = await _make_user(db, "admin")
    tid = str(uuid.uuid4())
    db.add(EventTemplate(id=tid, organizer_id=host_id, name="t",
                         template_data=json.dumps({"meeting_url": "javascript:alert(1)"})))
    await db.commit()
    now = datetime.now(timezone.utc)
    resp = await client.post("/api/events", headers=headers, json={
        "title": "Template event", "description": "x" * 30, "venue_name": "Venue",
        "address": "1 Test Street", "city": "Lagos", "template_id": tid,
        "start_date": (now + timedelta(days=3)).isoformat(),
        "end_date": (now + timedelta(days=3, hours=2)).isoformat(),
    })
    assert resp.status_code == 422


# ── 4. Phone OTP attempts ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_otp_attempt_limit_survives_failed_requests(client, db):
    phone = "+23480" + str(uuid.uuid4().int)[:8]
    with patch.object(auth_router, "send_otp_sms", new=AsyncMock()):
        assert (await client.post("/api/auth/phone/send-otp", json={"phone_number": phone})).status_code == 200

    db.expire_all()
    real_code = (await db.execute(select(PhoneOTP.otp_code).where(PhoneOTP.phone_number == phone))).scalar_one()
    wrong = "000000" if real_code != "000000" else "111111"

    for _ in range(3):
        r = await client.post("/api/auth/phone/verify", json={"phone_number": phone, "otp_code": wrong})
        assert r.status_code == 400

    db.expire_all()
    assert (await db.execute(select(PhoneOTP.attempts).where(PhoneOTP.phone_number == phone))).scalar_one() == 3

    # 4th attempt is refused even with the right code: the limit is real now.
    r = await client.post("/api/auth/phone/verify", json={"phone_number": phone, "otp_code": real_code})
    assert r.status_code == 400
    assert "access_token" not in r.json()


# ── 5. Refunds go through Paystack ────────────────────────────────────────────

async def _confirmed_paid_order(db, price: float) -> tuple[str, str, str]:
    _, buyer_id = await _make_user(db)
    _, host_id = await _make_user(db, "organizer")
    event_id = await _make_event(db, host_id)
    tier_id = await _make_tier(db, event_id, price)
    tier = (await db.execute(select(TicketTier).where(TicketTier.id == tier_id))).scalar_one()
    await tickets.reserve_inventory(db, tier, 1)
    order_id, ref = str(uuid.uuid4()), f"turnup-{_u()}"
    db.add(TicketOrder(id=order_id, user_id=buyer_id, event_id=event_id, tier_id=tier_id,
                       quantity=1, unit_price=price, total_price=price, status="pending",
                       payment_reference=ref))
    await db.flush()
    await tickets.confirm_order(db, order_id, payment_channel="card")
    await db.commit()
    return order_id, ref, tier_id


@pytest.mark.asyncio
async def test_refund_calls_paystack_for_the_order_amount(client, db):
    admin_headers, _ = await _make_user(db, "admin")
    order_id, ref, _ = await _confirmed_paid_order(db, price=2500.5)
    with patch.object(paystack, "refund_transaction", new=AsyncMock(return_value={"status": True})) as refund:
        resp = await client.post(f"/api/admin/orders/{order_id}/refund", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    refund.assert_awaited_once_with(ref, 250050)


@pytest.mark.asyncio
async def test_failed_paystack_refund_leaves_order_confirmed(client, db):
    admin_headers, _ = await _make_user(db, "admin")
    order_id, _, tier_id = await _confirmed_paid_order(db, price=1000.0)
    with patch.object(paystack, "refund_transaction", new=AsyncMock(side_effect=RuntimeError("declined"))):
        resp = await client.post(f"/api/admin/orders/{order_id}/refund", headers=admin_headers)
    assert resp.status_code == 502

    db.expire_all()
    status = (await db.execute(select(TicketOrder.status).where(TicketOrder.id == order_id))).scalar_one()
    sold = (await db.execute(select(TicketTier.quantity_sold).where(TicketTier.id == tier_id))).scalar_one()
    assert status == "confirmed"
    assert sold == 1


@pytest.mark.asyncio
async def test_refund_refuses_to_fake_outside_debug(db):
    order_id, ref, _ = await _confirmed_paid_order(db, price=1000.0)
    with patch.object(settings, "debug", False), patch.object(settings, "paystack_secret_key", ""):
        with pytest.raises(paystack.PaystackConfigError):
            await paystack.refund_transaction(ref, 100000)
