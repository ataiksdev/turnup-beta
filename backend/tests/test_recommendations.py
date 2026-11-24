"""Activity tracking, recommendation features and the /for-you ranker
(docs/recommendations-spec.md).

The database is shared by the whole session (see test_tickets.py), so every test makes its
own users, categories and events with unique names and only asserts about those.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select

from app.models.activity import Activity, EventFeatures, UserFeatures
from app.models.auth_tokens import UserSession
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import TicketTier
from app.models.social import Follow
from app.models.user import User
from app.services.auth import create_access_token
from app.services.rec_features import compute_event_features, compute_user_features, wilson_lower_bound

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def make_user(db, **kw) -> tuple[dict, str]:
    uid, jti, n = str(uuid.uuid4()), str(uuid.uuid4()), _u()
    db.add(User(id=uid, username=f"u_{n}", email=f"u_{n}@example.com", full_name="Test",
                role=kw.pop("role", "attendee"), is_active=True, is_deleted=False, **kw))
    db.add(UserSession(id=str(uuid.uuid4()), user_id=uid, jti=jti, is_active=True,
                       expires_at=NOW() + timedelta(hours=2)))
    await db.commit()
    token, _ = create_access_token(uid, jti)
    return {"Authorization": f"Bearer {token}"}, uid


async def make_category(db) -> tuple[str, str]:
    cid, slug = str(uuid.uuid4()), f"cat-{_u()}"
    db.add(Category(id=cid, name=f"Cat {slug}", slug=slug))
    await db.commit()
    return cid, slug


async def make_event(db, host_id: str, **kw) -> str:
    eid = str(uuid.uuid4())
    start = kw.pop("start", NOW() + timedelta(days=2))
    db.add(Event(id=eid, slug=f"ev-{eid[:8]}", title=kw.pop("title", f"Event {eid[:6]}"),
                 description="d" * 40, venue_name="Hall", address="1 Street",
                 city=kw.pop("city", "Lagos"), country="NG", start_date=start,
                 end_date=start + timedelta(hours=4), host_id=host_id, status="published", **kw))
    await db.commit()
    return eid


@pytest_asyncio.fixture
async def host(db):
    return await make_user(db, role="organizer")


def batch(anon: str, *events, **kw) -> dict:
    return {"anonymous_id": anon, "session_id": f"s{_u()}", "platform": "web", "events": list(events), **kw}


# ── Ingest ──────────────────────────────────────────────────────────────────────


async def test_track_keeps_known_client_events_and_drops_the_rest(client, db, host):
    eid = await make_event(db, host[1])
    anon = f"anon{_u()}"
    one = str(uuid.uuid4())
    r = await client.post("/api/track", json=batch(
        anon,
        {"id": one, "name": "event_viewed", "event_id": eid, "surface": "for_you", "position": 2},
        {"id": one, "name": "event_viewed", "event_id": eid},            # duplicate id
        {"name": "order_completed", "event_id": eid},                    # server-only name
        {"name": "made_up_event"},
        {"name": "search_executed", "props": {"q": "x" * 5000}},         # details too big
    ))
    assert r.status_code == 202 and r.json() == {"accepted": 1}
    # Re-sending the same batch (a retry) adds nothing.
    r = await client.post("/api/track", json=batch(anon, {"id": one, "name": "event_viewed", "event_id": eid}))
    assert r.json() == {"accepted": 0}
    rows = (await db.execute(select(Activity).where(Activity.anonymous_id == anon))).scalars().all()
    assert [(a.name, a.surface, a.position, a.user_id) for a in rows] == [("event_viewed", "for_you", 2, None)]


async def test_coordinates_are_kept_only_with_profiling_consent(client, db):
    no_auth, no_id = await make_user(db)
    yes_auth, yes_id = await make_user(db, profiling_consent=True)
    geo = {"city": "Lagos", "lat": 6.4281234, "lon": 3.4219876}
    for headers in (no_auth, yes_auth):
        r = await client.post("/api/track", headers=headers, json=batch(
            f"anon{_u()}", {"name": "session_started"}, geo=geo))
        assert r.status_code == 202
    rows = {a.user_id: a for a in (await db.execute(select(Activity).where(
        Activity.user_id.in_([no_id, yes_id])))).scalars().all()}
    assert (rows[no_id].geo_lat, rows[no_id].geo_city) == (None, "Lagos")
    assert (rows[yes_id].geo_lat, rows[yes_id].geo_lon) == (6.42812, 3.42199)


async def test_signing_in_claims_the_devices_signed_out_browsing(client, db, host):
    eid = await make_event(db, host[1])
    anon = f"anon{_u()}"
    await client.post("/api/track", json=batch(anon, {"name": "event_viewed", "event_id": eid}))
    auth, uid = await make_user(db)
    r = await client.post("/api/track/identify", headers=auth, json={"anonymous_id": anon})
    assert r.json() == {"linked": 1}
    row = (await db.execute(select(Activity).where(Activity.anonymous_id == anon))).scalar_one()
    assert row.user_id == uid


# ── Server events ───────────────────────────────────────────────────────────────


async def test_server_records_saves_rsvps_and_free_orders(client, db, host):
    auth, uid = await make_user(db)
    free_event = await make_event(db, host[1])
    ticketed = await make_event(db, host[1], is_free=False)
    tier_id = str(uuid.uuid4())
    db.add(TicketTier(id=tier_id, event_id=ticketed, name="Free pass", price=0, quantity=10))
    await db.commit()

    assert (await client.post(f"/api/events/{free_event}/save", headers=auth)).json() == {"saved": True}
    assert (await client.post(f"/api/events/{free_event}/attend", headers=auth,
                              json={"status": "interested"})).status_code == 200
    r = await client.post(f"/api/events/{ticketed}/tickets/checkout", headers=auth,
                          json={"items": [{"tier_id": tier_id, "quantity": 2}]})
    assert r.status_code == 200, r.text

    rows = (await db.execute(select(Activity).where(Activity.user_id == uid)
                             .order_by(Activity.id))).scalars().all()
    names = [(a.name, a.event_id) for a in rows]
    assert ("event_saved", free_event) in names
    assert ("rsvp_changed", free_event) in names
    assert ("checkout_started", ticketed) in names
    order = next(a for a in rows if a.name == "order_completed")
    assert order.source == "server" and order.props["ticket_count"] == 2 and order.props["lead_time_hours"] > 40


async def test_deleting_the_account_deletes_its_activity(client, db, host):
    auth, uid = await make_user(db)
    anon = f"anon{_u()}"
    eid = await make_event(db, host[1])
    await client.post("/api/track", headers=auth, json=batch(anon, {"name": "event_viewed", "event_id": eid}))
    # Later, signed out on the same phone.
    await client.post("/api/track", json=batch(anon, {"name": "event_viewed", "event_id": eid}))
    db.add(UserFeatures(user_id=uid))
    await db.commit()

    r = await client.request("DELETE", "/api/auth/account", headers=auth,
                             json={"confirm_username": (await db.get(User, uid)).username})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert (await db.execute(select(Activity).where(Activity.anonymous_id == anon))).first() is None
    assert await db.get(UserFeatures, uid) is None


async def test_profiling_consent_is_timestamped_and_withdrawing_clears_it(client, db):
    auth, uid = await make_user(db)
    r = await client.patch("/api/auth/preferences", headers=auth,
                           json={"profiling_consent": True, "birth_year": 1998, "gender": "female"})
    body = r.json()
    assert r.status_code == 200 and body["profiling_consent"] and body["profiling_consent_at"]
    assert (body["birth_year"], body["gender"]) == (1998, "female")

    db.add(UserFeatures(user_id=uid, segments=["big_spender"], tastemaker_score=0.4, peak_hours=[21]))
    await db.commit()
    r = await client.patch("/api/auth/preferences", headers=auth, json={"profiling_consent": False, "gender": None})
    assert r.json()["profiling_consent"] is False and r.json()["gender"] is None
    db.expire_all()
    f = await db.get(UserFeatures, uid)
    assert (f.segments, f.tastemaker_score, f.peak_hours) == (None, None, None)
    logged = (await db.execute(select(Activity).where(Activity.user_id == uid,
                                                      Activity.name == "profile_updated"))).scalars().all()
    # Age, gender and consent are noted by field name only, never their values.
    assert all("gender" not in (a.props.get("values") or {}) for a in logged)


# ── Features ────────────────────────────────────────────────────────────────────


async def test_event_features_count_people_not_clicks_and_ignore_the_host(client, db, host):
    host_auth, host_id = host
    eid = await make_event(db, host_id)
    viewer_a, viewer_b = f"anon{_u()}", f"anon{_u()}"
    await client.post("/api/track", json=batch(viewer_a, *[{"name": "event_viewed", "event_id": eid}] * 5))
    await client.post("/api/track", json=batch(viewer_b, {"name": "event_viewed", "event_id": eid}))
    await client.post("/api/track", headers=host_auth,
                      json=batch(f"anon{_u()}", *[{"name": "event_viewed", "event_id": eid}] * 9))
    await compute_event_features(db)
    f = await db.get(EventFeatures, eid)
    assert f.views_7d == 2


async def test_user_features_learn_taste_spend_and_timing(db, host):
    _, uid = await make_user(db)
    liked, glanced = (await make_category(db))[0], (await make_category(db))[0]
    for _ in range(2):
        db.add(EventSave(id=str(uuid.uuid4()), user_id=uid,
                         event_id=await make_event(db, host[1], category_id=liked, tags="afrobeats,live")))
    going = await make_event(db, host[1], category_id=glanced, start=NOW() + timedelta(hours=20))
    db.add(EventAttendee(id=str(uuid.uuid4()), user_id=uid, event_id=going, status="interested"))
    await db.commit()
    await compute_user_features(db, user_ids=[uid])
    f = await db.get(UserFeatures, uid)
    assert f.category_affinity[liked] == 1.0
    assert 0 < f.category_affinity[glanced] < 1
    assert "afrobeats" in f.tag_affinity
    assert f.segments is None  # no profiling consent


def test_wilson_prefers_more_evidence():
    assert wilson_lower_bound(80, 100) > wilson_lower_bound(3, 3)
    assert wilson_lower_bound(0, 0) == 0


# ── Ranker ──────────────────────────────────────────────────────────────────────


async def test_for_you_ranks_by_taste_with_reasons_and_logs_what_it_showed(client, db, host):
    cat_id, slug = await make_category(db)
    city = f"Town{_u()}"
    auth, uid = await make_user(db, category_preferences=slug, city=city)
    match = await make_event(db, host[1], category_id=cat_id, city=city)
    other = await make_event(db, host[1], city=city)
    saved = await make_event(db, host[1], category_id=cat_id, city=city)
    db.add(EventSave(id=str(uuid.uuid4()), user_id=uid, event_id=saved))
    await db.commit()
    await compute_event_features(db)

    r = await client.get("/api/events/for-you?limit=50", headers={**auth, "X-Anonymous-Id": f"anon{_u()}"})
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert saved not in ids                       # already saved: not recommended again
    assert ids.index(match) < ids.index(other)
    first = next(e for e in r.json() if e["id"] == match)
    assert first["rec_reason"] == f"Because you like Cat {slug}"
    served = (await db.execute(select(Activity).where(
        Activity.rec_request_id == first["rec_request_id"]))).scalar_one()
    assert served.name == "recs_served" and served.props["event_ids"] == ids


async def test_friends_going_beats_a_stranger_event(client, db, host):
    auth, uid = await make_user(db)
    _, friend = await make_user(db)
    db.add(Follow(follower_id=uid, following_id=friend))
    city = f"Town{_u()}"
    with_friend = await make_event(db, host[1], city=city)
    db.add(EventAttendee(id=str(uuid.uuid4()), user_id=friend, event_id=with_friend, status="going"))
    await db.commit()
    r = await client.get("/api/events/for-you?limit=50", headers=auth)
    top = next(e for e in r.json() if e["id"] == with_friend)
    assert top["rec_reason"] == "1 person you follow is going"


async def test_signed_out_feed_works_and_never_shows_your_own_events(client, db, host):
    r = await client.get("/api/events/for-you?limit=5&lat=6.45&lon=3.4", headers={"X-Anonymous-Id": f"anon{_u()}"})
    assert r.status_code == 200 and len(r.json()) <= 5
    host_auth, host_id = host
    own = await make_event(db, host_id)
    ids = [e["id"] for e in (await client.get("/api/events/for-you?limit=50", headers=host_auth)).json()]
    assert own not in ids


async def test_personalisation_off_gives_the_same_feed_as_signed_out_taste(client, db, host):
    cat_id, slug = await make_category(db)
    auth, uid = await make_user(db, category_preferences=slug, personalized_recs=False)
    match = await make_event(db, host[1], category_id=cat_id)
    r = await client.get("/api/events/for-you?limit=50", headers=auth)
    row = next((e for e in r.json() if e["id"] == match), None)
    assert row is None or row["rec_reason"] != f"Because you like Cat {slug}"


async def test_offline_evaluation_scores_the_ranker_and_leaves_live_features_alone(db, host):
    from app.services.rec_eval import evaluate
    cat_id, slug = await make_category(db)
    _, uid = await make_user(db, category_preferences=slug, created_at=NOW() - timedelta(days=30))
    liked = await make_event(db, host[1], category_id=cat_id, start=NOW() + timedelta(days=5),
                             created_at=NOW() - timedelta(days=20))
    db.add(EventSave(id=str(uuid.uuid4()), user_id=uid, event_id=liked, created_at=NOW() - timedelta(days=2)))
    db.add(EventFeatures(event_id=liked, demand_score=0.123))
    await db.commit()

    result = await evaluate(db, holdout_days=10, k=10)
    assert result["people"] >= 1 and set(result) >= {"ranker", "popular", "random"}
    assert result["ranker"]["recall@10"] is not None
    db.expire_all()
    assert (await db.get(EventFeatures, liked)).demand_score == 0.123  # rolled back


# ── Discovery slots ─────────────────────────────────────────────────────────────


def _scored(score: float, *, age_days: float = 1, host: str | None = None, cat: str | None = None):
    from app.services.recommender import Scored
    e = Event(id=str(uuid.uuid4()), host_id=host or str(uuid.uuid4()), category_id=cat,
              created_at=NOW() - timedelta(days=age_days))
    return Scored(event=e, score=score, parts={})


def _features(eid: str, impressions: int, quality: float = 0.5) -> EventFeatures:
    return EventFeatures(event_id=eid, impressions_7d=impressions, organizer_quality=quality)


def test_discovery_slots_go_to_new_events_few_people_have_seen():
    from app.services.recommender import DISCOVERY_SLOTS, add_discovery
    old = [_scored(10 - i * 0.1, age_days=60) for i in range(20)]          # established
    seen = _scored(5, age_days=2)                                           # new but widely shown
    fresh_a, fresh_b = _scored(3, age_days=1), _scored(2, age_days=3)       # new and unseen
    stale = _scored(4, age_days=30)                                         # too old
    poor = _scored(4.5, age_days=1)                                         # weak organizer
    scored = old + [seen, fresh_a, fresh_b, stale, poor]
    feats = {seen.event.id: _features(seen.event.id, 500), poor.event.id: _features(poor.event.id, 0, 0.2)}

    picked, ids = add_discovery(old[:20], scored, feats, NOW(), 20)
    assert len(picked) == 20
    assert [picked[i].event.id for i in DISCOVERY_SLOTS] == [fresh_a.event.id, fresh_b.event.id]
    assert ids == [fresh_a.event.id, fresh_b.event.id]
    assert picked[DISCOVERY_SLOTS[0]].reason == "New on Turnup"
    # Everything else keeps its order.
    others = [s.event.id for i, s in enumerate(picked) if i not in DISCOVERY_SLOTS]
    assert others == [s.event.id for s in old[:18]]


def test_a_new_event_already_ranked_into_a_slot_keeps_it_and_bad_fits_are_skipped():
    from app.services.recommender import DISCOVERY_SLOTS, add_discovery
    ranked = [_scored(10 - i, age_days=60) for i in range(5)]
    ranked[DISCOVERY_SLOTS[0]] = _scored(6.5, age_days=1)                  # earned slot 3 itself
    disliked = _scored(-1, age_days=1)                                      # new, but a bad fit
    picked, ids = add_discovery(ranked, ranked + [disliked], {}, NOW(), 10)
    assert [s.event.id for s in picked] == [s.event.id for s in ranked]
    assert ids == [ranked[DISCOVERY_SLOTS[0]].event.id]
    assert disliked.event.id not in {s.event.id for s in picked}


def test_short_feeds_and_no_candidates_are_left_alone():
    from app.services.recommender import add_discovery
    ranked = [_scored(5, age_days=60) for _ in range(3)]
    assert add_discovery(ranked, ranked, {}, NOW(), 3) == (ranked, [])
    fresh = _scored(1, age_days=1)
    picked, ids = add_discovery(ranked, ranked + [fresh], {}, NOW(), 20)
    assert [s.event.id for s in picked][-1] == fresh.event.id and ids == [fresh.event.id]


async def test_for_you_logs_which_events_held_discovery_slots(client, db, host):
    from app.services.recommender import DISCOVERY_SLOTS
    h, uid = await make_user(db)
    for _ in range(12):
        await make_event(db, host[1])
    r = await client.get("/api/events/for-you", headers=h, params={"limit": 20})
    assert r.status_code == 200
    served = [e["id"] for e in r.json()]
    row = (await db.execute(select(Activity).where(Activity.user_id == uid, Activity.name == "recs_served")
                            .order_by(Activity.id.desc()))).scalars().first()
    ids = row.props["discovery_ids"]
    assert ids and set(ids) <= set(served)
    assert all(served.index(i) in DISCOVERY_SLOTS for i in ids)
