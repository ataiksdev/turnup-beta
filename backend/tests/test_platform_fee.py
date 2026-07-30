"""Tests for the admin-adjustable ticket platform fee: snapshot semantics at confirm time,
the admin settings endpoint, and its effect on organizer dashboard / admin stats reporting.

Note: conftest's `engine`/`db` fixtures are session-scoped (data persists across tests in this
file), so every test uses unique event/tier names and scopes its assertions to rows it created
itself, rather than asserting on whole-table counts (same convention as the other test files).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from app.models.user import User
from app.services import settings as settings_service
from app.services import tickets
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


async def _make_event(db, host_id: str) -> str:
    unique = _unique()
    start = datetime.now(timezone.utc) + timedelta(days=5)
    event = Event(
        id=str(uuid.uuid4()), slug=f"event-{unique}", title=f"Test Event {unique}",
        description="A test event.", venue_name="Test Venue", address="1 Test St",
        city="Lagos", country="Nigeria", start_date=start, end_date=start + timedelta(hours=3),
        host_id=host_id, status="published", review_status="approved",
    )
    db.add(event)
    await db.commit()
    return event.id


async def _make_tier(db, event_id: str, price: float) -> str:
    tier = TicketTier(
        id=str(uuid.uuid4()), event_id=event_id, name=f"Tier {_unique()}",
        price=price, quantity=None, max_per_order=10, is_active=True,
    )
    db.add(tier)
    await db.commit()
    return tier.id


async def _confirmed_order(db, event_id: str, tier_id: str, buyer_id: str, price: float) -> str:
    tier = (await db.execute(select(TicketTier).where(TicketTier.id == tier_id))).scalar_one()
    await tickets.reserve_inventory(db, tier, 1)
    order_id = str(uuid.uuid4())
    db.add(TicketOrder(
        id=order_id, user_id=buyer_id, event_id=event_id, tier_id=tier_id,
        quantity=1, unit_price=price, total_price=price, status="pending",
        payment_reference=f"turnup-{_unique()}",
    ))
    await db.flush()
    await tickets.confirm_order(db, order_id, payment_channel="card")
    await db.commit()
    return order_id


# ── Fee snapshot semantics ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_order_snapshots_current_fee_percent(db, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    _, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=1000.0)

    await settings_service.set_ticket_fee_percent(db, 10.0)
    order_id = await _confirmed_order(db, event_id, tier_id, buyer_id, price=1000.0)

    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()
    assert order.platform_fee_percent == 10.0
    assert order.platform_fee_amount == 100.0


@pytest.mark.asyncio
async def test_confirm_order_free_ticket_has_zero_fee(db, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    _, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=0.0)

    await settings_service.set_ticket_fee_percent(db, 10.0)
    order_id = await _confirmed_order(db, event_id, tier_id, buyer_id, price=0.0)

    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()
    assert order.platform_fee_percent == 0.0
    assert order.platform_fee_amount == 0.0


@pytest.mark.asyncio
async def test_changing_fee_rate_does_not_affect_already_confirmed_orders(db, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    _, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=2000.0)

    await settings_service.set_ticket_fee_percent(db, 5.0)
    order_a = await _confirmed_order(db, event_id, tier_id, buyer_id, price=2000.0)

    await settings_service.set_ticket_fee_percent(db, 20.0)
    order_b = await _confirmed_order(db, event_id, tier_id, buyer_id, price=2000.0)

    db.expire_all()
    a = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_a))).scalar_one()
    b = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_b))).scalar_one()
    assert a.platform_fee_percent == 5.0
    assert a.platform_fee_amount == 100.0
    assert b.platform_fee_percent == 20.0
    assert b.platform_fee_amount == 400.0


# ── Admin settings endpoint ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_get_and_update_platform_fee(client, admin_auth):
    headers, _ = admin_auth

    get_resp = await client.get("/api/admin/settings/platform-fee", headers=headers)
    assert get_resp.status_code == 200

    patch_resp = await client.patch(
        "/api/admin/settings/platform-fee", json={"ticket_fee_percent": 7.5}, headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["ticket_fee_percent"] == 7.5

    get_resp2 = await client.get("/api/admin/settings/platform-fee", headers=headers)
    assert get_resp2.json()["ticket_fee_percent"] == 7.5


@pytest.mark.asyncio
async def test_platform_fee_update_requires_admin(client, organizer_auth):
    headers, _ = organizer_auth
    resp = await client.patch(
        "/api/admin/settings/platform-fee", json={"ticket_fee_percent": 7.5}, headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_fee_update_validates_range(client, admin_auth):
    headers, _ = admin_auth
    resp = await client.patch(
        "/api/admin/settings/platform-fee", json={"ticket_fee_percent": 150}, headers=headers,
    )
    assert resp.status_code == 422
    resp2 = await client.patch(
        "/api/admin/settings/platform-fee", json={"ticket_fee_percent": -1}, headers=headers,
    )
    assert resp2.status_code == 422


# ── Reporting ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_stats_includes_platform_fee_revenue(client, db, admin_auth, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    _, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=1000.0)

    await settings_service.set_ticket_fee_percent(db, 10.0)
    order_id = await _confirmed_order(db, event_id, tier_id, buyer_id, price=1000.0)

    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == order_id))).scalar_one()
    expected_fee = order.platform_fee_amount

    resp = await client.get("/api/admin/stats", headers=admin_auth[0])
    assert resp.status_code == 200
    # Session-scoped DB: other tests' confirmed orders contribute too, so assert this
    # order's fee is actually counted rather than asserting an exact total.
    assert resp.json()["platform_fee_revenue"] >= expected_fee


@pytest.mark.asyncio
async def test_organizer_dashboard_shows_gross_fee_net(client, db, organizer_auth, buyer_auth):
    headers, organizer_id = organizer_auth
    _, buyer_id = buyer_auth
    event_id = await _make_event(db, organizer_id)
    tier_id = await _make_tier(db, event_id, price=5000.0)

    await settings_service.set_ticket_fee_percent(db, 8.0)
    await _confirmed_order(db, event_id, tier_id, buyer_id, price=5000.0)

    resp = await client.get("/api/organizer/dashboard", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_revenue"] == 5000.0
    assert body["platform_fee_total"] == 400.0
    assert body["net_revenue"] == 4600.0
