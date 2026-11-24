"""Alerts for saved events ("almost sold out", "price dropped") and ranker-based weekend picks."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.activity import EventFeatures
from app.models.event import EventAttendee, EventSave
from app.models.organizer import TicketTier
from app.models.social import Notification
from app.models.user import User
from app.services.nudges import send_event_alerts
from tests.test_recommendations import NOW, make_event, make_user


async def _tier(db, eid, price, **kw):
    t = TicketTier(id=str(uuid.uuid4()), event_id=eid, name="Regular", price=price, is_active=True, **kw)
    db.add(t)
    await db.commit()
    return t


async def _save(client, h, eid):
    r = await client.post(f"/api/events/{eid}/save", headers=h)
    assert r.json() == {"saved": True}


async def _alerts(db, uid):
    return (await db.execute(select(Notification).where(
        Notification.user_id == uid, Notification.type.in_(("price_drop", "almost_sold_out")))
        .order_by(Notification.created_at))).scalars().all()


async def _almost_sold_out(db, eid, left=5):
    db.add(EventFeatures(event_id=eid, sell_through_pct=0.9, remaining_tickets=left))
    await db.commit()


async def test_price_drop_alert_once_per_drop(client, db):
    _, host = await make_user(db, role="organizer")
    h, uid = await make_user(db)
    eid = await make_event(db, host, is_free=False)
    tier = await _tier(db, eid, 10000)
    await _save(client, h, eid)
    save = (await db.execute(select(EventSave).where(EventSave.user_id == uid))).scalar_one()
    assert save.price_seen == 10000

    await send_event_alerts(db)
    assert await _alerts(db, uid) == []          # unchanged

    tier.price = 9500                               # only 5% off: not worth a message
    await db.commit()
    await send_event_alerts(db)
    assert await _alerts(db, uid) == []

    tier.price = 7000
    await db.commit()
    await send_event_alerts(db)
    alerts = await _alerts(db, uid)
    assert len(alerts) == 1 and alerts[0].type == "price_drop" and alerts[0].reference_id == eid
    assert "₦7,000" in alerts[0].body and "₦10,000" in alerts[0].body
    await db.refresh(save)
    assert save.price_seen == 7000
    await send_event_alerts(db)
    assert len(await _alerts(db, uid)) == 1        # same price: nothing new


async def test_almost_sold_out_alerts_once_and_skips_people_already_going(client, db):
    _, host = await make_user(db, role="organizer")
    h, uid = await make_user(db)
    h2, going = await make_user(db)
    eid = await make_event(db, host)
    await _save(client, h, eid)
    await _save(client, h2, eid)
    db.add(EventAttendee(user_id=going, event_id=eid, status="going"))
    await _almost_sold_out(db, eid, left=1)

    await send_event_alerts(db)
    await send_event_alerts(db, now=NOW() + timedelta(days=2))
    alerts = await _alerts(db, uid)
    assert len(alerts) == 1 and alerts[0].type == "almost_sold_out" and "Only 1 ticket left" in alerts[0].body
    assert await _alerts(db, going) == []


async def test_limits_opt_out_hidden_and_soon_events(client, db):
    _, host = await make_user(db, role="organizer")
    _, hidden_host = await make_user(db, role="organizer")
    h, uid = await make_user(db)
    events = [await make_event(db, host, start=NOW() + timedelta(days=d)) for d in (2, 3, 4, 5, 6)]
    hidden = await make_event(db, hidden_host, start=NOW() + timedelta(days=1))
    soon = await make_event(db, host, start=NOW() + timedelta(hours=1))
    for eid in events + [hidden, soon]:
        await _save(client, h, eid)
        await _almost_sold_out(db, eid)
    await client.post("/api/hidden", headers=h, json={"kind": "organizer", "target_id": hidden_host})

    await send_event_alerts(db)
    await send_event_alerts(db)                      # same day: daily limit
    alerts = await _alerts(db, uid)
    assert [a.reference_id for a in alerts] == [events[0]]   # soonest first; hidden and too-soon skipped

    # A run on each of the next four days: one a day, then the weekly limit of 3 stops it.
    for day in (1, 2, 3, 4):
        await send_event_alerts(db, now=NOW() + timedelta(days=day, minutes=1))
    assert [a.reference_id for a in await _alerts(db, uid)] == events[:3]

    # Turning alerts off stops them.
    h2, other = await make_user(db)
    await _save(client, h2, events[-1])
    r = await client.patch("/api/auth/preferences", headers=h2, json={"event_alerts": False})
    assert r.status_code == 200 and r.json()["event_alerts"] is False
    await send_event_alerts(db)
    assert await _alerts(db, other) == []


async def test_members_only_and_sold_out_tiers_dont_count_as_the_price(db):
    from app.services.nudges import lowest_prices
    from app.models.event import Event
    _, host = await make_user(db, role="organizer")
    eid = await make_event(db, host, is_free=False, price_min=999)
    await _tier(db, eid, 1000, members_only=True)
    await _tier(db, eid, 2000, quantity=10, quantity_sold=10)
    await _tier(db, eid, 5000)
    await _tier(db, eid, 3000, sale_start=NOW() + timedelta(days=1))
    event = await db.get(Event, eid)
    assert (await lowest_prices(db, [event]))[eid] == 5000
    free = await db.get(Event, await make_event(db, host, is_free=True))
    assert (await lowest_prices(db, [free]))[free.id] == 0


async def test_weekend_picks_come_from_the_ranker_and_skip_hidden_events(client, db):
    from app.services.picks import weekend_picks, weekend_window
    _, host = await make_user(db, role="organizer")
    h, uid = await make_user(db, city="Lagos")
    start, _ = weekend_window()
    when = max(start, datetime.now(timezone.utc)) + timedelta(hours=20)
    shown = await make_event(db, host, start=when)
    hidden = await make_event(db, host, start=when + timedelta(hours=1))
    elsewhere = await make_event(db, host, start=when, city="Kano")
    later = await make_event(db, host, start=when + timedelta(days=10))
    await client.post("/api/hidden", headers=h, json={"kind": "event", "target_id": hidden})
    user = await db.get(User, uid)
    picks = await weekend_picks(db, user, limit=50)
    ids = [e["id"] for e in picks["events"]]
    assert shown in ids
    assert hidden not in ids and elsewhere not in ids and later not in ids
    assert all(e["because"] for e in picks["events"])
