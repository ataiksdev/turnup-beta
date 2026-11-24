"""Similar events and "people who went to X also went to Y" (app/services/similar.py)."""
from datetime import timedelta

from app.models.event import EventAttendee, EventSave
from tests.test_recommendations import NOW, make_category, make_event, make_user


async def _going(db, uid, *eids):
    for eid in eids:
        db.add(EventAttendee(user_id=uid, event_id=eid, status="going"))
    await db.commit()


async def _similar(client, eid, headers=None):
    r = await client.get(f"/api/events/{eid}/similar", headers=headers, params={"limit": 20})
    assert r.status_code == 200, r.text
    return {e["id"]: e["rec_reason"] for e in r.json()}


async def test_people_who_went_also_went_needs_two_people_in_common(client, db):
    _, h1 = await make_user(db, role="organizer")
    _, h2 = await make_user(db, role="organizer")
    _, h3 = await make_user(db, role="organizer")
    x = await make_event(db, h1, title="Source Show")
    y = await make_event(db, h2)          # two people in common
    z = await make_event(db, h3)          # only one: never shown, it would point at one person
    a, b = (await make_user(db))[1], (await make_user(db))[1]
    await _going(db, a, x, y, z)
    await _going(db, b, x)
    db.add(EventSave(user_id=b, event_id=y))
    await db.commit()

    found = await _similar(client, x)
    assert found.get(y) == "People who went to this also went"
    assert z not in found and x not in found


async def test_content_similarity_fills_in_and_respects_the_viewer(client, db):
    cat, _ = await make_category(db)
    _, h1 = await make_user(db, role="organizer")
    _, h2 = await make_user(db, role="organizer")
    _, h3 = await make_user(db, role="organizer")
    x = await make_event(db, h1, category_id=cat, tags="jazz,live")
    same = await make_event(db, h2, category_id=cat, tags="jazz")
    hidden_host_event = await make_event(db, h3, category_id=cat, tags="jazz")
    already = await make_event(db, h2, category_id=cat, tags="jazz,live")
    past = await make_event(db, h2, category_id=cat, tags="jazz", start=NOW() - timedelta(days=3))
    unrelated = await make_event(db, h2, city="Kano")

    headers, me = await make_user(db)
    await _going(db, me, already)
    assert (await client.post("/api/hidden", headers=headers,
                              json={"kind": "organizer", "target_id": h3})).status_code == 201

    found = await _similar(client, x, headers)
    assert same in found and found[same].startswith("More ")
    for eid in (hidden_host_event, already, past, unrelated, x):
        assert eid not in found
    # Signed out, the hidden organizer and their own commitments don't apply.
    anon = await _similar(client, x)
    assert hidden_host_event in anon and already in anon


async def test_at_most_two_from_one_organizer_and_unknown_events_404(client, db):
    cat, _ = await make_category(db)
    _, h1 = await make_user(db, role="organizer")
    _, h2 = await make_user(db, role="organizer")
    x = await make_event(db, h1, category_id=cat, tags="afro")
    many = [await make_event(db, h2, category_id=cat, tags="afro") for _ in range(4)]
    found = await _similar(client, x)
    assert len(set(found) & set(many)) == 2
    assert (await client.get("/api/events/nope/similar")).status_code == 404
