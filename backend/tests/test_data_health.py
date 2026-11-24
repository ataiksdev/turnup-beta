"""Admin data-health page (app/services/data_health.py)."""
import uuid
from datetime import timedelta

from app.models.activity import Activity
from tests.test_recommendations import NOW, make_user


def _row(name, **kw):
    at = kw.pop("at", NOW() - timedelta(hours=1))
    return Activity(name=name, source=kw.pop("source", "client"), occurred_at=at,
                    received_at=kw.pop("received", at + timedelta(seconds=30)), **kw)


async def test_data_health_reports_volume_delay_positions_and_discovery(client, db):
    surface = f"zz{uuid.uuid4().hex[:6]}"
    req = str(uuid.uuid4())
    new_event, old_event = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(_row("recs_served", source="server", rec_request_id=req,
                props={"event_ids": [old_event, new_event], "discovery_ids": [new_event]}))
    for anon in ("a", "b", "c", "d"):
        db.add(_row("feed_impression", surface=surface, position=0, event_id=old_event, rec_request_id=req, anonymous_id=anon))
        db.add(_row("feed_impression", surface=surface, position=1, event_id=new_event, rec_request_id=req, anonymous_id=anon))
    # The same impression sent twice counts once.
    db.add(_row("feed_impression", surface=surface, position=0, event_id=old_event, rec_request_id=req, anonymous_id="a"))
    db.add(_row("event_clicked", surface=surface, position=1, event_id=new_event, rec_request_id=req, anonymous_id="a"))
    db.add(_row("search_executed", anonymous_id="s1", props={"query": f"{surface} karaoke", "results_count": 0}))
    await db.commit()

    admin_h, _ = await make_user(db, role="admin")
    r = await client.get("/api/admin/data-health", headers=admin_h, params={"days": 7})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["events_per_day"]) == 8 and d["events_per_day"][-1]["client"] >= 10
    assert d["ingestion"]["sample"] >= 10 and d["ingestion"]["p50_seconds"] is not None
    mine = {p["position"]: p for p in d["clicks_by_position"][surface]}
    assert (mine[0]["impressions"], mine[0]["clicks"]) == (1, 0)   # one feed load, deduplicated
    assert (mine[1]["impressions"], mine[1]["clicks"], mine[1]["ctr"]) == (1, 1, 1.0)
    assert d["discovery_slots"]["discovery"]["clicks"] >= 1
    assert any(s["query"] == f"{surface} karaoke" for s in d["zero_result_searches"])

    user_h, _ = await make_user(db)
    assert (await client.get("/api/admin/data-health", headers=user_h)).status_code == 403
