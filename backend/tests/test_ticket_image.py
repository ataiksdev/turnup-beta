"""The saved ticket image (GET /api/organizer/tickets/{id}/image.png)."""
import io
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image

from app.models.event import Event
from app.models.organizer import TicketOrder, TicketTier
from tests.test_venues import make_user


async def _order(db, user_id, status="confirmed", cover=None):
    _, host = await make_user(db, "organizer")
    eid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title="A Very Long Event Title That Has To Wrap Across Lines On The Ticket",
                 description="d" * 30, venue_name="Hall", address="1 Test Street", city="Lagos", country="NG",
                 start_date=now + timedelta(days=3), end_date=now + timedelta(days=3, hours=4), host_id=host,
                 status="published", review_status="approved", is_free=False, cover_image=cover))
    db.add(TicketTier(id=tid, event_id=eid, name="VIP", price=5000, max_per_order=5, is_active=True))
    oid = str(uuid.uuid4())
    db.add(TicketOrder(id=oid, user_id=user_id, event_id=eid, tier_id=tid, quantity=2, unit_price=5000,
                       total_price=10000, status=status, ticket_code=str(uuid.uuid4()) if status == "confirmed" else None))
    await db.commit()
    return oid


async def test_owner_gets_a_ticket_png(client, db):
    h, uid = await make_user(db)
    # A cover on a private address must not be fetched (SSRF guard); the image still renders.
    oid = await _order(db, uid, cover="http://127.0.0.1:9/cover.jpg")
    r = await client.get(f"/api/organizer/tickets/{oid}/image.png", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (1080, 1920)


async def test_other_users_and_unconfirmed_tickets_refused(client, db):
    h, uid = await make_user(db)
    other_h, _ = await make_user(db)
    oid = await _order(db, uid)
    assert (await client.get(f"/api/organizer/tickets/{oid}/image.png", headers=other_h)).status_code == 404
    pending = await _order(db, uid, status="pending")
    assert (await client.get(f"/api/organizer/tickets/{pending}/image.png", headers=h)).status_code == 409
