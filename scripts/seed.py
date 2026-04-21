#!/usr/bin/env python3
"""
Turnup seeder — run from the project root:
    cd backend && python ../scripts/seed.py
"""
import asyncio, os, re, sys, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
os.makedirs("data", exist_ok=True)

from app.database import AsyncSessionLocal, init_db
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.social import Follow
from app.models.user import User
from app.services.auth import hash_password


def utc(days: int, hour: int = 20) -> datetime:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


USERS = [
    {"username": "nova_beats",   "full_name": "Nova Williams",  "email": "nova@turnup.dev",
     "bio": "DJ & music producer 🎧", "location": "New York, NY", "verified": True,
     "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=nova",
     "prefs": "music,nightlife"},
    {"username": "jxmie",        "full_name": "Jamie Chen",     "email": "jamie@turnup.dev",
     "bio": "Festival addict. 50+ events this year.",  "location": "Los Angeles, CA", "verified": True,
     "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=jamie",
     "prefs": "music,comedy,arts"},
    {"username": "skyler_vibe",  "full_name": "Skyler Davis",   "email": "skyler@turnup.dev",
     "bio": "Event curator. Art meets sound.", "location": "Chicago, IL", "verified": False,
     "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=skyler",
     "prefs": "arts,food,sports"},
    {"username": "reina_mx",     "full_name": "Reina Morales",  "email": "reina@turnup.dev",
     "bio": "Promoter | Dancer | Tacos 🌮",  "location": "Miami, FL", "verified": True,
     "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=reina",
     "prefs": "nightlife,food"},
    {"username": "kobe_events",  "full_name": "Kobe Thompson",  "email": "kobe@turnup.dev",
     "bio": "Bringing culture to the city.", "location": "Atlanta, GA", "verified": False,
     "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=kobe",
     "prefs": "sports,wellness,tech"},
]

CATEGORIES = [
    ("Music",        "music",     "🎵", "#F97316"),
    ("Arts & Culture","arts",     "🎨", "#A855F7"),
    ("Food & Drink", "food",      "🍕", "#EF4444"),
    ("Sports",       "sports",    "⚽", "#22C55E"),
    ("Nightlife",    "nightlife", "🌙", "#3B82F6"),
    ("Tech",         "tech",      "💻", "#06B6D4"),
    ("Comedy",       "comedy",    "😂", "#EAB308"),
    ("Wellness",     "wellness",  "🧘", "#10B981"),
]


