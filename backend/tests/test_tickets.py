"""Tests for the cart-checkout ticket purchase flow: reservation/oversell safety, Paystack
webhook reconciliation, idempotency, refunds, expiry sweep, and the fail-closed mock guard.

Note: conftest's `engine`/`db` fixtures are session-scoped (data persists across tests in this
file), so every test uses unique event/tier titles and scopes its assertions to rows it created
itself, rather than asserting on whole-table counts (same convention as test_scout_agent.py).

Gotcha specific to this file: HTTP calls through the `client` fixture run in a *different*
DB session than the `db` fixture (though over the same underlying connection), so `db`'s
identity map can hold stale copies of rows a request just mutated. We capture plain id/value
variables (strings, floats) up front and call `db.expire_all()` before re-querying by id --
but never touch attributes on the original ORM objects (e.g. `tier.id`) after that, since an
expired attribute access outside an awaited call raises MissingGreenlet.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.models.auth_tokens import UserSession
from app.models.event import Event, EventAttendee
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification
from app.models.user import User
from app.routers import events as events_router
from app.services import paystack, tickets
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


@pytest_asyncio.fixture
async def buyer_auth(db):
    return await _make_auth(db, "attendee")


@pytest_asyncio.fixture
async def organizer_auth(db):
    return await _make_auth(db, "organizer")


@pytest_asyncio.fixture
async def admin_auth(db):
    return await _make_auth(db, "admin")


async def _make_event(db, host_id: str, **overrides) -> str:
    """Returns the new event's id (a plain string, safe to use after expire_all())."""
    unique = _unique()
    start = datetime.now(timezone.utc) + timedelta(days=5)
    event = Event(
        id=str(uuid.uuid4()), slug=f"event-{unique}", title=f"Test Event {unique}",
        description="A test event.", venue_name="Test Venue", address="1 Test St",
        city="Lagos", country="Nigeria", start_date=start, end_date=start + timedelta(hours=3),
        host_id=host_id, status="published", review_status="approved",
        **overrides,
    )
    db.add(event)
    await db.commit()
    return event.id


async def _make_tier(db, event_id: str, price: float = 0.0, quantity: int | None = None, **overrides) -> str:
    """Returns the new tier's id (a plain string, safe to use after expire_all())."""
    tier = TicketTier(
        id=str(uuid.uuid4()), event_id=event_id, name=f"Tier {_unique()}",
        price=price, quantity=quantity, max_per_order=10, is_active=True,
        **overrides,
    )
    db.add(tier)
    await db.commit()
    return tier.id


async def _tier_quantity_sold(db, tier_id: str) -> int:
    db.expire_all()
    return (await db.execute(select(TicketTier).where(TicketTier.id == tier_id))).scalar_one().quantity_sold


# ── Checkout: free tiers ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_single_free_tier_confirms_immediately(db, client, buyer_auth, organizer_auth):
    headers, buyer_id = buyer_auth
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=0.0, quantity=5)

    resp = await client.post(
        f"/api/events/{event_id}/tickets/checkout",
        json={"items": [{"tier_id": tier_id, "quantity": 2}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_free"] is True
    assert len(body["order_ids"]) == 1
    order_id = body["order_ids"][0]

    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()
    assert order.status == "confirmed"
    assert order.ticket_code is not None
    assert order.quantity == 2

    assert await _tier_quantity_sold(db, tier_id) == 2

    attendee = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == event_id, EventAttendee.user_id == buyer_id,
    ))).scalar_one_or_none()
    assert attendee is not None

    notif = (await db.execute(select(Notification).where(
        Notification.reference_id == order_id, Notification.type == "ticket_confirmed",
    ))).scalar_one_or_none()
    assert notif is not None


# ── Checkout: multi-tier paid cart ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_multi_tier_cart_paid_then_verify(db, client, buyer_auth, organizer_auth):
    headers, buyer_id = buyer_auth
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_a_id = await _make_tier(db, event_id, price=1000.0, quantity=10)
    tier_b_id = await _make_tier(db, event_id, price=2500.0, quantity=10)

    fake_init = {"status": True, "data": {"reference": "x", "authorization_url": "y"}}
    with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value=fake_init)):
        resp = await client.post(
            f"/api/events/{event_id}/tickets/checkout",
            json={"items": [
                {"tier_id": tier_a_id, "quantity": 2},
                {"tier_id": tier_b_id, "quantity": 1},
            ]},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_free"] is False
    assert len(body["order_ids"]) == 2
    assert body["amount_kobo"] == int((1000 * 2 + 2500 * 1) * 100)
    reference = body["payment_reference"]

    db.expire_all()
    orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == reference))).scalars().all()
    assert len(orders) == 2
    assert all(o.status == "pending" for o in orders)

    fake_verify = {"status": True, "data": {"status": "success", "channel": "card"}}
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=fake_verify)):
        verify_resp = await client.post(
            f"/api/events/{event_id}/tickets/verify-payment",
            json={"reference": reference},
            headers=headers,
        )
    assert verify_resp.status_code == 200, verify_resp.text
    confirmed = verify_resp.json()
    assert len(confirmed) == 2
    assert all(o["status"] == "confirmed" and o["ticket_code"] for o in confirmed)

    assert await _tier_quantity_sold(db, tier_a_id) == 2
    assert await _tier_quantity_sold(db, tier_b_id) == 1


