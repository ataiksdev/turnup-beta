#!/usr/bin/env python3
"""
Turnup platform seeder — populates auth-service and events-service databases
with realistic demo data. Run after services are up:

    python scripts/seed.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Ensure service packages are importable ──────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

USERS = [
    {"username": "nova_beats", "full_name": "Nova Williams", "email": "nova@turnup.dev",
     "bio": "DJ & music producer. Making every weekend unforgettable. 🎧",
     "location": "New York, NY", "is_verified": True,
     "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=nova"},
    {"username": "jxmie", "full_name": "Jamie Chen", "email": "jamie@turnup.dev",
     "bio": "Festival addict. I've been to 50+ events this year.",
     "location": "Los Angeles, CA", "is_verified": True,
     "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=jamie"},
    {"username": "skyler_vibe", "full_name": "Skyler Davis", "email": "skyler@turnup.dev",
     "bio": "Event curator. Art meets sound meets community.",
     "location": "Chicago, IL", "is_verified": False,
     "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=skyler"},
    {"username": "reina_mx", "full_name": "Reina Morales", "email": "reina@turnup.dev",
     "bio": "Promoter | Dancer | Tacos enthusiast 🌮",
     "location": "Miami, FL", "is_verified": True,
     "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=reina"},
    {"username": "kobe_events", "full_name": "Kobe Thompson", "email": "kobe@turnup.dev",
     "bio": "Bringing culture to the city, one event at a time.",
     "location": "Atlanta, GA", "is_verified": False,
     "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=kobe"},
]

CATEGORIES = [
    {"name": "Music", "slug": "music", "icon": "🎵", "color": "#F97316"},
    {"name": "Arts & Culture", "slug": "arts", "icon": "🎨", "color": "#A855F7"},
    {"name": "Food & Drink", "slug": "food", "icon": "🍕", "color": "#EF4444"},
    {"name": "Sports & Fitness", "slug": "sports", "icon": "⚽", "color": "#22C55E"},
    {"name": "Nightlife", "slug": "nightlife", "icon": "🌙", "color": "#3B82F6"},
    {"name": "Tech", "slug": "tech", "icon": "💻", "color": "#06B6D4"},
    {"name": "Comedy", "slug": "comedy", "icon": "😂", "color": "#EAB308"},
    {"name": "Wellness", "slug": "wellness", "icon": "🧘", "color": "#10B981"},
]

def future(days: int, hour: int = 20) -> datetime:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def make_events(user_ids: list[str], category_ids: dict) -> list[dict]:
    music_id = category_ids.get("music")
    nightlife_id = category_ids.get("nightlife")
    arts_id = category_ids.get("arts")
    food_id = category_ids.get("food")
    tech_id = category_ids.get("tech")
    sports_id = category_ids.get("sports")
    comedy_id = category_ids.get("comedy")
    wellness_id = category_ids.get("wellness")

    return [
        {
            "title": "Bass Collective: Underground Sessions",
            "description": "The city's most immersive underground bass music experience returns. Four rooms, eight DJs, and a sound system that will shake your soul. From liquid drum & bass to neurofunk, we cover the full spectrum of electronic music culture. This is not just a party — it's a movement.",
            "cover_image": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800",
            "venue_name": "Avant Gardner", "address": "140 Stewart Ave", "city": "New York",
            "country": "US", "latitude": 40.7033, "longitude": -73.9343,
            "start_date": future(3), "end_date": future(3, 4),
            "is_free": False, "price_min": 25, "price_max": 45, "currency": "USD",
            "ticket_url": "https://tickets.example.com/bass-collective",
            "capacity": 800, "attendees_count": 412, "interested_count": 289,
            "saves_count": 156, "is_featured": True, "is_trending": True,
            "status": "published", "tags": "bass,electronic,dnb,nightlife",
            "host_idx": 0, "category_id": nightlife_id,
        },
        {
            "title": "Afrobeats & Amapiano Festival",
            "description": "Celebrate African music excellence at the most anticipated festival of the season. Grammy-nominated artists, local legends, and rising stars unite for a 10-hour celebration of Afrobeats, Amapiano, Afro-house, and Afropop. Food vendors, fashion stalls, and interactive experiences throughout the day.",
            "cover_image": "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800",
            "venue_name": "Citi Field Parking Lot", "address": "126-01 Roosevelt Ave", "city": "New York",
            "country": "US", "latitude": 40.7571, "longitude": -73.8458,
            "start_date": future(7, 14), "end_date": future(7, 23),
            "is_free": False, "price_min": 55, "price_max": 120, "currency": "USD",
            "ticket_url": "https://tickets.example.com/afrobeats-festival",
            "capacity": 5000, "attendees_count": 2341, "interested_count": 1876,
            "saves_count": 923, "is_featured": True, "is_trending": True,
            "status": "published", "tags": "afrobeats,amapiano,festival,africa,music",
            "host_idx": 1, "category_id": music_id,
        },
        {
            "title": "Rooftop Sunset Sessions",
            "description": "Watch the city transform under a golden sky while house music fills the air. Our monthly rooftop series is back, featuring resident DJs and a curated cocktail menu. Dress code: smart casual. Limited capacity — book early.",
            "cover_image": "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=800",
            "venue_name": "The Skylark", "address": "200 W 39th St", "city": "New York",
            "country": "US", "latitude": 40.7536, "longitude": -73.9932,
            "start_date": future(5, 18), "end_date": future(5, 23),
            "is_free": False, "price_min": 20, "price_max": 35, "currency": "USD",
            "capacity": 200, "attendees_count": 178, "interested_count": 94,
            "saves_count": 67, "is_featured": True, "is_trending": False,
            "status": "published", "tags": "rooftop,house,sunset,cocktails",
            "host_idx": 0, "category_id": nightlife_id,
        },
        {
            "title": "Street Art & Mural Festival",
            "description": "A four-day open-air art festival celebrating urban creativity. Watch 30+ artists transform blank walls into breathtaking murals in real time. Includes live painting demos, panel discussions with leading street artists, a curated market, and interactive installations for all ages.",
            "cover_image": "https://images.unsplash.com/photo-1541414779317-a3cb69bf24d1?w=800",
            "venue_name": "Wynwood Walls", "address": "2520 NW 2nd Ave", "city": "Miami",
            "country": "US", "latitude": 25.8008, "longitude": -80.1993,
            "start_date": future(10, 11), "end_date": future(13, 20),
            "is_free": True, "price_min": None, "price_max": None, "currency": "USD",
            "capacity": None, "attendees_count": 892, "interested_count": 634,
            "saves_count": 211, "is_featured": True, "is_trending": True,
            "status": "published", "tags": "art,murals,street-art,free,culture",
            "host_idx": 2, "category_id": arts_id,
        },
        {
            "title": "Late Night Jazz & Cocktails",
            "description": "Immerse yourself in an evening of live jazz performance in an intimate speakeasy setting. Our house quartet performs standards and originals, while expert mixologists craft bespoke cocktails inspired by jazz legends. Limited seating — this one always sells out.",
            "cover_image": "https://images.unsplash.com/photo-1415201364774-f6f0bb35f28f?w=800",
            "venue_name": "The Blue Note", "address": "131 W 3rd St", "city": "New York",
            "country": "US", "latitude": 40.7300, "longitude": -74.0007,
            "start_date": future(4, 21), "end_date": future(4, 2),
            "is_free": False, "price_min": 30, "price_max": 30, "currency": "USD",
            "capacity": 120, "attendees_count": 98, "interested_count": 45,
            "saves_count": 38, "is_featured": False, "is_trending": False,
            "status": "published", "tags": "jazz,live-music,cocktails,intimate",
            "host_idx": 0, "category_id": music_id,
        },
        {
            "title": "Tech & Innovation Summit 2026",
            "description": "The Southeast's largest technology conference brings together founders, engineers, investors, and creatives for two days of keynotes, workshops, and unparalleled networking. Topics: AI, Web3, climate tech, fintech, and the future of work. Hackathon included.",
            "cover_image": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800",
            "venue_name": "Georgia World Congress Center", "address": "285 Andrew Young Intl Blvd NW",
            "city": "Atlanta", "country": "US", "latitude": 33.7590, "longitude": -84.3977,
            "start_date": future(21, 9), "end_date": future(22, 18),
            "is_free": False, "price_min": 99, "price_max": 499, "currency": "USD",
            "ticket_url": "https://tickets.example.com/tech-summit",
            "capacity": 3000, "attendees_count": 1456, "interested_count": 789,
            "saves_count": 345, "is_featured": True, "is_trending": True,
            "status": "published", "tags": "tech,ai,startup,networking,innovation",
            "host_idx": 4, "category_id": tech_id,
        },
        {
            "title": "Morning Yoga in the Park",
            "description": "Start your Sunday right with a free community yoga session in Piedmont Park. All levels welcome — bring your mat, water, and good vibes. Led by certified instructors from local studios. Post-session smoothie meetup at the nearby farmer's market.",
            "cover_image": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800",
            "venue_name": "Piedmont Park", "address": "1320 Monroe Dr NE", "city": "Atlanta",
            "country": "US", "latitude": 33.7867, "longitude": -84.3732,
            "start_date": future(6, 8), "end_date": future(6, 10),
            "is_free": True, "price_min": None, "price_max": None,
            "capacity": 150, "attendees_count": 87, "interested_count": 134,
            "saves_count": 56, "is_featured": False, "is_trending": False,
            "status": "published", "tags": "yoga,wellness,free,outdoor,fitness",
            "host_idx": 4, "category_id": wellness_id,
        },
        {
            "title": "Tacos & Tequila Festival",
            "description": "The ultimate celebration of Mexican food culture is coming to Miami! Over 40 taco vendors, 25 tequila and mezcal brands, live mariachi, lucha libre exhibitions, and cooking demos from Michelin-starred chefs. Three days of pure flavor.",
            "cover_image": "https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=800",
            "venue_name": "Bayfront Park", "address": "301 Biscayne Blvd", "city": "Miami",
            "country": "US", "latitude": 25.7747, "longitude": -80.1858,
            "start_date": future(14, 12), "end_date": future(16, 22),
            "is_free": False, "price_min": 35, "price_max": 75, "currency": "USD",
            "capacity": 2000, "attendees_count": 1123, "interested_count": 567,
            "saves_count": 289, "is_featured": True, "is_trending": True,
            "status": "published", "tags": "food,tacos,tequila,festival,mexican,miami",
            "host_idx": 3, "category_id": food_id,
        },
        {
            "title": "Stand-Up Showcase: Next Gen Comics",
            "description": "Five of comedy's hottest rising stars take the stage for an evening of laughs you won't forget. These aren't open mic rookies — these are the comedians you'll be seeing on Netflix in two years. Two-drink minimum. Doors open at 7pm.",
            "cover_image": "https://images.unsplash.com/photo-1527224857830-43a7acc85260?w=800",
            "venue_name": "The Comedy Store", "address": "8433 W Sunset Blvd", "city": "Los Angeles",
            "country": "US", "latitude": 34.0903, "longitude": -118.3875,
            "start_date": future(8, 20), "end_date": future(8, 22),
            "is_free": False, "price_min": 20, "price_max": 20, "currency": "USD",
            "capacity": 250, "attendees_count": 201, "interested_count": 88,
            "saves_count": 74, "is_featured": False, "is_trending": True,
            "status": "published", "tags": "comedy,stand-up,live,los-angeles",
            "host_idx": 1, "category_id": comedy_id,
        },
        {
            "title": "3-on-3 Basketball Tournament",
            "description": "The streets meet the courts. Register your squad for Chicago's most competitive 3-on-3 tournament. Cash prizes for top 3 teams, plus a dunking competition, skills challenges, and live DJ all day. $500 winner take all. Register as a team of 3-4.",
            "cover_image": "https://images.unsplash.com/photo-1546519638-68e109498ffc?w=800",
            "venue_name": "Millennium Park", "address": "201 E Randolph St", "city": "Chicago",
            "country": "US", "latitude": 41.8827, "longitude": -87.6233,
            "start_date": future(12, 9), "end_date": future(12, 18),
            "is_free": False, "price_min": 15, "price_max": 15, "currency": "USD",
            "capacity": 400, "attendees_count": 245, "interested_count": 178,
            "saves_count": 92, "is_featured": False, "is_trending": True,
            "status": "published", "tags": "basketball,sports,tournament,chicago",
            "host_idx": 2, "category_id": sports_id,
        },
        {
            "title": "Latin Night: Salsa & Bachata",
            "description": "The hottest Latin dance night in LA is back. Free dance lessons from 8-9pm, followed by open dancing until 2am. Live percussion, world-class DJs, and an energy that can't be matched. Whether you're a pro or a beginner, this floor is for everyone.",
            "cover_image": "https://images.unsplash.com/photo-1504609813442-a8924e83f76e?w=800",
            "venue_name": "El Floridita", "address": "1253 Vine St", "city": "Los Angeles",
            "country": "US", "latitude": 34.0956, "longitude": -118.3267,
            "start_date": future(2, 21), "end_date": future(2, 2),
            "is_free": False, "price_min": 15, "price_max": 25, "currency": "USD",
            "capacity": 300, "attendees_count": 267, "interested_count": 143,
            "saves_count": 118, "is_featured": False, "is_trending": True,
            "status": "published", "tags": "salsa,bachata,latin,dance,nightlife",
            "host_idx": 3, "category_id": nightlife_id,
        },
        {
            "title": "Pop-Up Food Market: Global Bites",
            "description": "Chicago's most eclectic food market returns with 60+ vendors from around the world. Explore flavors from West Africa, Southeast Asia, Latin America, the Middle East, and beyond. Live cooking demos every hour. Dog-friendly. Free admission.",
            "cover_image": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800",
            "venue_name": "Logan Square Farmers Market", "address": "2755 N Milwaukee Ave",
            "city": "Chicago", "country": "US", "latitude": 41.9294, "longitude": -87.7026,
            "start_date": future(9, 10), "end_date": future(9, 18),
            "is_free": True, "price_min": None, "price_max": None,
            "capacity": None, "attendees_count": 534, "interested_count": 312,
            "saves_count": 167, "is_featured": True, "is_trending": False,
            "status": "published", "tags": "food,market,free,global,chicago",
            "host_idx": 2, "category_id": food_id,
        },
    ]


async def seed():
    import re
    # ── Seed auth-service ────────────────────────────────────────────────────────
    os.chdir(ROOT / "services" / "auth-service")
    os.makedirs("data", exist_ok=True)

    from services.auth_service.app.config import get_settings as auth_settings
    from services.auth_service.app.database import AsyncSessionLocal as auth_session, init_db as auth_init
    from services.auth_service.app.models import User
    from services.auth_service.app.security import hash_password

    await auth_init()

    user_ids = {}
    async with auth_session() as db:
        from sqlalchemy import select, delete
        # Clear existing
        await db.execute(delete(User))
        await db.commit()

        for u in USERS:
            uid = str(uuid.uuid4())
            user = User(
                id=uid, email=u["email"], username=u["username"],
                full_name=u["full_name"], hashed_password=hash_password("password123"),
                bio=u.get("bio"), avatar_url=u.get("avatar_url"),
                location=u.get("location"), is_verified=u.get("is_verified", False),
                followers_count=0, following_count=0,
            )
            db.add(user)
            user_ids[u["username"]] = uid
        await db.commit()
        print(f"✓ Seeded {len(USERS)} users into auth-service")

    # ── Seed events-service ──────────────────────────────────────────────────────
    os.chdir(ROOT / "services" / "events-service")
    os.makedirs("data", exist_ok=True)

    from services.events_service.app.database import AsyncSessionLocal as events_session, init_db as events_init
    from services.events_service.app.models import Category, Event

    await events_init()

    def slugify(text, uid):
        s = re.sub(r"[^\w\s-]", "", text.lower())
        return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"

    cat_ids = {}
    events_user_list = list(user_ids.values())

    async with events_session() as db:
        from sqlalchemy import delete
        await db.execute(delete(Event))
        await db.execute(delete(Category))
        await db.commit()

        for cat in CATEGORIES:
            cid = str(uuid.uuid4())
            db.add(Category(id=cid, name=cat["name"], slug=cat["slug"],
                            icon=cat["icon"], color=cat["color"]))
            cat_ids[cat["slug"]] = cid
        await db.commit()

        user_details = {u["username"]: u for u in USERS}
        username_list = list(user_ids.keys())

        for ev in make_events(events_user_list, cat_ids):
            eid = str(uuid.uuid4())
            host_username = username_list[ev["host_idx"]]
            host_uid = user_ids[host_username]
            host_info = user_details[host_username]

            event = Event(
                id=eid, slug=slugify(ev["title"], eid),
                title=ev["title"], description=ev["description"],
                cover_image=ev.get("cover_image"),
                host_id=host_uid, host_username=host_username,
                host_full_name=host_info["full_name"],
                host_avatar_url=host_info.get("avatar_url"),
                host_is_verified=host_info.get("is_verified", False),
                venue_name=ev["venue_name"], address=ev["address"],
                city=ev["city"], country=ev["country"],
                latitude=ev.get("latitude"), longitude=ev.get("longitude"),
                start_date=ev["start_date"], end_date=ev["end_date"],
                is_free=ev["is_free"], price_min=ev.get("price_min"),
                price_max=ev.get("price_max"), currency=ev.get("currency", "USD"),
                ticket_url=ev.get("ticket_url"), capacity=ev.get("capacity"),
                attendees_count=ev.get("attendees_count", 0),
                interested_count=ev.get("interested_count", 0),
                saves_count=ev.get("saves_count", 0),
                is_featured=ev.get("is_featured", False),
                is_trending=ev.get("is_trending", False),
                status=ev.get("status", "published"),
                tags=ev.get("tags"), category_id=ev.get("category_id"),
            )
            db.add(event)

        await db.commit()
        print(f"✓ Seeded {len(CATEGORIES)} categories and {len(make_events([], {}))} events into events-service")

    print("\n🎉 Seed complete! Demo credentials: any user@turnup.dev / password123")


if __name__ == "__main__":
    asyncio.run(seed())
