"""Search (full-text with typo tolerance), "Not interested" / "Hide this organizer", and
"Notify me" search alerts."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.discovery import SearchAlert
from app.models.event import Event
from app.models.social import Notification
from app.services.search_alerts import send_search_alerts
from tests.test_venues import make_user


def _word() -> str:
    """A made-up word unique to one test (the test database is shared across tests)."""
    return "zq" + uuid.uuid4().hex[:8].translate(str.maketrans("0123456789", "ghijklmnop"))


async def _event(db, host_id: str, title: str, *, tags: str | None = None, city: str = "Lagos",
                 days: int = 5, created_at: datetime | None = None) -> Event:
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    days += 900  # well after other tests' events, so these never crowd their first page
    e = Event(id=eid, slug=f"e-{eid}", title=title, description="An evening out " * 3,
              venue_name="Terra Kulture", address="1 Test Street", city=city, country="NG",
              start_date=now + timedelta(days=days), end_date=now + timedelta(days=days, hours=4),
              host_id=host_id, status="published", review_status="approved", tags=tags,
              created_at=created_at or now)
    db.add(e)
    await db.commit()
    return e


async def _search(client, q: str, headers=None, **params) -> list[str]:
    r = await client.get("/api/events", params={"q": q, "limit": 100, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return [e["id"] for e in r.json()]


# ── Search ──────────────────────────────────────────────────────────────────────

async def test_search_matches_every_word_across_fields(client, db):
    _, host = await make_user(db, "organizer")
    w = _word()
    hit = await _event(db, host, f"{w} Rooftop Night", city="Abuja")
    miss = await _event(db, host, f"{w} Brunch", city="Ibadan")
    found = await _search(client, f"{w} abuja")
    assert hit.id in found and miss.id not in found


async def test_search_finds_word_prefixes(client, db):
    _, host = await make_user(db, "organizer")
    w = _word()
    e = await _event(db, host, f"{w}beats Live")
    assert e.id in await _search(client, w)


async def test_search_tolerates_a_typo(client, db):
    from tests.conftest import IS_SQLITE
    if not IS_SQLITE:
        # The suite builds its schema with create_all; typo tolerance needs migration 0009's pg_trgm.
        from sqlalchemy import text
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await db.commit()
        from app.services import search
        search._trgm_cache.clear()
    _, host = await make_user(db, "organizer")
    w = _word()  # e.g. zqabcdefgh
    e = await _event(db, host, f"{w} Showcase")
    typo = w[:-2] + w[-1] + w[-2]  # last two letters swapped
    assert e.id in await _search(client, typo)


async def test_search_by_relevance_puts_the_best_match_first(client, db):
    _, host = await make_user(db, "organizer")
    w = _word()
    weak = await _event(db, host, "Afternoon Mixer", tags=w, days=1)
    strong = await _event(db, host, f"{w} {w} Festival", tags=w, days=9)
    found = await _search(client, w, sort="relevance")
    assert set(found) >= {weak.id, strong.id}
    # SQLite can't score, so relevance falls back to date order there; Postgres ranks.
    from tests.conftest import IS_SQLITE
    if not IS_SQLITE:
        assert found.index(strong.id) < found.index(weak.id)


async def test_search_with_only_punctuation_returns_everything_else_filtered(client, db):
    r = await client.get("/api/events", params={"q": "!!!", "limit": 5})
    assert r.status_code == 200


# ── Hidden events and organizers ────────────────────────────────────────────────

async def test_not_interested_hides_an_event_from_feeds_until_unhidden(client, db):
    h, _ = await make_user(db)
    _, host = await make_user(db, "organizer")
    w = _word()
    e = await _event(db, host, f"{w} Party")
    assert e.id in await _search(client, w, headers=h)

    r = await client.post("/api/hidden", headers=h, json={"kind": "event", "target_id": e.id})
    assert r.status_code == 201 and r.json()["label"] == e.title
    # Hiding twice is fine.
    assert (await client.post("/api/hidden", headers=h, json={"kind": "event", "target_id": e.id})).status_code == 201

    assert e.id not in await _search(client, w, headers=h)
    for_you = (await client.get("/api/events/for-you", headers=h, params={"limit": 50})).json()
    assert e.id not in [x["id"] for x in for_you]
    # Other people still see it, and so does anyone signed out.
    h2, _ = await make_user(db)
    assert e.id in await _search(client, w, headers=h2)
    assert e.id in await _search(client, w)
    # The event page still opens for the person who hid it.
    assert (await client.get(f"/api/events/{e.id}", headers=h)).status_code == 200

    listed = (await client.get("/api/hidden", headers=h)).json()
    assert [(x["kind"], x["target_id"]) for x in listed] == [("event", e.id)]

    assert (await client.delete(f"/api/hidden/event/{e.id}", headers=h)).status_code == 204
    assert e.id in await _search(client, w, headers=h)
    assert (await client.get("/api/hidden", headers=h)).json() == []


async def test_hiding_an_organizer_hides_all_their_events(client, db):
    h, me = await make_user(db)
    _, host = await make_user(db, "organizer")
    _, other_host = await make_user(db, "organizer")
    w = _word()
    a = await _event(db, host, f"{w} One")
    b = await _event(db, host, f"{w} Two")
    c = await _event(db, other_host, f"{w} Three")

    r = await client.post("/api/hidden", headers=h, json={"kind": "organizer", "target_id": host})
    assert r.status_code == 201
    found = await _search(client, w, headers=h)
    assert a.id not in found and b.id not in found and c.id in found

    assert (await client.post("/api/hidden", headers=h, json={"kind": "organizer", "target_id": me})).status_code == 400
    assert (await client.post("/api/hidden", headers=h, json={"kind": "organizer", "target_id": "nope"})).status_code == 404
    assert (await client.post("/api/hidden", headers=h, json={"kind": "event", "target_id": "nope"})).status_code == 404
    assert (await client.get("/api/hidden")).status_code == 401


# ── Search alerts ───────────────────────────────────────────────────────────────

async def test_search_alert_notifies_once_about_a_new_matching_event(client, db):
    h, me = await make_user(db)
    _, host = await make_user(db, "organizer")
    w = _word()
    old = await _event(db, host, f"{w} Old Show", created_at=datetime.now(timezone.utc) - timedelta(days=1))

    r = await client.post("/api/search-alerts", headers=h, json={"q": f"  {w} ", "city": "Lagos"})
    assert r.status_code == 201, r.text
    alert_id = r.json()["id"]
    # The same search again returns the same alert.
    again = await client.post("/api/search-alerts", headers=h, json={"q": w.upper(), "city": "lagos"})
    assert again.json()["id"] == alert_id

    await send_search_alerts(db)
    notes = (await db.execute(select(Notification).where(Notification.user_id == me,
                                                         Notification.type == "search_alert"))).scalars().all()
    assert notes == []  # the event existed before the alert

    new = await _event(db, host, f"{w} New Show")
    await _event(db, host, f"{w} Elsewhere", city="Kano")
    await send_search_alerts(db)
    notes = (await db.execute(select(Notification).where(Notification.user_id == me,
                                                         Notification.type == "search_alert"))).scalars().all()
    assert len(notes) == 1 and notes[0].reference_id == new.id and notes[0].body == new.title
    assert old.id != new.id

    # Checked again: nothing new, nothing sent.
    await send_search_alerts(db)
    count = len((await db.execute(select(Notification).where(Notification.user_id == me,
                                                             Notification.type == "search_alert"))).scalars().all())
    assert count == 1

    listed = (await client.get("/api/search-alerts", headers=h)).json()
    assert [a["id"] for a in listed] == [alert_id] and listed[0]["notified_count"] == 1
    assert (await client.delete(f"/api/search-alerts/{alert_id}", headers=h)).status_code == 204
    assert (await client.get("/api/search-alerts", headers=h)).json() == []


async def test_search_alert_skips_hidden_organizers_and_expires(client, db):
    h, me = await make_user(db)
    _, host = await make_user(db, "organizer")
    w = _word()
    await client.post("/api/hidden", headers=h, json={"kind": "organizer", "target_id": host})
    r = await client.post("/api/search-alerts", headers=h, json={"q": w})
    alert_id = r.json()["id"]
    await _event(db, host, f"{w} Hidden Host Show")
    await send_search_alerts(db)
    assert (await db.execute(select(Notification).where(Notification.user_id == me))).scalars().all() == []

    alert = await db.get(SearchAlert, alert_id)
    alert.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()
    await send_search_alerts(db)
    await db.refresh(alert)
    assert alert.is_active is False


async def test_search_alert_validation_and_limit(client, db):
    h, _ = await make_user(db)
    assert (await client.post("/api/search-alerts", headers=h, json={"q": "   "})).status_code == 422
    assert (await client.post("/api/search-alerts", headers=h, json={"q": "?!"})).status_code == 422
    for i in range(20):
        assert (await client.post("/api/search-alerts", headers=h, json={"q": f"thing {i}"})).status_code == 201
    assert (await client.post("/api/search-alerts", headers=h, json={"q": "one too many"})).status_code == 409
