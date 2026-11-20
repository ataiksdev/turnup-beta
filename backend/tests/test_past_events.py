"""A past event can still be opened (e.g. from an organizer's profile), but nobody can buy its
tickets, join its waitlist or RSVP to it."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.event import Event
from app.models.organizer import TicketTier
from tests.test_venues import make_user


async def _event(db, *, start: timedelta, end: timedelta, price=5000):
    _, host = await make_user(db, "organizer")
    eid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title="Past Or Present Party", description="d" * 30,
                 venue_name="Hall", address="1 Test Street", city="Lagos", country="NG",
                 start_date=now + start, end_date=now + end, host_id=host, status="published",
                 review_status="approved", is_free=price == 0, waitlist_enabled=True))
    db.add(TicketTier(id=tid, event_id=eid, name="Regular", price=price, max_per_order=5, is_active=True))
    await db.commit()
    return eid, tid


async def test_tickets_for_an_ended_event_cant_be_bought(client, db):
    h, _ = await make_user(db)
    for price in (5000, 0):  # paid and free tiers alike
        eid, tid = await _event(db, start=-timedelta(days=3), end=-timedelta(days=3) + timedelta(hours=4), price=price)
        r = await client.post(f"/api/events/{eid}/tickets/checkout", headers=h,
                              json={"items": [{"tier_id": tid, "quantity": 1}]})
        assert r.status_code == 400 and "ended" in r.json()["detail"]
        # The event page itself still opens.
        assert (await client.get(f"/api/events/{eid}")).status_code == 200


async def test_tickets_stay_on_sale_until_the_event_ends(client, db):
    h, _ = await make_user(db)
    eid, tid = await _event(db, start=-timedelta(hours=1), end=timedelta(hours=3), price=0)
    r = await client.post(f"/api/events/{eid}/tickets/checkout", headers=h,
                          json={"items": [{"tier_id": tid, "quantity": 1}]})
    assert r.status_code == 200, r.text


async def test_no_waitlist_or_rsvp_after_the_event(client, db):
    h, _ = await make_user(db)
    eid, _ = await _event(db, start=-timedelta(days=2), end=-timedelta(days=2) + timedelta(hours=4), price=0)
    assert (await client.post(f"/api/events/{eid}/waitlist", headers=h)).status_code == 400
    for status in ("going", "interested"):
        r = await client.post(f"/api/events/{eid}/attend", headers=h, json={"status": status})
        assert r.status_code == 400 and "ended" in r.json()["detail"]
