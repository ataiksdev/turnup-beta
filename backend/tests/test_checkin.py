"""Door check-in: one person at a time on multi-person tickets, the shared live count, and
two doors scanning the same ticket."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from tests.test_venues import make_user


async def _event(db, host_id, quantities):
    eid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title="Door test", description="d" * 30, venue_name="Hall",
                 address="1 Test Street", city="Lagos", country="NG", start_date=now, end_date=now + timedelta(hours=4),
                 host_id=host_id, status="published", review_status="approved", is_free=True))
    db.add(TicketTier(id=tid, event_id=eid, name="GA", price=0, max_per_order=10, is_active=True))
    codes = []
    for q in quantities:
        _, buyer = await make_user(db)
        code = str(uuid.uuid4())
        db.add(TicketOrder(user_id=buyer, event_id=eid, tier_id=tid, quantity=q, unit_price=0, total_price=0,
                           status="confirmed", ticket_code=code))
        codes.append(code)
    await db.commit()
    return eid, codes


async def test_multi_person_ticket_admits_in_parts(client, db):
    h, host = await make_user(db, "organizer")
    eid, (code,) = await _event(db, host, [3])
    url = f"/api/events/{eid}/checkin"
    r = (await client.post(url, headers=h, json={"ticket_code": code})).json()
    assert r["needs_choice"] and r["admitted_now"] == 0 and r["remaining"] == 3
    r = (await client.post(url, headers=h, json={"ticket_code": code, "admit": 2})).json()
    assert r["admitted_count"] == 2 and r["remaining"] == 1 and not r["needs_choice"]
    # The last person: no choice needed.
    r = (await client.post(url, headers=h, json={"ticket_code": code})).json()
    assert r["admitted_now"] == 1 and r["remaining"] == 0
    r = await client.post(url, headers=h, json={"ticket_code": code})
    assert r.status_code == 409 and "all 3" in r.json()["detail"]
    r = await client.post(url, headers=h, json={"ticket_code": code, "admit": 1})
    assert r.status_code == 409


async def test_cannot_admit_more_than_remaining(client, db):
    h, host = await make_user(db, "organizer")
    eid, (code,) = await _event(db, host, [2])
    await client.post(f"/api/events/{eid}/checkin", headers=h, json={"ticket_code": code, "admit": 1})
    r = await client.post(f"/api/events/{eid}/checkin", headers=h, json={"ticket_code": code, "admit": 2})
    assert r.status_code == 409 and "Only 1" in r.json()["detail"]


async def test_live_door_count(client, db):
    h, host = await make_user(db, "organizer")
    eid, codes = await _event(db, host, [1, 3, 2])
    await client.post(f"/api/events/{eid}/checkin", headers=h, json={"ticket_code": codes[0]})
    await client.post(f"/api/events/{eid}/checkin", headers=h, json={"ticket_code": codes[1], "admit": 2})
    s = (await client.get(f"/api/events/{eid}/checkin/stats", headers=h)).json()
    assert (s["people_in"], s["people_expected"], s["tickets_in"], s["tickets_total"]) == (3, 6, 1, 3)
    assert {(x["admitted"], x["quantity"]) for x in s["recent"]} == {(1, 1), (2, 3)}
    stranger_h, _ = await make_user(db)
    assert (await client.get(f"/api/events/{eid}/checkin/stats", headers=stranger_h)).status_code == 403


async def test_tickets_checked_in_before_partial_admission_count_as_full(client, db):
    h, host = await make_user(db, "organizer")
    eid, (code,) = await _event(db, host, [2])
    from sqlalchemy import update
    await db.execute(update(TicketOrder).where(TicketOrder.ticket_code == code).values(
        checked_in_at=datetime.now(timezone.utc), admitted_count=0))
    await db.commit()
    r = await client.post(f"/api/events/{eid}/checkin", headers=h, json={"ticket_code": code})
    assert r.status_code == 409
    s = (await client.get(f"/api/events/{eid}/checkin/stats", headers=h)).json()
    assert s["people_in"] == 2
