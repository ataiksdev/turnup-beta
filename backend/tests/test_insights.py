"""Organizer insights (app/services/insights.py)."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.activity import Activity
from app.models.event import EventAttendee
from app.models.organizer import TicketTier
from app.services.insights import LAGOS
from tests.test_recommendations import NOW, make_category, make_event, make_user


def _lagos(days_ago: int, weekday: int, hour: int) -> datetime:
    """A past date on the given Lagos weekday and hour."""
    d = (NOW() - timedelta(days=days_ago)).astimezone(LAGOS)
    d -= timedelta(days=(d.weekday() - weekday) % 7)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def _people_going(db, eid, n, start, days_before=(10,)):
    for i in range(n):
        _, uid = await make_user(db)
        db.add(EventAttendee(user_id=uid, event_id=eid, status="going",
                             created_at=start - timedelta(days=days_before[i % len(days_before)])))
    await db.commit()


async def test_best_day_price_and_booking_pace(client, db):
    cat, _ = await make_category(db)
    host_h, me = await make_user(db, role="organizer")
    others = [(await make_user(db, role="organizer"))[1] for _ in range(3)]
    # Past events in this category: Saturday evenings draw 8, Tuesday mornings 3.
    for i in range(4):
        sat = _lagos(20 + 7 * i, 5, 19)
        eid = await make_event(db, others[i % 3], category_id=cat, start=sat, is_free=False)
        db.add(TicketTier(id=str(uuid.uuid4()), event_id=eid, name="R", price=5000 + 1000 * i, is_active=True))
        await _people_going(db, eid, 8, sat, days_before=(20, 10, 5, 1))
        tue = _lagos(22 + 7 * i, 1, 9)
        eid = await make_event(db, others[i % 3], category_id=cat, start=tue, is_free=False)
        db.add(TicketTier(id=str(uuid.uuid4()), event_id=eid, name="R", price=9000 + 500 * i, is_active=True))
        await _people_going(db, eid, 6, tue, days_before=(10, 2))
    h, _ = await make_user(db)
    mine = await make_event(db, me, category_id=cat, start=NOW() + timedelta(days=12), is_free=False)
    db.add(TicketTier(id=str(uuid.uuid4()), event_id=mine, name="R", price=20000, is_active=True))
    await db.commit()
    await _people_going(db, mine, 4, NOW() + timedelta(days=12), days_before=(13,))

    r = await client.get(f"/api/events/{mine}/insights", headers=host_h)
    assert r.status_code == 200, r.text
    data = r.json()

    best = data["best_times"]["best"][0]
    assert (best["day"], best["part"], best["avg_turnout"]) == ("Sat", "evening", 8.0)
    price = data["price"]
    assert price["comparables"] == 8 and price["position"] == "high" and price["yours"] == 20000
    assert price["p25"] <= price["median"] <= price["p75"]
    curve = data["booking_curve"]
    assert curve["so_far"] == 4 and curve["comparables"] == 8
    at = {p["days_before"]: p for p in curve["points"]}
    assert at[0]["typical_share"] == 1.0 and at[30]["typical_share"] == 0.0
    assert at[14]["yours"] == 0 and at[7]["yours"] is None   # 7 days before hasn't happened yet
    assert curve["projected_total"] and curve["projected_total"] >= 4

    # Only the event's team can see it.
    assert (await client.get(f"/api/events/{mine}/insights", headers=h)).status_code == 403


async def test_unmet_searches_need_three_people_and_respect_city(client, db):
    word = f"zq{uuid.uuid4().hex[:6]}"
    def search(person, query, results, city=None):
        db.add(Activity(name="search_executed", source="client", anonymous_id=person,
                        occurred_at=NOW() - timedelta(days=1), received_at=NOW(),
                        props={"query": query, "results_count": results, "filters": {"city": city}}))
    for i in range(3):
        search(f"p{i}{word}", f"{word} Brunch", 0, "Abuja")
    search(f"p0{word}", f"{word}  brunch", 0, "Abuja")            # same person again: still 3 people
    for i in range(2):
        search(f"q{i}{word}", f"{word} rave", 0, "Abuja")          # only 2 people: hidden
    for i in range(4):
        search(f"r{i}{word}", f"{word} jazz", 3, "Abuja")          # found something: not unmet
    await db.commit()

    org_h, _ = await make_user(db, role="organizer")
    r = await client.get("/api/organizer/insights/searches", headers=org_h, params={"city": "abuja"})
    found = {s["query"]: s["people"] for s in r.json()["searches"] if word in s["query"]}
    assert found == {f"{word} brunch": 3}
    r = await client.get("/api/organizer/insights/searches", headers=org_h, params={"city": "Kano"})
    assert not [s for s in r.json()["searches"] if word in s["query"]]
    attendee_h, _ = await make_user(db)
    assert (await client.get("/api/organizer/insights/searches", headers=attendee_h)).status_code == 403
