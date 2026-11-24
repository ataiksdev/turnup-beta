"""Synthetic activity for test/staging (docs/recommendations-spec.md).

    python -m app.cli seed-activity [--users 150] [--events 50] [--days 45]

Run after `seed`. Adds demo-only people (usernames start with `demo_`) who each have hidden
tastes (two favourite categories, a home area, a budget, how spontaneous they are, how often
they go out), plus events across Lagos and Abuja, then simulates their sessions over the past
`days`: feed impressions, clicks, views and time on page, saves, RSVPs, ticket choices,
orders, abandoned checkouts, shares, searches, check-ins and reviews. Because behaviour
follows those hidden tastes, the offline evaluation (`recs-eval`) has something real to find.

Never on production: it refuses unless DEBUG=true.
"""
import math
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.demo_data import SeedRefused
from app.models.activity import Activity
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.organizer import EventReview, TicketOrder, TicketTier
from app.models.social import Follow
from app.models.user import User
from app.services.rec_features import compute_event_features, compute_user_features, haversine_km

AREAS = [  # city, area, lat, lon
    ("Lagos", "Victoria Island", 6.4281, 3.4219), ("Lagos", "Lekki", 6.4474, 3.4700),
    ("Lagos", "Ikeja", 6.6018, 3.3515), ("Lagos", "Yaba", 6.5095, 3.3711),
    ("Lagos", "Surulere", 6.4969, 3.3534), ("Abuja", "Maitama", 9.0820, 7.4951),
    ("Abuja", "Wuse", 9.0765, 7.4651),
]
TITLES = {
    "music": ["Afrobeats Live", "Highlife Sundays", "Alté Sessions", "Amapiano Night", "Jazz on the Island"],
    "nightlife": ["Rooftop Rave", "Detty Night Out", "Silent Disco", "Club Takeover", "Pool Party"],
    "arts": ["Gallery Walk", "Poetry Slam", "Film Night", "Art Fair", "Theatre Night"],
    "food": ["Suya Festival", "Jollof Wars", "Brunch Club", "Food Truck Fiesta", "Wine Tasting"],
    "tech": ["Startup Mixer", "Fintech Meetup", "AI Builders Night", "Product Breakfast", "Hackathon"],
    "sports": ["5-a-side Cup", "Fun Run", "Watch Party", "Basketball 3x3", "Padel Social"],
    "comedy": ["Stand-up Night", "Comedy Roast", "Improv Show", "Open Mic Comedy", "Laugh Out Loud"],
    "wellness": ["Sunrise Yoga", "Sound Bath", "Mindful Morning", "Beach Workout", "Wellness Retreat"],
}
TAGS = {
    "music": ["afrobeats", "live", "amapiano", "jazz"], "nightlife": ["party", "dj", "rooftop", "rave"],
    "arts": ["gallery", "poetry", "film", "culture"], "food": ["food", "brunch", "street-food", "wine"],
    "tech": ["startups", "networking", "ai", "fintech"], "sports": ["football", "fitness", "running", "padel"],
    "comedy": ["standup", "laughs", "improv", "comedy"], "wellness": ["yoga", "mindfulness", "fitness", "outdoors"],
}
PRICES = [2000, 3500, 5000, 10000, 15000, 25000, 50000]
BUDGETS = {"free": 0, "budget": 5000, "mid": 20000, "any": 80000}


def _id() -> str:
    return str(uuid.uuid4())