def make_events(user_ids: dict, cat_ids: dict) -> list[dict]:
    M, NL, AR, FD, TC, SP, CM, WL = (
        cat_ids["music"], cat_ids["nightlife"], cat_ids["arts"], cat_ids["food"],
        cat_ids["tech"], cat_ids["sports"], cat_ids["comedy"], cat_ids["wellness"],
    )
    H = list(user_ids.keys())  # host usernames by index

    return [
        dict(title="Bass Collective: Underground Sessions",
             desc="The city's most immersive underground bass experience. Four rooms, eight DJs, a sound system that will shake your soul.",
             img="https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800",
             venue="Avant Gardner", addr="140 Stewart Ave", city="New York",
             lat=40.7033, lng=-73.9343, start=utc(3), end=utc(3, 4),
             free=False, pmin=25, pmax=45, cap=800, going=412, interested=289, saves=156,
             featured=True, trending=True, tags="bass,electronic,dnb",
             host=H[0], cat=NL),

        dict(title="Afrobeats & Amapiano Festival",
             desc="Celebrate African music excellence. Grammy-nominated artists, local legends, and rising stars for a 10-hour celebration.",
             img="https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800",
             venue="Citi Field Lot", addr="126-01 Roosevelt Ave", city="New York",
             lat=40.7571, lng=-73.8458, start=utc(7, 14), end=utc(7, 23),
             free=False, pmin=55, pmax=120, cap=5000, going=2341, interested=1876, saves=923,
             featured=True, trending=True, tags="afrobeats,amapiano,festival",
             host=H[1], cat=M),

        dict(title="Rooftop Sunset Sessions",
             desc="Watch the city transform under a golden sky while house music fills the air. Monthly rooftop series with resident DJs.",
             img="https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=800",
             venue="The Skylark", addr="200 W 39th St", city="New York",
             lat=40.7536, lng=-73.9932, start=utc(5, 18), end=utc(5, 23),
             free=False, pmin=20, pmax=35, cap=200, going=178, interested=94, saves=67,
             featured=True, trending=False, tags="rooftop,house,sunset",
             host=H[0], cat=NL),

        dict(title="Street Art & Mural Festival",
             desc="Four-day open-air festival. Watch 30+ artists transform blank walls in real time. Free admission.",
             img="https://images.unsplash.com/photo-1499781350541-7783f6c6a0c8?w=800",
             venue="Wynwood Walls", addr="2520 NW 2nd Ave", city="Miami",
             lat=25.8008, lng=-80.1993, start=utc(10, 11), end=utc(13, 20),
             free=True, pmin=None, pmax=None, cap=None, going=892, interested=634, saves=211,
             featured=True, trending=True, tags="art,murals,free,culture",
             host=H[2], cat=AR),

        dict(title="Late Night Jazz & Cocktails",
             desc="Intimate speakeasy setting. House quartet performs standards and originals while expert mixologists craft bespoke cocktails.",
             img="https://images.unsplash.com/photo-1415201364774-f6f0bb35f28f?w=800",
             venue="The Blue Note", addr="131 W 3rd St", city="New York",
             lat=40.7300, lng=-74.0007, start=utc(4, 21), end=utc(5, 2),
             free=False, pmin=30, pmax=30, cap=120, going=98, interested=45, saves=38,
             featured=False, trending=False, tags="jazz,live-music,cocktails",
             host=H[0], cat=M),

        dict(title="Tech & Innovation Summit 2026",
             desc="Southeast's largest tech conference. Founders, engineers, investors for two days of keynotes, workshops, and networking.",
             img="https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800",
             venue="Georgia World Congress Center", addr="285 Andrew Young Intl Blvd NW", city="Atlanta",
             lat=33.7590, lng=-84.3977, start=utc(21, 9), end=utc(22, 18),
             free=False, pmin=99, pmax=499, cap=3000, going=1456, interested=789, saves=345,
             featured=True, trending=True, tags="tech,ai,startup,networking",
             host=H[4], cat=TC),

        dict(title="Morning Yoga in the Park",
             desc="Free community yoga in Piedmont Park. All levels welcome. Post-session smoothie meetup at the farmer's market.",
             img="https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800",
             venue="Piedmont Park", addr="1320 Monroe Dr NE", city="Atlanta",
             lat=33.7867, lng=-84.3732, start=utc(6, 8), end=utc(6, 10),
             free=True, pmin=None, pmax=None, cap=150, going=87, interested=134, saves=56,
             featured=False, trending=False, tags="yoga,wellness,free,outdoor",
             host=H[4], cat=WL),

        dict(title="Tacos & Tequila Festival",
             desc="40+ taco vendors, 25 tequila brands, live mariachi, lucha libre, and cooking demos from Michelin-starred chefs.",
             img="https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=800",
             venue="Bayfront Park", addr="301 Biscayne Blvd", city="Miami",
             lat=25.7747, lng=-80.1858, start=utc(14, 12), end=utc(16, 22),
             free=False, pmin=35, pmax=75, cap=2000, going=1123, interested=567, saves=289,
             featured=True, trending=True, tags="food,tacos,tequila,festival",
             host=H[3], cat=FD),

        dict(title="Stand-Up Showcase: Next Gen Comics",
             desc="Five of comedy's hottest rising stars. Two-drink minimum. Doors 7pm.",
             img="https://images.unsplash.com/photo-1527224857830-43a7acc85260?w=800",
             venue="The Comedy Store", addr="8433 W Sunset Blvd", city="Los Angeles",
             lat=34.0903, lng=-118.3875, start=utc(8, 20), end=utc(8, 22),
             free=False, pmin=20, pmax=20, cap=250, going=201, interested=88, saves=74,
             featured=False, trending=True, tags="comedy,stand-up,live",
             host=H[1], cat=CM),

        dict(title="3-on-3 Basketball Tournament",
             desc="Chicago's most competitive 3-on-3 tournament. $500 winner take all. Dunking competition, skills challenges, live DJ.",
             img="https://images.unsplash.com/photo-1546519638-68e109498ffc?w=800",
             venue="Millennium Park", addr="201 E Randolph St", city="Chicago",
             lat=41.8827, lng=-87.6233, start=utc(12, 9), end=utc(12, 18),
             free=False, pmin=15, pmax=15, cap=400, going=245, interested=178, saves=92,
             featured=False, trending=True, tags="basketball,sports,tournament",
             host=H[2], cat=SP),

        dict(title="Latin Night: Salsa & Bachata",
             desc="Free dance lessons 8-9pm, open dancing till 2am. Live percussion, world-class DJs. All levels welcome.",
             img="https://images.unsplash.com/photo-1504609813442-a8924e83f76e?w=800",
             venue="El Floridita", addr="1253 Vine St", city="Los Angeles",
             lat=34.0956, lng=-118.3267, start=utc(2, 21), end=utc(3, 2),
             free=False, pmin=15, pmax=25, cap=300, going=267, interested=143, saves=118,
             featured=False, trending=True, tags="salsa,bachata,latin,dance",
             host=H[3], cat=NL),

        dict(title="Pop-Up Food Market: Global Bites",
             desc="60+ vendors from around the world. West Africa, Southeast Asia, Latin America, the Middle East. Free admission.",
             img="https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800",
             venue="Logan Square Farmers Market", addr="2755 N Milwaukee Ave", city="Chicago",
             lat=41.9294, lng=-87.7026, start=utc(9, 10), end=utc(9, 18),
             free=True, pmin=None, pmax=None, cap=None, going=534, interested=312, saves=167,
             featured=True, trending=False, tags="food,market,free,global",
             host=H[2], cat=FD),
    ]


