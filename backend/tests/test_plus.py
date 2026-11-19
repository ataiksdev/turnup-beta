"""Turnup+ and Venue Pro subscriptions, member perks, venue-hosted events and reviews
(docs/venues-spec.md 4.6-4.9)."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update

from app.models.event import Event, EventAttendee
from app.models.organizer import EventWaitlist, TicketOrder, TicketTier
from app.models.social import Notification
from app.models.user import User
from app.models.venue import ScheduledAlert, Subscription, Venue, VenueBooking, VenueFollow
from app.routers import events as events_router
from tests.test_venues import _no_rate_limits, book, live_venue, make_user, seeded, utcnow  # noqa: F401


async def make_plus(db, uid):
    await db.execute(update(User).where(User.id == uid).values(plus_until=utcnow() + timedelta(days=30)))
    await db.commit()


async def event_with_tier(db, host_id, *, price=0.0, members_only=False, tier_members_only=False,
                          presale_until=None, presale_then="open", fast_lane=False, quantity=None, **ev):
    eid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    now = utcnow()
    db.add(Event(id=eid, slug=f"e-{eid}", title=f"Party {eid[:5]}", description="d" * 30,
                 venue_name="Venue", address="1 Test Street", city="Lagos", country="NG",
                 start_date=ev.pop("start", now + timedelta(days=5)), end_date=ev.pop("end", now + timedelta(days=5, hours=3)),
                 host_id=host_id, status="published", review_status="approved", is_free=price == 0,
                 members_only=members_only, fast_lane_enabled=fast_lane, **ev))
    db.add(TicketTier(id=tid, event_id=eid, name="GA", price=price, quantity=quantity, max_per_order=10,
                      is_active=True, members_only=tier_members_only, plus_presale_ends_at=presale_until,
                      presale_then=presale_then))
    await db.commit()
    return eid, tid


async def checkout(client, h, eid, tid):
    with patch.object(events_router, "initialize_transaction", new=AsyncMock(return_value={})) as init:
        r = await client.post(f"/api/events/{eid}/tickets/checkout", json={"items": [{"tier_id": tid, "quantity": 1}]},
                              headers=h)
    return r, init


# ── Subscription lifecycle ─────────────────────────────────────────────────────

async def test_turnup_plus_subscription_lifecycle(client, db, seeded):
    from app.services.plus import handle_subscription_event
    h, uid = await make_user(db)
    plans = (await client.get("/api/plus/plans")).json()
    assert {p["code"] for p in plans["plans"]} == {"turnup_plus_monthly", "turnup_plus_annually"}
    assert len(plans["perks"]) == 10
    r = await client.post("/api/plus/subscribe", headers=h, json={"plan_code": "turnup_plus_monthly"})
    assert r.status_code == 200, r.text
    ref = r.json()["reference"]
    assert not (await client.get("/api/plus/me", headers=h)).json()["is_plus"]
    await client.post(f"/api/venue-payments/verify?reference={ref}", headers=h)
    me = (await client.get("/api/plus/me", headers=h)).json()
    assert me["is_plus"] and me["status"] == "active"
    # A second subscription is refused.
    assert (await client.post("/api/plus/subscribe", headers=h, json={"plan_code": "turnup_plus_monthly"})).status_code == 409

    sub = (await db.execute(select(Subscription).where(Subscription.reference == ref))).scalar_one()
    plan_code = "PLN_dev_monthly_150000"
    await db.execute(update(Subscription).where(Subscription.id == sub.id).values(paystack_customer_code="CUS_1"))
    await db.commit()
    await handle_subscription_event(db, "subscription.create", {
        "subscription_code": "SUB_1", "email_token": "tok", "plan": {"plan_code": plan_code},
        "customer": {"customer_code": "CUS_1"}})
    await handle_subscription_event(db, "invoice.payment_failed", {"subscription": {"subscription_code": "SUB_1"}})
    await db.commit()
    await db.refresh(sub)
    assert sub.status == "past_due" and sub.grace_until
    assert (await client.get("/api/plus/me", headers=h)).json()["is_plus"]  # grace period
    await handle_subscription_event(db, "subscription.disable", {"subscription_code": "SUB_1"})
    await db.commit()
    assert not (await client.get("/api/plus/me", headers=h)).json()["is_plus"]


async def test_venue_pro_raises_media_limit(client, db, seeded):
    v = await live_venue(client, db)
    base = f"/api/venue-portal/venues/{v['id']}"
    r = await client.post(f"{base}/pro", headers=v["owner_h"], json={"plan_code": "venue_pro_monthly"})
    assert r.status_code == 200, r.text
    await client.post(f"/api/venue-payments/verify?reference={r.json()['reference']}", headers=v["owner_h"])
    detail = (await client.get(base, headers=v["owner_h"])).json()
    assert detail["pro"]["active"] and detail["limits"] == {"photos": 12, "videos": 5, "team_seats": 10}
    for i in range(11):
        assert (await client.post(f"{base}/media", headers=v["owner_h"], json={
            "kind": "photo", "url": f"https://img.example.com/p{i}.jpg"})).status_code == 201
    assert (await client.post(f"{base}/media", headers=v["owner_h"], json={
        "kind": "photo", "url": "https://img.example.com/x.jpg"})).status_code == 409
    assert (await client.get(f"{base}/analytics", headers=v["owner_h"])).status_code == 200
    # Pro lapses: nothing deleted, photos past 6 hidden publicly.
    await db.execute(update(Venue).where(Venue.id == v["id"]).values(pro_until=utcnow() - timedelta(days=1), is_pro=False))
    await db.commit()
    page = (await client.get(f"/api/venues/{v['slug']}")).json()
    assert len([m for m in page["media"] if m["kind"] == "photo"]) == 6
    detail = (await client.get(base, headers=v["owner_h"])).json()
    assert len(detail["media"]) == 12 and sum(m["hidden"] for m in detail["media"]) == 6
    assert (await client.get(f"{base}/analytics", headers=v["owner_h"])).status_code == 402


# ── Member perks ───────────────────────────────────────────────────────────────

async def test_members_only_and_presale(client, db, seeded):
    _, host = await make_user(db, "organizer")
    h, uid = await make_user(db)
    eid, tid = await event_with_tier(db, host, members_only=True)
    r, _ = await checkout(client, h, eid, tid)
    assert r.status_code == 402
    await make_plus(db, uid)
    r, _ = await checkout(client, h, eid, tid)
    assert r.status_code == 200

    h2, uid2 = await make_user(db)
    eid, tid = await event_with_tier(db, host, presale_until=utcnow() + timedelta(days=1))
    r, _ = await checkout(client, h2, eid, tid)
    assert r.status_code == 402 and "presale" in r.json()["detail"]
    await db.execute(update(TicketTier).where(TicketTier.id == tid).values(plus_presale_ends_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
    r, _ = await checkout(client, h2, eid, tid)
    assert r.status_code == 200  # opens to everyone afterwards
    eid, tid = await event_with_tier(db, host, presale_until=utcnow() - timedelta(minutes=1), presale_then="close")
    r, _ = await checkout(client, h, eid, tid)
    assert r.status_code == 400


async def test_priority_waitlist_and_fast_lane(client, db, seeded):
    host_h, host = await make_user(db, "organizer")
    eid, tid = await event_with_tier(db, host, fast_lane=True)
    regular_h, regular = await make_user(db)
    member_h, member = await make_user(db)
    await make_plus(db, member)
    db.add(EventWaitlist(event_id=eid, user_id=regular, position=1))
    db.add(EventWaitlist(event_id=eid, user_id=member, position=2))
    await db.commit()
    r = await client.post(f"/api/events/{eid}/waitlist/notify", headers=host_h, json={"count": 1})
    member_name = (await db.execute(select(User.username).where(User.id == member))).scalar_one()
    assert r.json()["notified"] == [member_name]

    r, _ = await checkout(client, member_h, eid, tid)
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == r.json()["order_ids"][0]))).scalar_one()
    r = await client.post(f"/api/events/{eid}/checkin", headers=host_h, json={"ticket_code": order.ticket_code})
    assert r.status_code == 200 and r.json()["fast_lane"] is True
    r, _ = await checkout(client, regular_h, eid, tid)
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == r.json()["order_ids"][0]))).scalar_one()
    r = await client.post(f"/api/events/{eid}/checkin", headers=host_h, json={"ticket_code": order.ticket_code})
    assert r.json()["fast_lane"] is False


async def test_ticket_transfer(client, db, seeded):
    _, host = await make_user(db, "organizer")
    eid, tid = await event_with_tier(db, host)
    h, uid = await make_user(db)
    _, friend = await make_user(db)
    friend_name = (await db.execute(select(User.username).where(User.id == friend))).scalar_one()
    r, _ = await checkout(client, h, eid, tid)
    oid = r.json()["order_ids"][0]
    assert (await client.post(f"/api/tickets/{oid}/transfer", headers=h, json={"to_username": friend_name})).status_code == 402
    await make_plus(db, uid)
    old_code = (await db.execute(select(TicketOrder.ticket_code).where(TicketOrder.id == oid))).scalar_one()
    r = await client.post(f"/api/tickets/{oid}/transfer", headers=h, json={"to_username": "@" + friend_name})
    assert r.status_code == 200, r.text
    order = (await db.execute(select(TicketOrder).where(TicketOrder.id == oid).execution_options(populate_existing=True))).scalar_one()
    assert order.user_id == friend and order.ticket_code != old_code
    await db.execute(update(Event).where(Event.id == eid).values(allow_ticket_transfers=False))
    await db.commit()
    r, _ = await checkout(client, h, eid, tid)
    assert (await client.post(f"/api/tickets/{r.json()['order_ids'][0]}/transfer", headers=h,
                              json={"to_username": friend_name})).status_code == 409


async def test_member_deals_claim_and_redeem(client, db, seeded):
    v = await live_venue(client, db)
    base = f"/api/venue-portal/venues/{v['id']}"
    deal = (await client.post(f"{base}/deals", headers=v["owner_h"], json={
        "title": "Free entry before 11pm", "kind": "free_entry"})).json()
    h, uid = await make_user(db)
    assert (await client.post(f"/api/deals/{deal['id']}/claim", headers=h)).status_code == 402
    await make_plus(db, uid)
    code = (await client.post(f"/api/deals/{deal['id']}/claim", headers=h)).json()["code"]
    assert (await client.post(f"/api/deals/{deal['id']}/claim", headers=h)).json()["code"] == code  # same unused code
    r = await client.post(f"{base}/deals/redeem", headers=v["owner_h"], json={"code": code})
    assert r.json()["ok"] is True
    r = await client.post(f"{base}/deals/redeem", headers=v["owner_h"], json={"code": code})
    assert r.json() == {**r.json(), "ok": False, "reason": "already_used"}
    assert (await client.post(f"/api/deals/{deal['id']}/claim", headers=h)).status_code == 409  # max 1 per member
    mine = (await client.get("/api/me/deals", headers=h)).json()
    assert mine[0]["where"]["type"] == "venue" and mine[0]["redeemed_at"]


async def test_early_alerts_for_members(client, db, seeded):
    from app.services.alerts import announce_event, send_due_alerts
    v = await live_venue(client, db)
    _, member = await make_user(db)
    _, regular = await make_user(db)
    await make_plus(db, member)
    for uid in (member, regular):
        db.add(VenueFollow(user_id=uid, venue_id=v["id"]))
    await db.commit()
    r = await client.post(f"/api/venue-portal/venues/{v['id']}/events", headers=v["owner_h"], json={
        "title": "Friday Night Live", "description": "Live band and DJ all night long at the venue.",
        "start_date": (utcnow() + timedelta(days=9)).isoformat(),
        "end_date": (utcnow() + timedelta(days=9, hours=5)).isoformat()})
    assert r.status_code == 201 and r.json()["review_status"] == "pending"
    ev = (await db.execute(select(Event).where(Event.id == r.json()["id"]))).scalar_one()
    assert ev.host_venue_id == v["id"] and ev.venue_name != "venue"  # taken from the venue
    out = await announce_event(db, ev)  # what admin approval triggers
    await db.commit()
    assert out == {"now": 1, "later": 1}
    assert (await db.execute(select(Notification).where(
        Notification.user_id == member, Notification.reference_id == ev.id))).scalar_one()
    alert = (await db.execute(select(ScheduledAlert).where(ScheduledAlert.user_id == regular))).scalar_one()
    assert alert.send_at.replace(tzinfo=timezone.utc) if alert.send_at.tzinfo is None else alert.send_at
    await db.execute(update(ScheduledAlert).where(ScheduledAlert.id == alert.id).values(send_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
    assert await send_due_alerts(db) == 1
    # Venue managers manage the venue's events through the normal event endpoints.
    r = await client.post(f"/api/events/{ev.id}/tickets", headers=v["owner_h"], json={"name": "GA", "price": 0})
    assert r.status_code == 201


async def test_reviews_both_kinds(client, db, seeded):
    from app.services.venue_booking import run_booking_sweeps
    v = await live_venue(client, db)
    b = await book(client, db, v, days_ahead=3)
    r = await client.post(f"/api/venue-bookings/{b['booking_id']}/review", headers=b["org_h"], json={"rating": 5})
    assert r.status_code == 409  # not completed yet
    await db.execute(update(VenueBooking).where(VenueBooking.id == b["booking_id"]).values(
        starts_at=utcnow() - timedelta(days=4), ends_at=utcnow() - timedelta(days=3)))
    await db.commit()
    await run_booking_sweeps(db)
    r = await client.post(f"/api/venue-bookings/{b['booking_id']}/review", headers=b["org_h"],
                          json={"rating": 4, "body": "Great hall"})
    assert r.status_code == 200

    _, host = await make_user(db, "organizer")
    guest_h, guest = await make_user(db)
    eid, tid = await event_with_tier(db, host, venue_id=v["id"], start=utcnow() - timedelta(days=1),
                                     end=utcnow() - timedelta(hours=20))
    db.add(TicketOrder(user_id=guest, event_id=eid, tier_id=tid, quantity=1, unit_price=0, total_price=0,
                       status="confirmed", ticket_code=str(uuid.uuid4()), checked_in_at=utcnow() - timedelta(days=1)))
    await db.commit()
    stranger_h, _ = await make_user(db)
    assert (await client.post(f"/api/events/{eid}/venue-review", headers=stranger_h, json={"rating": 2})).status_code == 403
    assert (await client.post(f"/api/events/{eid}/venue-review", headers=guest_h, json={"rating": 3})).status_code == 200
    page = (await client.get(f"/api/venues/{v['slug']}")).json()
    assert page["rating_organizers"] == 4.0 and page["rating_guests"] == 3.0
    reviews = (await client.get(f"/api/venues/{v['slug']}/reviews", params={"kind": "guest"})).json()
    assert len(reviews) == 1 and reviews[0]["kind"] == "guest"


async def test_venue_hosted_ticket_checkout_is_split(client, db, seeded):
    v = await live_venue(client, db)
    ev_id = (await client.post(f"/api/venue-portal/venues/{v['id']}/events", headers=v["owner_h"], json={
        "title": "Rooftop Session", "description": "Sunset sounds on the rooftop with friends.",
        "start_date": (utcnow() + timedelta(days=9)).isoformat(),
        "end_date": (utcnow() + timedelta(days=9, hours=5)).isoformat()})).json()["id"]
    await db.execute(update(Event).where(Event.id == ev_id).values(status="published", review_status="approved"))
    tid = str(uuid.uuid4())
    db.add(TicketTier(id=tid, event_id=ev_id, name="GA", price=10_000, max_per_order=5, is_active=True))
    await db.commit()
    from app.services.settings import set_ticket_fee_percent
    await set_ticket_fee_percent(db, 5.0)  # other tests change the shared settings row
    await db.commit()
    h, _ = await make_user(db)
    r, init = await checkout(client, h, ev_id, tid)
    assert r.status_code == 200, r.text
    kwargs = init.await_args.kwargs
    assert kwargs["subaccount"].startswith("ACCT_") and kwargs["bearer"] == "subaccount"
    assert kwargs["transaction_charge"] == 50_000  # 5% ticket fee of N10,000


async def test_wrapped_and_weekend_picks(client, db, seeded):
    h, uid = await make_user(db, city="Lagos")
    _, host = await make_user(db, "organizer")
    year = utcnow().year - 1
    eid, _ = await event_with_tier(db, host, start=datetime(year, 6, 5, 20, tzinfo=timezone.utc),
                                   end=datetime(year, 6, 5, 23, tzinfo=timezone.utc))
    db.add(EventAttendee(user_id=uid, event_id=eid, status="going"))
    await db.commit()
    w = (await client.get(f"/api/me/wrapped/{year}", headers=h)).json()
    assert w["events_attended"] == 1 and w["full"] is False
    await make_plus(db, uid)
    w = (await client.get(f"/api/me/wrapped/{year}", headers=h)).json()
    assert w["full"] is True and w["busiest_month"] == "June"
    img = await client.get(f"/api/me/wrapped/{year}/image.png", headers=h)
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    assert (await client.get(f"/api/me/wrapped/{utcnow().year + 1}", headers=h)).status_code == 404

    from app.services.picks import weekend_window
    start, _ = weekend_window()
    await event_with_tier(db, host, start=start + timedelta(days=1, hours=20), end=start + timedelta(days=1, hours=23))
    picks = (await client.get("/api/me/weekend-picks", headers=h)).json()
    assert picks["events"] and picks["city"] == "Lagos"
