"""Consent history and "download my data" (app/services/data_rights.py)."""
import json

from app.models.activity import Activity
from app.models.auth_tokens import TwoFactor
from tests.test_recommendations import NOW, make_event, make_user


async def test_consent_changes_are_logged_in_order(client, db):
    h, _ = await make_user(db)
    await client.patch("/api/auth/preferences", headers=h, json={"profiling_consent": True})
    await client.patch("/api/auth/preferences", headers=h, json={"profiling_consent": True})  # no change
    await client.patch("/api/auth/preferences", headers=h, json={"profiling_consent": False, "city": "Abuja"})
    await client.patch("/api/plus/settings", headers=h, json={"wrapped_opt_in": False})
    log = (await client.get("/api/me/consents", headers=h)).json()
    assert [(c["setting"], c["value"]) for c in log] == [
        ("wrapped_opt_in", False), ("profiling_consent", False), ("profiling_consent", True)]
    assert all(c["source"] == "settings" for c in log)


async def test_export_has_my_data_and_no_secrets_or_other_peoples(client, db):
    h, me = await make_user(db, city="Lagos")
    _, host = await make_user(db, role="organizer")
    friend_h, friend = await make_user(db)
    eid = await make_event(db, host, title="Export Party")
    await client.post(f"/api/events/{eid}/save", headers=h)
    await client.post(f"/api/hidden", headers=h, json={"kind": "organizer", "target_id": host})
    await client.patch("/api/auth/preferences", headers=h, json={"personalized_recs": False})
    db.add(Activity(name="event_viewed", source="client", user_id=me, event_id=eid, occurred_at=NOW(), received_at=NOW()))
    db.add(TwoFactor(user_id=me, secret="SUPERSECRETVALUE", backup_codes="CODE1,CODE2"))
    await db.commit()
    # Someone I brought through a share link.
    code = (await client.post("/api/share", headers=h, json={"event_id": eid, "channel": "whatsapp"})).json()["code"]
    await client.post("/api/share/open", headers=friend_h, json={"code": code})
    await client.post(f"/api/events/{eid}/attend", headers=friend_h, json={"status": "going"})

    r = await client.get("/api/me/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    t = data["tables"]
    assert t["users"][0]["id"] == me and "hashed_password" not in t["users"][0]
    assert [s["event_id"] for s in t["event_saves"]] == [eid]
    assert t["hidden_items"][0]["target_id"] == host
    assert t["consent_log"][0]["setting"] == "personalized_recs"
    assert any(a["name"] == "event_viewed" for a in t["activity_log"])
    assert t["user_sessions"] and "jti" not in t["user_sessions"][0]
    assert "secret" not in t["two_factor"][0] and "backup_codes" not in t["two_factor"][0]
    conv = t["share_conversions"][0]
    assert conv["sharer_id"] == me and conv["user_id"] is None     # who I brought stays private
    raw = json.dumps(data)
    assert "SUPERSECRETVALUE" not in raw and "CODE1" not in raw and friend not in raw

    # Someone else's export doesn't include mine.
    other = (await client.get("/api/me/export", headers=friend_h)).json()["tables"]
    assert "event_saves" not in other and other["users"][0]["id"] == friend
    assert (await client.get("/api/me/export")).status_code == 401
