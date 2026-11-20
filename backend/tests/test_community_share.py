"""Sharing an event to a community: members only, once per community, upcoming events only,
and the share sheet can tell which of my communities already have the event."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.event import Event
from tests.test_venues import make_user


async def _event(db, days: int) -> str:
    _, host = await make_user(db, "organizer")
    eid, now = str(uuid.uuid4()), datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title="Shareable Party", description="d" * 30, venue_name="Hall",
                 address="1 Test Street", city="Lagos", country="NG", start_date=now + timedelta(days=days),
                 end_date=now + timedelta(days=days, hours=4), host_id=host, status="published",
                 review_status="approved", is_free=True))
    await db.commit()
    return eid


async def _community(client, headers) -> str:
    r = await client.post("/api/communities", headers=headers, json={
        "name": f"Club {uuid.uuid4().hex[:6]}", "description": "A community for testing shares"})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


async def test_share_once_and_see_where_it_is_shared(client, db):
    h, _ = await make_user(db)
    slug, other = await _community(client, h), await _community(client, h)
    eid = await _event(db, 5)

    assert (await client.get(f"/api/communities/my/shared-event/{eid}", headers=h)).json() == {"slugs": []}
    assert (await client.post(f"/api/communities/{slug}/events", headers=h, json={"event_id": eid})).status_code == 201
    community = (await client.get(f"/api/communities/{slug}", headers=h)).json()
    assert community["event_count"] == 1
    assert [e["id"] for e in (await client.get(f"/api/communities/{slug}/events", headers=h)).json()] == [eid]
    assert (await client.get(f"/api/communities/my/shared-event/{eid}", headers=h)).json() == {"slugs": [slug]}
    assert other != slug

    again = await client.post(f"/api/communities/{slug}/events", headers=h, json={"event_id": eid})
    assert again.status_code == 409 and "already shared" in again.json()["detail"]


async def test_only_members_can_share(client, db):
    owner, _ = await make_user(db)
    stranger, _ = await make_user(db)
    slug = await _community(client, owner)
    eid = await _event(db, 5)
    assert (await client.post(f"/api/communities/{slug}/events", headers=stranger, json={"event_id": eid})).status_code == 403
    # A stranger's lookup only covers their own communities.
    assert (await client.get(f"/api/communities/my/shared-event/{eid}", headers=stranger)).json() == {"slugs": []}


async def test_ended_events_cant_be_shared(client, db):
    h, _ = await make_user(db)
    slug = await _community(client, h)
    eid = await _event(db, -3)
    r = await client.post(f"/api/communities/{slug}/events", headers=h, json={"event_id": eid})
    assert r.status_code == 400 and "ended" in r.json()["detail"]