async def run():
    await init_db()

    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        # Clear all in correct order
        for model in (Follow, EventAttendee, EventSave, Event, Category, User):
            await db.execute(delete(model))
        await db.commit()

        # ── Users ──────────────────────────────────────────────────────────────
        user_ids: dict[str, str] = {}
        for u in USERS:
            uid = str(uuid.uuid4())
            db.add(User(
                id=uid, email=u["email"], username=u["username"],
                full_name=u["full_name"], hashed_password=hash_password("password123"),
                bio=u.get("bio"), avatar_url=u.get("avatar"),
                location=u.get("location"), is_verified=u.get("verified", False),
                category_preferences=u.get("prefs"), onboarding_completed=True,
            ))
            user_ids[u["username"]] = uid
        await db.commit()
        print(f"✓ {len(USERS)} users")

        # ── Categories ─────────────────────────────────────────────────────────
        cat_ids: dict[str, str] = {}
        for name, slug, icon, color in CATEGORIES:
            cid = str(uuid.uuid4())
            db.add(Category(id=cid, name=name, slug=slug, icon=icon, color=color))
            cat_ids[slug] = cid
        await db.commit()
        print(f"✓ {len(CATEGORIES)} categories")

        # ── Events ─────────────────────────────────────────────────────────────
        events = make_events(user_ids, cat_ids)
        for ev in events:
            eid = str(uuid.uuid4())
            db.add(Event(
                id=eid, slug=slugify(ev["title"], eid),
                title=ev["title"], description=ev["desc"],
                cover_image=ev.get("img"),
                host_id=user_ids[ev["host"]],
                venue_name=ev["venue"], address=ev["addr"], city=ev["city"],
                latitude=ev.get("lat"), longitude=ev.get("lng"),
                start_date=ev["start"], end_date=ev["end"],
                is_free=ev["free"], price_min=ev.get("pmin"), price_max=ev.get("pmax"),
                capacity=ev.get("cap"),
                attendees_count=ev.get("going", 0),
                interested_count=ev.get("interested", 0),
                saves_count=ev.get("saves", 0),
                is_featured=ev.get("featured", False),
                is_trending=ev.get("trending", False),
                status="published", tags=ev.get("tags"),
                category_id=ev.get("cat"),
            ))
        await db.commit()
        print(f"✓ {len(events)} events")

        # ── Some follows ────────────────────────────────────────────────────────
        follow_pairs = [
            ("jxmie", "nova_beats"), ("skyler_vibe", "nova_beats"),
            ("reina_mx", "jxmie"), ("kobe_events", "jxmie"),
            ("nova_beats", "reina_mx"), ("jxmie", "skyler_vibe"),
        ]
        for follower, following in follow_pairs:
            if follower in user_ids and following in user_ids:
                db.add(Follow(
                    id=str(uuid.uuid4()),
                    follower_id=user_ids[follower],
                    following_id=user_ids[following],
                ))
        await db.commit()
        print(f"✓ {len(follow_pairs)} follows")

    print("\n🎉 Seed complete!")
    print("   Login with any user: nova@turnup.dev / password123")
    print("   All users share the password: password123")


if __name__ == "__main__":
    asyncio.run(run())