# ── Oversell race ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_oversell_race(db, client, organizer_auth):
    """Regression guard for the reservation-at-purchase-time fix: before it, availability was
    only checked (not reserved) at purchase time and only incremented at confirm time, so two
    requests for the last unit could both pass the check. Issued sequentially rather than via
    true asyncio concurrency -- the test harness's in-memory SQLite DB is a single shared
    connection (StaticPool), which cannot run two independent transactions at once, so a real
    concurrent race here would hit a test-harness artifact rather than exercise the app logic.
    The atomic conditional UPDATE this guards is what makes it correct under real concurrent
    connections (Postgres row locks, or SQLite's connection-level serialization) in production."""
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=0.0, quantity=1)

    buyer1, _ = await _make_auth(db, "attendee")
    buyer2, _ = await _make_auth(db, "attendee")

    resp1 = await client.post(f"/api/events/{event_id}/tickets/checkout",
                               json={"items": [{"tier_id": tier_id, "quantity": 1}]}, headers=buyer1)
    resp2 = await client.post(f"/api/events/{event_id}/tickets/checkout",
                               json={"items": [{"tier_id": tier_id, "quantity": 1}]}, headers=buyer2)
    statuses = sorted(r.status_code for r in [resp1, resp2])
    assert statuses == [200, 409], [r.text for r in results]

    assert await _tier_quantity_sold(db, tier_id) == 1


# ── Webhook ──────────────────────────────────────────────────────────────────────

def _sign(body: bytes) -> str:
    return hmac.new(b"test_secret", body, hashlib.sha512).hexdigest()


