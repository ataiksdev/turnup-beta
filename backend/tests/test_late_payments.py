"""Late payments: a buyer's payment clears AFTER their pending order expired (30 min sweep),
or the browser callback/webhook never arrived at all. Money must never be kept without a
ticket: the order is revived if tickets remain, refunded if they've sold out, and flagged
"needs_refund" for an admin if even the refund call fails.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update

from app.config import settings
from app.models.auth_tokens import UserSession
from app.models.event import Event, EventAttendee
from app.models.organizer import TicketOrder, TicketTier
from app.models.social import Notification
from app.models.user import User
from app.routers import events as events_router
from app.services import paystack, tickets
from app.services.auth import create_access_token


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def _user(db, role="attendee") -> tuple[dict, str]:
    uid, jti, u = str(uuid.uuid4()), str(uuid.uuid4()), _u()
    db.add(User(id=uid, username=f"{role}_{u}", email=f"{role}_{u}@example.com",
                full_name=role.title(), role=role))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}, uid


async def _setup(db, price=3000.0, quantity=1):
    headers, buyer_id = await _user(db)
    _, host_id = await _user(db, "organizer")
    eid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title=f"Late {_u()}", description="d" * 30,
                 venue_name="Venue", address="1 Test Street", city="Lagos", country="NG",
                 start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=3),
                 host_id=host_id, status="published", review_status="approved", is_free=False))
    db.add(TicketTier(id=tid, event_id=eid, name=f"GA {_u()}", price=price,
                      quantity=quantity, max_per_order=10, is_active=True))
    await db.commit()
    return headers, buyer_id, eid, tid


async def _checkout(client, headers, eid, tid) -> str:
    with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value={})):
        r = await client.post(f"/api/events/{eid}/tickets/checkout",
                              json={"items": [{"tier_id": tid, "quantity": 1}]}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["payment_reference"]


async def _age_and_expire(db, reference: str):
    """Backdate the order past the expiry window and run the sweep (no Paystack key in
    tests, so the sweep expires without asking Paystack -- the 'payment still in flight' case)."""
    await db.execute(update(TicketOrder).where(TicketOrder.payment_reference == reference)
                     .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db.commit()
    await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert await _status(db, reference) == "cancelled"


async def _status(db, reference: str) -> str:
    db.expire_all()
    return (await db.execute(select(TicketOrder.status).where(
        TicketOrder.payment_reference == reference))).scalar_one()


async def _sold(db, tid: str) -> int:
    db.expire_all()
    return (await db.execute(select(TicketTier.quantity_sold).where(TicketTier.id == tid))).scalar_one()


def _paid(amount_kobo: int) -> dict:
    return {"status": True, "data": {"status": "success", "amount": amount_kobo,
                                     "currency": "NGN", "channel": "card"}}


async def _verify(client, headers, eid, ref, amount_kobo):
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=_paid(amount_kobo))):
        return await client.post(f"/api/events/{eid}/tickets/verify-payment",
                                 json={"reference": ref}, headers=headers)


@pytest.mark.asyncio
async def test_late_payment_revives_expired_order_when_tickets_remain(client, db):
    headers, buyer_id, eid, tid = await _setup(db)
    ref = await _checkout(client, headers, eid, tid)
    await _age_and_expire(db, ref)
    assert await _sold(db, tid) == 0  # sweep released the reservation

    r = await _verify(client, headers, eid, ref, 300000)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1 and r.json()[0]["ticket_code"]
    assert await _status(db, ref) == "confirmed"
    assert await _sold(db, tid) == 1  # re-reserved
    going = (await db.execute(select(EventAttendee).where(
        EventAttendee.event_id == eid, EventAttendee.user_id == buyer_id))).scalar_one_or_none()
    assert going is not None


@pytest.mark.asyncio
async def test_late_payment_is_refunded_when_tickets_sold_out(client, db):
    headers, buyer_id, eid, tid = await _setup(db, quantity=1)
    ref = await _checkout(client, headers, eid, tid)
    await _age_and_expire(db, ref)

    # Someone else buys the last ticket while the first buyer's payment is still in flight.
    other_headers, _ = await _user(db)
    await _checkout(client, other_headers, eid, tid)

    with patch.object(paystack, "refund_transaction", new=AsyncMock(return_value={"status": True})) as refund:
        r = await _verify(client, headers, eid, ref, 300000)
    assert r.status_code == 200, r.text
    assert r.json() == []  # nothing confirmed; the frontend explains the refund
    refund.assert_awaited_once_with(ref, 300000)
    assert await _status(db, ref) == "refunded"
    assert await _sold(db, tid) == 1  # the other buyer's ticket is untouched

    notif = (await db.execute(select(Notification).where(
        Notification.user_id == buyer_id, Notification.type == "ticket_refunded_unavailable",
    ))).scalar_one_or_none()
    assert notif is not None


@pytest.mark.asyncio
async def test_failed_auto_refund_is_flagged_and_admin_can_retry(client, db):
    headers, _, eid, tid = await _setup(db, quantity=1)
    ref = await _checkout(client, headers, eid, tid)
    await _age_and_expire(db, ref)
    other_headers, _ = await _user(db)
    await _checkout(client, other_headers, eid, tid)

    with patch.object(paystack, "refund_transaction", new=AsyncMock(side_effect=RuntimeError("down"))):
        r = await _verify(client, headers, eid, ref, 300000)
    assert r.status_code == 200
    assert await _status(db, ref) == "needs_refund"

    order_id = (await db.execute(select(TicketOrder.id).where(
        TicketOrder.payment_reference == ref))).scalar_one()
    admin_headers, _ = await _user(db, "admin")
    with patch.object(paystack, "refund_transaction", new=AsyncMock(return_value={"status": True})) as refund:
        resp = await client.post(f"/api/admin/orders/{order_id}/refund", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    refund.assert_awaited_once_with(ref, 300000)
    assert await _status(db, ref) == "refunded"
    assert await _sold(db, tid) == 1  # needs_refund never held inventory, so nothing released


@pytest.mark.asyncio
async def test_webhook_revives_expired_order(client, db):
    headers, _, eid, tid = await _setup(db)
    with patch.object(settings, "paystack_secret_key", "test_secret"):
        ref = await _checkout(client, headers, eid, tid)
        await db.execute(update(TicketOrder).where(TicketOrder.payment_reference == ref)
                         .values(status="cancelled"))
        await tickets.release_inventory(db, tid, 1)
        await db.commit()

        body = json.dumps({"event": "charge.success", "data": {
            "reference": ref, "amount": 300000, "currency": "NGN", "channel": "card"}}).encode()
        sig = hmac.new(b"test_secret", body, hashlib.sha512).hexdigest()
        r = await client.post("/api/events/webhooks/paystack", content=body,
                              headers={"x-paystack-signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert await _status(db, ref) == "confirmed"
    assert await _sold(db, tid) == 1


@pytest.mark.asyncio
async def test_verify_after_webhook_returns_tickets_instead_of_error(client, db):
    headers, _, eid, tid = await _setup(db)
    ref = await _checkout(client, headers, eid, tid)
    first = await _verify(client, headers, eid, ref, 300000)   # stands in for the webhook
    assert first.status_code == 200

    verify_mock = AsyncMock()
    with patch.object(events_router, "verify_transaction", new=verify_mock):
        second = await client.post(f"/api/events/{eid}/tickets/verify-payment",
                                   json={"reference": ref}, headers=headers)
    assert second.status_code == 200, second.text
    assert len(second.json()) == 1
    verify_mock.assert_not_awaited()  # already settled: no second Paystack round-trip


# ── Expiry sweep asks Paystack first ──────────────────────────────────────────

async def _stale_pending(client, db, headers, eid, tid) -> str:
    ref = await _checkout(client, headers, eid, tid)
    await db.execute(update(TicketOrder).where(TicketOrder.payment_reference == ref)
                     .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db.commit()
    return ref


@pytest.mark.asyncio
async def test_sweep_confirms_order_that_was_actually_paid(client, db):
    headers, _, eid, tid = await _setup(db)
    ref = await _stale_pending(client, db, headers, eid, tid)
    with patch.object(settings, "paystack_secret_key", "test_secret"), \
         patch.object(paystack, "verify_transaction", new=AsyncMock(return_value=_paid(300000))), \
         patch("app.services.email.send_ticket_email", new=AsyncMock()):
        summary = await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert summary.recovered >= 1
    assert await _status(db, ref) == "confirmed"


@pytest.mark.asyncio
async def test_sweep_expires_order_paystack_says_was_abandoned(client, db):
    headers, _, eid, tid = await _setup(db)
    ref = await _stale_pending(client, db, headers, eid, tid)
    abandoned = {"status": True, "data": {"status": "abandoned"}}
    with patch.object(settings, "paystack_secret_key", "test_secret"), \
         patch.object(paystack, "verify_transaction", new=AsyncMock(return_value=abandoned)):
        await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert await _status(db, ref) == "cancelled"
    assert await _sold(db, tid) == 0


@pytest.mark.asyncio
async def test_sweep_leaves_order_pending_when_paystack_unreachable(client, db):
    headers, _, eid, tid = await _setup(db)
    ref = await _stale_pending(client, db, headers, eid, tid)
    with patch.object(settings, "paystack_secret_key", "test_secret"), \
         patch.object(paystack, "verify_transaction", new=AsyncMock(side_effect=OSError("timeout"))):
        summary = await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert summary.deferred >= 1
    assert await _status(db, ref) == "pending"
    assert await _sold(db, tid) == 1