async def run(users: int = 150, events: int = 50, days: int = 45, seed: int = 7) -> dict:
    if not settings.debug:
        raise SeedRefused("Refusing to add synthetic activity with DEBUG=false: that looks like production.")
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        cats = {c.slug: c for c in (await db.execute(select(Category))).scalars().all() if c.slug in TITLES}
        organizers = (await db.execute(select(User).where(User.role == "organizer",
                                                          User.is_deleted == False))).scalars().all()  # noqa: E712
        if not cats or not organizers:
            raise SeedRefused("Run `python -m app.cli seed` first (needs the demo categories and organizers).")
        if (await db.execute(select(User.id).where(User.username.like("demo\\_%", escape="\\")).limit(1))).first():
            raise SeedRefused("Synthetic activity is already there (users named demo_*).")

        # ── Events ──────────────────────────────────────────────────────────────
        evs: list[Event] = []
        tiers: dict[str, TicketTier] = {}
        for i in range(events):
            slug = rng.choice(list(cats))
            city, area, lat, lon = rng.choice(AREAS)
            start = now + timedelta(days=rng.uniform(-days * 0.8, 30), hours=rng.choice([10, 14, 18, 20, 21]) - 12)
            free = rng.random() < 0.35
            price = 0 if free else rng.choice(PRICES)
            e = Event(
                id=_id(), title=f"{rng.choice(TITLES[slug])} · {area}", slug=f"demo-{i}-{uuid.uuid4().hex[:6]}",
                description=f"A demo {cats[slug].name.lower()} event in {area}. " * 3,
                venue_name=f"{area} Hall", address=f"{rng.randint(1, 200)} {area} Road", city=city, country="NG",
                latitude=lat + rng.uniform(-0.02, 0.02), longitude=lon + rng.uniform(-0.02, 0.02),
                start_date=start, end_date=start + timedelta(hours=rng.choice([3, 4, 6])),
                is_free=free, price_min=price or None, price_max=(price * 2 if price else None),
                category_id=cats[slug].id, tags=",".join(rng.sample(TAGS[slug], 2)),
                host_id=rng.choice(organizers).id, status="published", created_via="demo",
                created_at=min(start - timedelta(days=rng.uniform(5, 35)), now - timedelta(hours=1)),
            )
            evs.append(e)
            db.add(e)
            if not free:
                t = TicketTier(id=_id(), event_id=e.id, name="Regular", price=price,
                               quantity=rng.choice([80, 150, 300]), quantity_sold=0, max_per_order=6)
                tiers[e.id] = t
                db.add(t)
        await db.flush()
        cat_of = {e.id: next(s for s, c in cats.items() if c.id == e.category_id) for e in evs}

        # ── People ──────────────────────────────────────────────────────────────
        people = []
        for i in range(users):
            city, area, lat, lon = rng.choice(AREAS)
            favs = rng.sample(list(cats), 2)
            budget = rng.choices(list(BUDGETS), weights=[2, 3, 3, 1])[0]
            onboarded = rng.random() < 0.7
            consent = rng.random() < 0.4
            u = User(
                id=_id(), username=f"demo_{i:03d}_{uuid.uuid4().hex[:4]}", email=f"demo{i}_{uuid.uuid4().hex[:4]}@demo.turnup.ng",
                full_name=f"Demo Person {i}", role="attendee", is_active=True, city=city,
                category_preferences=",".join(favs) if onboarded else None, onboarding_completed=onboarded,
                price_sensitivity=budget if onboarded else None,
                profiling_consent=consent, profiling_consent_at=now - timedelta(days=days) if consent else None,
                birth_year=rng.randint(1975, 2006) if rng.random() < 0.6 else None,
                gender=rng.choice(["female", "male", "non_binary", "prefer_not_to_say"]) if rng.random() < 0.5 else None,
                created_at=now - timedelta(days=days + rng.uniform(0, 30)),
            )
            db.add(u)
            people.append(dict(user=u, favs=favs, lat=lat, lon=lon, budget=BUDGETS[budget],
                               spont=rng.random(), rate=rng.uniform(0.5, 5), device=f"demo-dev-{uuid.uuid4().hex[:12]}",
                               platform=rng.choice(["web", "android", "android", "android"])))
        await db.flush()
        for p in people:
            same_taste = [q for q in people if q is not p and set(q["favs"]) & set(p["favs"])]
            for q in rng.sample(same_taste, min(len(same_taste), rng.randint(0, 6))):
                db.add(Follow(follower_id=p["user"].id, following_id=q["user"].id))
        await db.flush()

        # ── Behaviour ───────────────────────────────────────────────────────────
        def appeal(p, e: Event, at: datetime) -> float:
            taste = 1.0 if cat_of[e.id] in p["favs"] else 0.12
            place = math.exp(-haversine_km(p["lat"], p["lon"], e.latitude, e.longitude) / 12)
            price = e.price_min or 0
            money = 1.0 if price <= max(p["budget"], 1) * 1.2 else 0.25
            hours = (e.start_date - at).total_seconds() / 3600
            timing = (0.6 + 0.8 * p["spont"]) if hours < 48 else (1.3 - 0.6 * p["spont"])
            return min(taste * (0.3 + 0.7 * place) * money * timing, 1.0)

        acts: list[Activity] = []
        committed: dict[tuple[str, str], str] = {}
        counts = {"orders": 0, "saves": 0, "rsvps": 0}

        def log(p, name, at, **kw):
            acts.append(Activity(name=name, source=kw.pop("source", "client"), occurred_at=at, received_at=at,
                                 user_id=p["user"].id, anonymous_id=p["device"], session_id=kw.pop("session", None),
                                 platform=p["platform"], app_version="0.1.0", geo_city=p["user"].city,
                                 client_id=_id() if kw.get("source", "client") == "client" else None, **kw))

        for p in people:
            for d in range(days, 0, -1):
                if rng.random() > p["rate"] / 7:
                    continue
                at = now - timedelta(days=d) + timedelta(hours=rng.choice([8, 12, 17, 19, 20, 21, 22]) - 1,
                                                         minutes=rng.randint(0, 59))
                session = uuid.uuid4().hex
                log(p, "session_started", at, session=session,
                    props={"entry_point": rng.choice(["direct", "direct", "link"]), "local_hour": (at.hour + 1) % 24})
                live = [e for e in evs if e.created_at <= at < e.start_date]
                if not live:
                    continue
                if rng.random() < 0.25:
                    q = cats[rng.choice(p["favs"])].name
                    found = [e for e in live if cats[cat_of[e.id]].name == q]
                    log(p, "search_executed", at, session=session, surface="search",
                        props={"query": q.lower(), "results_count": len(found)})
                shown = rng.sample(live, min(len(live), 8))
                for pos, e in enumerate(shown):
                    t = at + timedelta(seconds=10 * pos)
                    log(p, "feed_impression", t, session=session, event_id=e.id, surface="for_you", position=pos)
                    a = appeal(p, e, t)
                    if rng.random() > 0.04 + 0.45 * a:
                        continue
                    log(p, "event_clicked", t, session=session, event_id=e.id, surface="for_you", position=pos)
                    log(p, "event_viewed", t, session=session, event_id=e.id, surface="for_you", position=pos,
                        props={"days_until_event": round((e.start_date - t).total_seconds() / 86400, 1)})
                    log(p, "event_dwell_ended", t + timedelta(seconds=40), session=session, event_id=e.id,
                        props={"dwell_seconds": int(5 + 80 * a * rng.random()), "scroll_depth_pct": int(30 + 70 * a)})
                    key = (p["user"].id, e.id)
                    if rng.random() < 0.06 * a:
                        log(p, "event_shared", t, session=session, event_id=e.id, props={"share_channel": "native"})
                    if key not in committed and rng.random() < 0.3 * a:
                        db.add(EventSave(id=_id(), user_id=key[0], event_id=e.id, created_at=t))
                        log(p, "event_saved", t, source="server", event_id=e.id)
                        committed[key] = "saved"
                        counts["saves"] += 1
                        e.saves_count += 1
                    tier = tiers.get(e.id)
                    if tier and rng.random() < 0.5 * a:
                        log(p, "ticket_drawer_opened", t, session=session, event_id=e.id,
                            props={"lowest_available_price": tier.price})
                        qty = rng.choice([1, 1, 2, 3])
                        log(p, "ticket_tier_selected", t, session=session, event_id=e.id,
                            props={"tier_id": tier.id, "unit_price": tier.price, "quantity": qty})
                        if committed.get(key) != "going" and rng.random() < 0.55 * a and tier.quantity_sold + qty <= tier.quantity:
                            o = TicketOrder(id=_id(), user_id=key[0], event_id=e.id, tier_id=tier.id, quantity=qty,
                                            unit_price=tier.price, total_price=tier.price * qty, status="confirmed",
                                            ticket_code=_id(), payment_reference=f"demo-{uuid.uuid4().hex[:12]}",
                                            created_at=t)
                            if e.end_date < now and rng.random() < 0.8:
                                o.checked_in_at = e.start_date + timedelta(minutes=rng.randint(0, 90))
                                o.admitted_count = qty
                            db.add(o)
                            tier.quantity_sold += qty
                            log(p, "order_completed", t, source="server", event_id=e.id,
                                props={"total_amount": tier.price * qty, "ticket_count": qty})
                            if committed.get(key) is None or committed.get(key) == "saved":
                                db.add(EventAttendee(id=_id(), user_id=key[0], event_id=e.id, status="going", created_at=t))
                                e.attendees_count += 1
                            committed[key] = "going"
                            counts["orders"] += 1
                            if o.checked_in_at and rng.random() < 0.35:
                                db.add(EventReview(id=_id(), event_id=e.id, user_id=key[0],
                                                   rating=max(1, min(5, round(3 + 2 * a + rng.uniform(-1, 1)))),
                                                   created_at=e.end_date + timedelta(hours=12)))
                        else:
                            log(p, "checkout_abandoned", t, session=session, event_id=e.id,
                                props={"step": rng.choice(["tier_select", "payment"]), "cart_value": tier.price * qty})
                    elif not tier and committed.get(key) != "going" and rng.random() < 0.35 * a:
                        status = "going" if rng.random() < 0.7 else "interested"
                        if committed.get(key) in (None, "saved"):
                            db.add(EventAttendee(id=_id(), user_id=key[0], event_id=e.id, status=status, created_at=t))
                            if status == "going":
                                e.attendees_count += 1
                            else:
                                e.interested_count += 1
                            committed[key] = status if status == "going" else committed.get(key, "interested")
                            counts["rsvps"] += 1
                            log(p, "rsvp_changed", t, source="server", event_id=e.id, props={"status": status})
        db.add_all(acts)
        await db.commit()

        await compute_event_features(db)
        await compute_user_features(db)
        return {"users": users, "events": events, "activity_rows": len(acts), **counts}