@pytest.mark.asyncio
async def test_webhook_reconciles_pending_order_and_is_idempotent(db, client, buyer_auth, organizer_auth):
    headers, buyer_id = buyer_auth
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=500.0, quantity=5)

    with patch.object(settings, "paystack_secret_key", "test_secret"):
        fake_init = {"status": True, "data": {"reference": "x"}}
        with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value=fake_init)):
            checkout_resp = await client.post(
                f"/api/events/{event_id}/tickets/checkout",
                json={"items": [{"tier_id": tier_id, "quantity": 1}]},
                headers=headers,
            )
        reference = checkout_resp.json()["payment_reference"]

        body = json.dumps({"event": "charge.success", "data": {"reference": reference, "channel": "card"}}).encode()
        sig = _sign(body)

        resp1 = await client.post(
            "/api/events/webhooks/paystack", content=body,
            headers={"x-paystack-signature": sig, "Content-Type": "application/json"},
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["status"] == "ok"

        db.expire_all()
        order = (await db.execute(select(TicketOrder).where(
            TicketOrder.payment_reference == reference))).scalar_one()
        assert order.status == "confirmed"
        order_id = order.id

        notif_count_1 = len((await db.execute(select(Notification).where(
            Notification.reference_id == order_id))).scalars().all())
        assert notif_count_1 == 1

        # Duplicate delivery (Paystack's at-least-once semantics) is a no-op.
        resp2 = await client.post(
            "/api/events/webhooks/paystack", content=body,
            headers={"x-paystack-signature": sig, "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200

        db.expire_all()
        notif_count_2 = len((await db.execute(select(Notification).where(
            Notification.reference_id == order_id))).scalars().all())
        assert notif_count_2 == 1


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(db, client, buyer_auth, organizer_auth):
    headers, _ = buyer_auth
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=500.0, quantity=5)

    with patch.object(settings, "paystack_secret_key", "test_secret"):
        fake_init = {"status": True, "data": {"reference": "x"}}
        with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value=fake_init)):
            checkout_resp = await client.post(
                f"/api/events/{event_id}/tickets/checkout",
                json={"items": [{"tier_id": tier_id, "quantity": 1}]},
                headers=headers,
            )
        reference = checkout_resp.json()["payment_reference"]

        body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode()
        resp = await client.post(
            "/api/events/webhooks/paystack", content=body,
            headers={"x-paystack-signature": "wrong-signature", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401

        db.expire_all()
        order = (await db.execute(select(TicketOrder).where(
            TicketOrder.payment_reference == reference))).scalar_one()
        assert order.status == "pending"


# ── Expiry sweep ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expiry_sweep_cancels_stale_pending_orders_and_releases_inventory(db, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    headers, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=500.0, quantity=5)

    tier = (await db.execute(select(TicketTier).where(TicketTier.id == tier_id))).scalar_one()
    await tickets.reserve_inventory(db, tier, 1)
    stale_order_id = str(uuid.uuid4())
    db.add(TicketOrder(
        id=stale_order_id, user_id=buyer_id, event_id=event_id, tier_id=tier_id,
        quantity=1, unit_price=tier.price, total_price=tier.price, status="pending",
        payment_reference=f"turnup-{_unique()}",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    ))
    await db.commit()

    summary = await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert summary.expired >= 1

    db.expire_all()
    refreshed_order = (await db.execute(select(TicketOrder).where(TicketOrder.id == stale_order_id))).scalar_one()
    assert refreshed_order.status == "cancelled"

    assert await _tier_quantity_sold(db, tier_id) == 0


# ── Refunds ──────────────────────────────────────────────────────────────────────

async def _confirmed_order(db, event_id: str, tier_id: str, buyer_id: str) -> str:
    """Returns the new order's id."""
    tier = (await db.execute(select(TicketTier).where(TicketTier.id == tier_id))).scalar_one()
    await tickets.reserve_inventory(db, tier, 1)
    order_id = str(uuid.uuid4())
    db.add(TicketOrder(
        id=order_id, user_id=buyer_id, event_id=event_id, tier_id=tier_id,
        quantity=1, unit_price=tier.price, total_price=tier.price, status="pending",
        payment_reference=f"turnup-{_unique()}",
    ))
    await db.flush()
    await tickets.confirm_order(db, order_id, payment_channel="card")
    await db.commit()
    return order_id


@pytest.mark.asyncio
async def test_admin_refund_releases_inventory_and_notifies(db, client, admin_auth, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    headers, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=1000.0, quantity=5)
    order_id = await _confirmed_order(db, event_id, tier_id, buyer_id)

    resp = await client.post(f"/api/admin/orders/{order_id}/refund", headers=admin_auth[0])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "refunded"

    assert await _tier_quantity_sold(db, tier_id) == 0

    notif = (await db.execute(select(Notification).where(
        Notification.reference_id == order_id, Notification.type == "ticket_refunded",
    ))).scalar_one_or_none()
    assert notif is not None


@pytest.mark.asyncio
async def test_organizer_can_only_refund_own_event_orders(db, client, organizer_auth, buyer_auth):
    other_organizer_auth = await _make_auth(db, "organizer")
    _, organizer_id = organizer_auth
    headers, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=1000.0, quantity=5)
    order_id = await _confirmed_order(db, event_id, tier_id, buyer_id)

    resp = await client.post(f"/api/organizer/orders/{order_id}/refund", headers=other_organizer_auth[0])
    assert resp.status_code == 403

    own_resp = await client.post(f"/api/organizer/orders/{order_id}/refund", headers=organizer_auth[0])
    assert own_resp.status_code == 200, own_resp.text


# ── Idempotency ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_idempotent_duplicate_request(db, client, buyer_auth, organizer_auth):
    headers, _ = buyer_auth
    _, organizer_id = organizer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=0.0, quantity=5)
    key = str(uuid.uuid4())

    resp1 = await client.post(
        f"/api/events/{event_id}/tickets/checkout",
        json={"items": [{"tier_id": tier_id, "quantity": 1}], "idempotency_key": key},
        headers=headers,
    )
    resp2 = await client.post(
        f"/api/events/{event_id}/tickets/checkout",
        json={"items": [{"tier_id": tier_id, "quantity": 1}], "idempotency_key": key},
        headers=headers,
    )
    assert resp1.status_code == 200 and resp2.status_code == 200
    assert resp1.json()["order_ids"] == resp2.json()["order_ids"]

    db.expire_all()
    all_orders = (await db.execute(select(TicketOrder).where(
        TicketOrder.idempotency_key == key))).scalars().all()
    assert len(all_orders) == 1

    assert await _tier_quantity_sold(db, tier_id) == 1


# ── Fail-closed Paystack mock ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paystack_mock_fails_closed_outside_debug():
    with patch.object(settings, "paystack_secret_key", ""), patch.object(settings, "debug", False):
        with pytest.raises(paystack.PaystackConfigError):
            await paystack.initialize_transaction(email="a@b.com", amount_kobo=100, reference="r")
        with pytest.raises(paystack.PaystackConfigError):
            await paystack.verify_transaction("r")


@pytest.mark.asyncio
async def test_paystack_mock_still_works_in_debug_mode():
    with patch.object(settings, "paystack_secret_key", ""), patch.object(settings, "debug", True):
        init_resp = await paystack.initialize_transaction(email="a@b.com", amount_kobo=100, reference="r")
        assert init_resp["status"] is True
        verify_resp = await paystack.verify_transaction("r")
        assert verify_resp["data"]["status"] == "success"
