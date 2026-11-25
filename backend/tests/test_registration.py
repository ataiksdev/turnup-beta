"""Promo codes and registration questions: managing them, applying them at checkout and RSVP,
and keeping a code's use count right through payment, expiry and late payment."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update

from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.organizer import PromoCode, RegistrationAnswer, TicketOrder, TicketTier
from app.models.user import User
from app.routers import events as events_router
from app.services import tickets
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


async def _event(db, host_id: str, tiers: list[tuple[float, int | None]]) -> tuple[str, list[str]]:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title=f"Reg {_u()}", description="d" * 30,
                 venue_name="Venue", address="1 Test Street", city="Lagos", country="NG",
                 start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=3),
                 host_id=host_id, status="published", review_status="approved",
                 is_free=not tiers or all(p == 0 for p, _ in tiers)))
    tids = []
    for price, qty in tiers:
        tid = str(uuid.uuid4())
        db.add(TicketTier(id=tid, event_id=eid, name=f"T {_u()}", price=price, quantity=qty,
                          max_per_order=10, is_active=True))
        tids.append(tid)
    await db.commit()
    return eid, tids


async def _checkout(client, headers, eid, items, **extra):
    with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value={})):
        return await client.post(f"/api/events/{eid}/tickets/checkout",
                                 json={"items": items, **extra}, headers=headers)


async def _times_used(db, code_id: str) -> int:
    db.expire_all()
    return (await db.execute(select(PromoCode.times_used).where(PromoCode.id == code_id))).scalar_one()


# ── Promo codes ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_percent_code_discounts_checkout_amount(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(5000.0, 10)])

    r = await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                          json={"code": "early20", "discount_type": "percent", "discount_value": 20})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "EARLY20"

    r = await client.post(f"/api/events/{eid}/tickets/promo-check", headers=buyer_h,
                          json={"code": "Early20", "items": [{"tier_id": tid, "quantity": 2}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"code": "EARLY20", "discount_type": "percent", "discount_value": 20.0,
                        "subtotal": 10000.0, "discount": 2000.0, "total": 8000.0}

    r = await _checkout(client, buyer_h, eid, [{"tier_id": tid, "quantity": 2}], promo_code="early20")
    assert r.status_code == 200, r.text
    assert r.json()["amount_kobo"] == 800_000
    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == r.json()["payment_reference"]))).scalar_one()
    assert (order.unit_price, order.total_price, order.discount_amount) == (5000.0, 8000.0, 2000.0)


@pytest.mark.asyncio
async def test_fixed_amount_code_only_applies_to_chosen_tiers(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    eid, (ga, vip) = await _event(db, host_id, [(2000.0, None), (10000.0, None)])
    r = await client.post(f"/api/events/{eid}/promo-codes", headers=host_h, json={
        "code": "VIPOFF", "discount_type": "amount", "discount_value": 15000, "tier_ids": [vip]})
    assert r.status_code == 201, r.text

    # Not for GA tickets
    r = await client.post(f"/api/events/{eid}/tickets/promo-check", headers=buyer_h,
                          json={"code": "VIPOFF", "items": [{"tier_id": ga, "quantity": 1}]})
    assert r.status_code == 400

    # Capped at the VIP subtotal; GA still paid in full
    r = await _checkout(client, buyer_h, eid, [{"tier_id": ga, "quantity": 1}, {"tier_id": vip, "quantity": 1}],
                        promo_code="VIPOFF")
    assert r.status_code == 200, r.text
    assert r.json()["amount_kobo"] == 200_000


@pytest.mark.asyncio
async def test_full_discount_confirms_without_payment(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(3000.0, 5)])
    await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                      json={"code": "COMP", "discount_type": "percent", "discount_value": 100})
    r = await _checkout(client, buyer_h, eid, [{"tier_id": tid, "quantity": 1}], promo_code="COMP")
    assert r.status_code == 200, r.text
    assert r.json()["is_free"] is True
    db.expire_all()
    order = (await db.execute(select(TicketOrder).where(
        TicketOrder.payment_reference == r.json()["payment_reference"]))).scalar_one()
    assert order.status == "confirmed" and order.total_price == 0 and order.platform_fee_amount == 0


@pytest.mark.asyncio
async def test_invalid_expired_and_used_up_codes_are_refused(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    other_h, _ = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(1000.0, 50)])
    items = [{"tier_id": tid, "quantity": 1}]

    r = await _checkout(client, buyer_h, eid, items, promo_code="NOPE")
    assert r.status_code == 400 and "isn't valid" in r.json()["detail"]

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                      json={"code": "OLD", "discount_value": 10, "valid_until": past})
    r = await _checkout(client, buyer_h, eid, items, promo_code="OLD")
    assert r.status_code == 400 and "expired" in r.json()["detail"]

    await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                      json={"code": "ONCE", "discount_value": 10, "max_uses": 1})
    assert (await _checkout(client, buyer_h, eid, items, promo_code="ONCE")).status_code == 200
    r = await _checkout(client, other_h, eid, items, promo_code="ONCE")
    assert r.status_code == 400 and "fully used" in r.json()["detail"]

    # Nothing was reserved by the refused checkouts
    db.expire_all()
    sold = (await db.execute(select(TicketTier.quantity_sold).where(TicketTier.id == tid))).scalar_one()
    assert sold == 1


@pytest.mark.asyncio
async def test_expired_cart_gives_use_back_and_late_payment_retakes_it(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(1000.0, None)])
    r = await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                          json={"code": "HALF", "discount_value": 50, "max_uses": 1})
    code_id = r.json()["id"]
    r = await _checkout(client, buyer_h, eid, [{"tier_id": tid, "quantity": 1}], promo_code="HALF")
    ref = r.json()["payment_reference"]
    assert await _times_used(db, code_id) == 1

    await db.execute(update(TicketOrder).where(TicketOrder.payment_reference == ref)
                     .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db.commit()
    await tickets.run_expire_pending_orders(db, older_than_minutes=30)
    assert await _times_used(db, code_id) == 0

    paid = {"status": True, "data": {"status": "success", "amount": 50_000, "currency": "NGN", "channel": "card"}}
    with patch.object(events_router, "verify_transaction", new=AsyncMock(return_value=paid)):
        r = await client.post(f"/api/events/{eid}/tickets/verify-payment", json={"reference": ref}, headers=buyer_h)
    assert r.status_code == 200 and len(r.json()) == 1
    assert await _times_used(db, code_id) == 1


@pytest.mark.asyncio
async def test_promo_codes_are_organizer_only_and_used_codes_cannot_be_deleted(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, _ = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(1000.0, None)])
    assert (await client.post(f"/api/events/{eid}/promo-codes", headers=buyer_h,
                              json={"code": "MINE", "discount_value": 10})).status_code == 403
    assert (await client.get(f"/api/events/{eid}/promo-codes", headers=buyer_h)).status_code == 403
    code_id = (await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                                 json={"code": "USED", "discount_value": 10})).json()["id"]
    assert (await client.post(f"/api/events/{eid}/promo-codes", headers=host_h,
                              json={"code": "used", "discount_value": 5})).status_code == 409
    await _checkout(client, buyer_h, eid, [{"tier_id": tid, "quantity": 1}], promo_code="USED")
    assert (await client.delete(f"/api/events/{eid}/promo-codes/{code_id}", headers=host_h)).status_code == 409
    r = await client.patch(f"/api/events/{eid}/promo-codes/{code_id}", headers=host_h, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


# ── Registration questions ────────────────────────────────────────────────────────

async def _questions(client, host_h, eid):
    r1 = await client.post(f"/api/events/{eid}/questions", headers=host_h,
                           json={"label": "Company", "kind": "text", "required": True})
    r2 = await client.post(f"/api/events/{eid}/questions", headers=host_h, json={
        "label": "Diet", "kind": "multi_choice", "options": ["Vegan", "Halal", "None"]})
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    return r1.json()["id"], r2.json()["id"]


@pytest.mark.asyncio
async def test_checkout_requires_and_stores_answers(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, buyer_id = await _user(db)
    eid, (tid,) = await _event(db, host_id, [(0.0, None)])
    company, diet = await _questions(client, host_h, eid)

    public = (await client.get(f"/api/events/{eid}/questions")).json()
    assert [q["label"] for q in public] == ["Company", "Diet"]

    items = [{"tier_id": tid, "quantity": 1}]
    r = await _checkout(client, buyer_h, eid, items)
    assert r.status_code == 422 and "Company" in r.json()["detail"]
    r = await _checkout(client, buyer_h, eid, items, answers={company: "Acme", diet: ["Pizza"]})
    assert r.status_code == 422  # not one of the choices

    r = await _checkout(client, buyer_h, eid, items, answers={company: " Acme ", diet: ["Vegan", "Halal"]})
    assert r.status_code == 200, r.text

    # Buying again later: the required question was already answered
    assert (await _checkout(client, buyer_h, eid, items)).status_code == 200

    reg = (await client.get(f"/api/events/{eid}/registrations", headers=host_h)).json()
    row = next(x for x in reg["rows"] if x["user_id"] == buyer_id)
    assert row["status"] == "ticket"
    assert row["answers"] == {company: "Acme", diet: "Vegan, Halal"}
    assert (await client.get(f"/api/events/{eid}/registrations", headers=buyer_h)).status_code == 403


@pytest.mark.asyncio
async def test_rsvp_going_asks_questions_but_interested_does_not(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, buyer_id = await _user(db)
    eid, _ = await _event(db, host_id, [])
    company, _diet = await _questions(client, host_h, eid)

    assert (await client.post(f"/api/events/{eid}/attend", headers=buyer_h,
                              json={"status": "interested"})).status_code == 200
    r = await client.post(f"/api/events/{eid}/attend", headers=buyer_h, json={"status": "going"})
    assert r.status_code == 422
    r = await client.post(f"/api/events/{eid}/attend", headers=buyer_h,
                          json={"status": "going", "answers": {company: "Turnup"}})
    assert r.status_code == 200, r.text
    db.expire_all()
    ans = (await db.execute(select(RegistrationAnswer.answer).where(
        RegistrationAnswer.user_id == buyer_id, RegistrationAnswer.question_id == company))).scalar_one()
    assert ans == "Turnup"


@pytest.mark.asyncio
async def test_deleting_an_answered_question_keeps_the_answers(client, db):
    host_h, host_id = await _user(db, "organizer")
    buyer_h, buyer_id = await _user(db)
    eid, _ = await _event(db, host_id, [])
    company, diet = await _questions(client, host_h, eid)
    await client.post(f"/api/events/{eid}/attend", headers=buyer_h,
                      json={"status": "going", "answers": {company: "Acme"}})

    assert (await client.delete(f"/api/events/{eid}/questions/{company}", headers=host_h)).status_code == 204
    assert (await client.delete(f"/api/events/{eid}/questions/{diet}", headers=host_h)).status_code == 204
    assert (await client.get(f"/api/events/{eid}/questions")).json() == []
    reg = (await client.get(f"/api/events/{eid}/registrations", headers=host_h)).json()
    assert [q["id"] for q in reg["questions"]] == [company]
    assert next(x for x in reg["rows"] if x["user_id"] == buyer_id)["answers"] == {company: "Acme"}


@pytest.mark.asyncio
async def test_choice_questions_need_options(client, db):
    host_h, host_id = await _user(db, "organizer")
    eid, _ = await _event(db, host_id, [])
    r = await client.post(f"/api/events/{eid}/questions", headers=host_h,
                          json={"label": "Pick", "kind": "single_choice", "options": ["Only one"]})
    assert r.status_code == 400
