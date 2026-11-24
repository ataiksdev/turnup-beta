"""Share links with a ref code, credit for the people they bring in, and the tastemaker score."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.models.sharing import ShareConversion, ShareLink
from app.services.sharing import credit
from tests.test_recommendations import NOW, make_event, make_user


async def _link(client, h, eid, channel="whatsapp"):
    r = await client.post("/api/share", headers=h, json={"event_id": eid, "channel": channel})
    assert r.status_code == 200, r.text
    return r.json()


async def _open(client, code, headers=None, anon=None):
    hdrs = dict(headers or {})
    if anon:
        hdrs["X-Anonymous-Id"] = anon
    r = await client.post("/api/share/open", headers=hdrs, json={"code": code})
    assert r.status_code == 204, r.text


async def test_share_link_is_stable_per_channel_and_points_at_the_event(client, db):
    _, host = await make_user(db, role="organizer")
    h, _ = await make_user(db)
    eid = await make_event(db, host)
    a = await _link(client, h, eid)
    assert a == await _link(client, h, eid)
    b = await _link(client, h, eid, "copy_link")
    assert a["code"] != b["code"]
    assert a["url"].endswith(f"?ref={a['code']}") and "/events/ev-" in a["url"]
    assert (await client.post("/api/share", json={"event_id": eid, "channel": "whatsapp"})).status_code == 401
    assert (await client.post("/api/share", headers=h, json={"event_id": eid, "channel": "sms"})).status_code == 422


async def test_signed_out_open_then_signup_and_rsvp_credits_the_sharer(client, db):
    _, host = await make_user(db, role="organizer")
    sharer_h, sharer = await make_user(db)
    eid = await make_event(db, host)
    code = (await _link(client, sharer_h, eid))["code"]

    anon = f"anon-{uuid.uuid4().hex[:12]}"
    await _open(client, code, anon=anon)
    await _open(client, code, anon=anon)                 # same device again: one open
    friend_h, friend = await make_user(db)
    # Signing in on that device claims its signed-out activity, the open included.
    assert (await client.post("/api/track/identify", headers=friend_h, json={"anonymous_id": anon})).status_code < 300
    assert (await client.post(f"/api/events/{eid}/attend", headers=friend_h, json={"status": "going"})).status_code == 200
    assert (await client.post(f"/api/events/{eid}/save", headers=friend_h)).json() == {"saved": True}

    convs = (await db.execute(select(ShareConversion).where(ShareConversion.sharer_id == sharer))).scalars().all()
    assert sorted(c.kind for c in convs) == ["going", "save"] and {c.user_id for c in convs} == {friend}

    mine = (await client.get("/api/share/mine", headers=sharer_h)).json()
    assert mine["people_brought"] == 1 and mine["opens"] == 1
    assert mine["events"][0]["event_id"] == eid and mine["events"][0]["going"] == 1


async def test_no_credit_for_yourself_strangers_or_stale_opens(client, db):
    _, host = await make_user(db, role="organizer")
    sharer_h, sharer = await make_user(db)
    eid = await make_event(db, host)
    code = (await _link(client, sharer_h, eid))["code"]

    await _open(client, code, headers=sharer_h)          # the sharer opening their own link
    await client.post(f"/api/events/{eid}/attend", headers=sharer_h, json={"status": "going"})
    stranger_h, _ = await make_user(db)                  # never opened the link
    await client.post(f"/api/events/{eid}/attend", headers=stranger_h, json={"status": "going"})
    late_h, late = await make_user(db)
    await _open(client, code, headers=late_h)
    assert await credit(db, late, eid, "order", now=NOW() + timedelta(days=8)) is False
    assert await credit(db, late, eid, "order") is True
    assert await credit(db, late, eid, "order") is False   # once per kind
    await db.commit()

    convs = (await db.execute(select(ShareConversion).where(ShareConversion.sharer_id == sharer))).scalars().all()
    assert [(c.user_id, c.kind) for c in convs] == [(late, "order")]
    link = (await db.execute(select(ShareLink).where(ShareLink.code == code))).scalar_one()
    assert link.opens == 1
    await _open(client, "ZZZZZZZZ")                       # unknown codes are ignored


async def test_people_brought_through_shares_raise_the_tastemaker_score(client, db):
    from app.models.user import User
    from app.services.rec_features import _tastemaker_scores
    _, host = await make_user(db, role="organizer")
    sharer_h, sharer = await make_user(db, profiling_consent=True)
    quiet_h, quiet = await make_user(db, profiling_consent=True)
    eid = await make_event(db, host)
    code = (await _link(client, sharer_h, eid))["code"]
    for _ in range(3):
        h, _ = await make_user(db)
        await _open(client, code, headers=h)
        await client.post(f"/api/events/{eid}/attend", headers=h, json={"status": "going"})
    scores = await _tastemaker_scores(db, {sharer, quiet}, NOW() + timedelta(seconds=5))
    assert scores[sharer] > 0.3 and scores[quiet] == 0
    assert (await db.get(User, sharer)) is not None
