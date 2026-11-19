"""Demo data for test/staging environments: users, events, tickets, communities, reviews...

    python -m app.cli seed            # fill an EMPTY database
    python -m app.cli seed --reset    # wipe EVERYTHING in the database, then fill it

In Docker: `docker compose run --rm migrate python -m app.cli seed`.
All demo accounts share the password "password123"; never run this against production.
"""
import re, uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import AsyncSessionLocal, Base, init_db
from app.models.community import Community, CommunityEvent, CommunityMember
from app.models.event import Category, Event, EventAttendee, EventSave
from app.models.social import Follow, Notification, Comment
from app.models.organizer import EventReview, EventWaitlist, OrganizerProfile, TicketTier, TicketOrder
from app.models.user import User
from app.services.auth import hash_password


_WAT = ZoneInfo("Africa/Lagos")


def utc(days: int, hour: int = 20) -> datetime:
    d = datetime.now(_WAT) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


def slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


# ── Users ──────────────────────────────────────────────────────────────────────
USERS = [
    {
        "username": "turnup_admin",
        "full_name": "Turnup Admin",
        "email": "admin@turnup.ng",
        "bio": "Platform administrator",
        "location": "Lagos, Nigeria",
        "verified": True,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=admin",
        "prefs": "",
        "role": "admin",
    },
    {
        "username": "adaeze_sounds",
        "full_name": "Adaeze Okonkwo",
        "email": "adaeze@turnup.ng",
        "bio": "DJ · Music curator · Lagos nightlife since 2018 🎧 Book me: adaeze@book.ng",
        "location": "Lagos, Nigeria",
        "verified": True,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=adaeze",
        "prefs": "music,nightlife,arts",
        "role": "organizer",
    },
    {
        "username": "seun_pg",
        "full_name": "Seun Adeleke",
        "email": "seun@turnup.ng",
        "bio": "Event promoter 🔥 Lagos & Abuja. Bringing the vibes since 2020. @seun_pg everywhere.",
        "location": "Lagos, Nigeria",
        "verified": True,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=seun",
        "prefs": "nightlife,music,food",
        "role": "organizer",
    },
    {
        "username": "tunde_vibes",
        "full_name": "Tunde Badmus",
        "email": "tunde@turnup.ng",
        "bio": "Lifestyle curator 🌴 If it's not vibey, I'm not going. Lagos Island mostly.",
        "location": "Lagos, Nigeria",
        "verified": False,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=tunde",
        "prefs": "food,arts,nightlife",
        "role": "attendee",
    },
    {
        "username": "chiamaka_lit",
        "full_name": "Chiamaka Eze",
        "email": "chiamaka@turnup.ng",
        "bio": "Foodie 🍲 Festival goer 🎪 Content creator. PH → Lagos. Always at the next thing.",
        "location": "Lagos, Nigeria",
        "verified": False,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=chiamaka",
        "prefs": "food,wellness,arts",
        "role": "attendee",
    },
    {
        "username": "dayo_hype",
        "full_name": "Dayo Adeyemi",
        "email": "dayo@turnup.ng",
        "bio": "Stand-up comedian 😂 MC · Host · Abuja-based. Bookings DM me.",
        "location": "Abuja, Nigeria",
        "verified": True,
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=dayo",
        "prefs": "comedy,music,nightlife",
        "role": "organizer",
    },
    {
        "username": "bola_venues",
        "full_name": "Bola Ogunleye",
        "email": "bola@turnup.ng",
        "bio": "Owner, The Grand Pavilion (Lekki) and Skyline Rooftop (VI).",
        "location": "Lagos, Nigeria",
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=bola",
        "prefs": "music,nightlife",
        "role": "attendee",
    },
    {
        "username": "kemi_agent",
        "full_name": "Kemi Balogun",
        "email": "kemi@turnup.ng",
        "bio": "Turnup venue agent, Lagos and Ogun.",
        "location": "Lagos, Nigeria",
        "avatar": "https://api.dicebear.com/9.x/avataaars/svg?seed=kemi",
        "prefs": "music",
        "role": "attendee",
    },
]

# ── Categories ─────────────────────────────────────────────────────────────────
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

# ── Events ─────────────────────────────────────────────────────────────────────
def make_events(user_ids: dict, cat_ids: dict) -> list[dict]:
    M, NL, AR, FD, TC, SP, CM, WL = (
        cat_ids["music"], cat_ids["nightlife"], cat_ids["arts"], cat_ids["food"],
        cat_ids["tech"], cat_ids["sports"], cat_ids["comedy"], cat_ids["wellness"],
    )

    return [
        # ── Upcoming ────────────────────────────────────────────────────────────
        dict(
            title="Detty December Kickoff: Pool Party & Afrobeats",
            desc=(
                "The biggest pool party in Lagos is BACK. Wizkid's team DJ, Mr Eazi surprise set rumoured, "
                "bottle service, and a crowd that knows how to turn up. Afrobeats, Amapiano, and Naija classics "
                "from sunset to sunrise. VIP tables go fast — this is not a drill."
            ),
            img="https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800",
            venue="Hard Rock Hotel Lagos", addr="Plot 1261A Ahmadu Bello Way", city="Lagos",
            lat=6.4350, lng=3.4259, start=utc(4, 16), end=utc(5, 4),
            free=False, pmin=15000, pmax=75000, cap=1500,
            going=1243, interested=892, saves=517,
            featured=True, trending=True,
            tags="detty-december,pool-party,afrobeats,lagos",
            host="seun_pg", cat=NL,
            tiers=[
                dict(name="Regular Entry", price=15000, qty=800, max_per=4,
                     desc="General pool area access from 4pm"),
                dict(name="Premium", price=35000, qty=500, max_per=4,
                     desc="Premium section + 1 cocktail on arrival"),
                dict(name="VIP Table (4 pax)", price=250000, qty=50, max_per=1,
                     desc="Private table for 4, bottle service included, priority entry"),
            ],
        ),
        dict(
            title="Flytime Music Festival 2026",
            desc=(
                "Nigeria's most anticipated annual music festival returns to Eko Atlantic. Burna Boy, "
                "Davido, Tiwa Savage, Asake, Rema, and 10 more acts across 2 stages. "
                "This year's theme: The African Giant Experience. Prepare to be moved."
            ),
            img="https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800",
            venue="Eko Atlantic City", addr="Victoria Island", city="Lagos",
            lat=6.4054, lng=3.4108, start=utc(8, 15), end=utc(8, 23),
            free=False, pmin=25000, pmax=150000, cap=10000,
            going=7823, interested=4512, saves=2891,
            featured=True, trending=True,
            tags="flytime,afrobeats,burna-boy,davido,festival,eko-atlantic",
            host="adaeze_sounds", cat=M,
            tiers=[
                dict(name="General", price=25000, qty=6000, max_per=4),
                dict(name="Golden Circle", price=75000, qty=2000, max_per=2,
                     desc="Front-stage zone + meet & greet access ballot"),
                dict(name="VIP Experience", price=150000, qty=500, max_per=2,
                     desc="Dedicated bar, lounges, complimentary meal, artist access zone"),
            ],
        ),
        dict(
            title="New Afrika Shrine: Felabration Pre-Party",
            desc=(
                "Every year Lagos remembers Fela. This is the warm-up. Live Afrobeat band plays "
                "through the original catalogue, palm wine flows, and the Shrine grounds fill with "
                "everyone from diplomats to street artists. No dress code — just love for the music."
            ),
            img="https://images.unsplash.com/photo-1415201364774-f6f0bb35f28f?w=800",
            venue="New Afrika Shrine", addr="1 Nerdc Rd, Agidingbi", city="Lagos",
            lat=6.6018, lng=3.3515, start=utc(6, 19), end=utc(7, 2),
            free=False, pmin=5000, pmax=20000, cap=2000,
            going=1567, interested=893, saves=421,
            featured=True, trending=False,
            tags="fela,afrobeat,shrine,felabration,live-band",
            host="adaeze_sounds", cat=M,
            tiers=[
                dict(name="General", price=5000, qty=1500, max_per=6),
                dict(name="VIP Lounge", price=20000, qty=200, max_per=2,
                     desc="Elevated VIP section, table service"),
            ],
        ),
        dict(
            title="Lagos Comic Con 2026",
            desc=(
                "West Africa's biggest pop culture convention. Manga, anime, gaming, cosplay competitions "
                "with ₦500k prize pool, celebrity voice actors, Nollywood film premiers, and 200+ vendors. "
                "Cosplay is encouraged — we'll be judging."
            ),
            img="https://images.unsplash.com/photo-1608889335941-32ac5f2041b9?w=800",
            venue="Eko Convention Centre", addr="Plot 1415 Adetokunbo Ademola St", city="Lagos",
            lat=6.4336, lng=3.4237, start=utc(11, 10), end=utc(12, 18),
            free=False, pmin=3500, pmax=15000, cap=8000,
            going=5231, interested=3102, saves=1876,
            featured=True, trending=True,
            tags="comic-con,anime,gaming,cosplay,nollywood",
            host="dayo_hype", cat=AR,
            tiers=[
                dict(name="Day Pass", price=3500, qty=5000, max_per=4),
                dict(name="Weekend Pass", price=7500, qty=2000, max_per=4,
                     desc="Both days + early entry 9:30am"),
                dict(name="Creator Pass", price=15000, qty=200, max_per=1,
                     desc="Both days + exhibitor table + badge + meet-and-greet priority"),
            ],
        ),
        dict(
            title="Stand Up Lagos: New Money Edition",
            desc=(
                "Four of Nigeria's hottest comedians — including Bovi, Kenny Blaq, and two surprise acts — "
                "talk money, hustle, and the Nigerian experience. AY Promotions production. "
                "Adults only (18+). You've been warned."
            ),
            img="https://images.unsplash.com/photo-1527224857830-43a7acc85260?w=800",
            venue="Eko Hotel & Suites", addr="Plot 1415 Adetokunbo Ademola St, VI", city="Lagos",
            lat=6.4343, lng=3.4238, start=utc(9, 19), end=utc(9, 22),
            free=False, pmin=10000, pmax=50000, cap=3000,
            going=2234, interested=1102, saves=678,
            featured=False, trending=True,
            tags="comedy,stand-up,bovi,kenny-blaq,naija",
            host="dayo_hype", cat=CM,
            tiers=[
                dict(name="Standard", price=10000, qty=1500, max_per=4),
                dict(name="Premium", price=25000, qty=1000, max_per=4,
                     desc="Premium seating, closer to the stage"),
                dict(name="VIP Front Row", price=50000, qty=100, max_per=2,
                     desc="Front row seats + meet-the-comedians after-show"),
            ],
        ),
        dict(
            title="Naija Jollof Wars 2026",
            desc=(
                "Lagos vs Abuja vs PH — whose jollof reigns supreme? 30 chefs compete live, public votes "
                "decide the winner. Between rounds: live music, suya station, Chapman bar, "
                "and the most chaotic food battle you'll ever witness."
            ),
            img="https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800",
            venue="Freedom Park Lagos", addr="38 Broad St, Lagos Island", city="Lagos",
            lat=6.4504, lng=3.3876, start=utc(13, 13), end=utc(13, 20),
            free=False, pmin=5000, pmax=5000, cap=3000,
            going=1892, interested=1034, saves=567,
            featured=True, trending=True,
            tags="jollof,food,festival,lagos,naija",
            host="chiamaka_lit", cat=FD,
            tiers=[
                dict(name="Tasting Pass", price=5000, qty=3000, max_per=6,
                     desc="Entry + 5 tasting tokens (each token = 1 full plate)"),
            ],
        ),
        dict(
            title="Lagos Tech Fest: AI & Startups",
            desc=(
                "Co-hosted by CcHub and Google for Startups. Founders, engineers, and investors from "
                "across the continent. Day 1: Pitch competition (₦5m prize pool). "
                "Day 2: Deep-dive workshops on AI, fintech, and building for Africa. Free to attend."
            ),
            img="https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800",
            venue="Co-Creation Hub (CcHub)", addr="294 Herbert Macaulay Way, Yaba", city="Lagos",
            lat=6.5058, lng=3.3798, start=utc(21, 9), end=utc(22, 18),
            free=True, pmin=None, pmax=None, cap=500,
            going=387, interested=612, saves=234,
            featured=False, trending=False,
            tags="tech,ai,startup,nigeria,cchub,fintech",
            host="tunde_vibes", cat=TC,
            tiers=[
                dict(name="Free Registration", price=0, qty=500, max_per=1),
            ],
        ),
        dict(
            title="Afrobeats & Asoebi: Terra Kulture Jazz Night",
            desc=(
                "Intimate jazz experience at Lagos's most beloved cultural hub. The Terra Kulture "
                "house quartet performs Fela, Lagbaja, and original compositions. "
                "Dress code: Agbada, kaftan, asoebi, or 'what your mum would approve of'."
            ),
            img="https://images.unsplash.com/photo-1510915361894-db8b60106cb1?w=800",
            venue="Terra Kulture Arena", addr="Plot 1376 Tiamiyu Savage St, VI", city="Lagos",
            lat=6.4327, lng=3.4219, start=utc(3, 19), end=utc(3, 23),
            free=False, pmin=8000, pmax=25000, cap=400,
            going=312, interested=178, saves=134,
            featured=False, trending=False,
            tags="jazz,live-music,terra-kulture,afrobeats,lagos",
            host="adaeze_sounds", cat=M,
            tiers=[
                dict(name="Regular", price=8000, qty=250, max_per=4),
                dict(name="Table of 2", price=25000, qty=40, max_per=1,
                     desc="Reserved table for 2 with complimentary drinks"),
            ],
        ),
        dict(
            title="Sunrise Yoga at Bar Beach",
            desc=(
                "Meet at Bar Beach for a 90-minute sunrise yoga and meditation session with certified "
                "instructor Kemi Ade. All levels welcome. Mats available. Post-session: "
                "fresh coconut water and acai bowls from vendors on site."
            ),
            img="https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800",
            venue="Bar Beach", addr="Ahmadu Bello Way, Victoria Island", city="Lagos",
            lat=6.4268, lng=3.4241, start=utc(2, 6), end=utc(2, 8),
            free=True, pmin=None, pmax=None, cap=100,
            going=67, interested=143, saves=89,
            featured=False, trending=False,
            tags="yoga,wellness,beach,free,vi,sunrise",
            host="chiamaka_lit", cat=WL,
            tiers=[
                dict(name="Free RSVP", price=0, qty=100, max_per=1),
            ],
        ),
        dict(
            title="Abuja Dinner Jazz: Highlife & Wine",
            desc=(
                "An evening of vintage highlife, contemporary jazz, and curated Nigerian wines at "
                "Transcorp Hilton's rooftop. Four-course Nigerian fine dining by Chef Imoteda. "
                "Dress: Smart casual. FCT's most refined monthly series."
            ),
            img="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800",
            venue="Transcorp Hilton Abuja", addr="1 Aguiyi Ironsi St, Maitama", city="Abuja",
            lat=9.0802, lng=7.4929, start=utc(16, 19), end=utc(16, 23),
            free=False, pmin=35000, pmax=35000, cap=150,
            going=112, interested=67, saves=43,
            featured=False, trending=False,
            tags="jazz,highlife,wine,abuja,fine-dining",
            host="dayo_hype", cat=M,
            tiers=[
                dict(name="Dinner Seat", price=35000, qty=150, max_per=2,
                     desc="4-course dinner + welcome cocktail + live jazz"),
            ],
        ),
        # ── Past events (for attendance history) ────────────────────────────────
        dict(
            title="Headies Awards After-Party 2025",
            desc="Official after-party for the 17th Headies Awards. Exclusive. Invite-only for nominees — but we sold 200 tickets.",
            img="https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800",
            venue="Balmoral Convention Centre", addr="Federal Palace Hotel, VI", city="Lagos",
            lat=6.4295, lng=3.4256, start=utc(-30, 22), end=utc(-29, 4),
            free=False, pmin=20000, pmax=75000, cap=500,
            going=423, interested=234, saves=189,
            featured=False, trending=False,
            tags="headies,awards,afterparty,afrobeats",
            host="seun_pg", cat=NL,
            tiers=[
                dict(name="General", price=20000, qty=300, max_per=2),
                dict(name="VIP Table", price=150000, qty=20, max_per=1,
                     desc="Table of 4 with bottle service"),
            ],
        ),
        dict(
            title="Burna Boy: I Told Them Listening Party",
            desc="Lagos listening party for Burna Boy's latest album. Exclusive 300-person experience at Eko Hotel.",
            img="https://images.unsplash.com/photo-1508700929628-666bc8bd84ea?w=800",
            venue="Eko Hotel & Suites", addr="Plot 1415 Adetokunbo Ademola St, VI", city="Lagos",
            lat=6.4343, lng=3.4238, start=utc(-14, 20), end=utc(-14, 23),
            free=False, pmin=30000, pmax=30000, cap=300,
            going=287, interested=142, saves=98,
            featured=False, trending=False,
            tags="burna-boy,listening-party,afrobeats,exclusive",
            host="adaeze_sounds", cat=M,
            tiers=[
                dict(name="Listening Session Pass", price=30000, qty=300, max_per=2),
            ],
        ),
    ]


class SeedRefused(RuntimeError):
    """The database already has real-looking data and --reset wasn't given."""


async def run(reset: bool = False):
    await init_db()

    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete, func, select, text  # noqa: F401  (text: used below)

        existing = (await db.execute(
            select(func.count(User.id)).where(User.username != settings.scout_bot_username)
        )).scalar()
        if existing and not reset:
            raise SeedRefused(
                f"The database already has {existing} user(s). Seeding would mix demo data into it.\n"
                "To WIPE EVERYTHING and load demo data instead, run: python -m app.cli seed --reset"
            )
        if reset:
            # Every table, children before parents, so foreign keys are never violated (the old
            # hand-written list missed newer tables and failed on Postgres).
            for table in reversed(Base.metadata.sorted_tables):
                await db.execute(delete(table))
            await db.commit()

        # ── Users ──────────────────────────────────────────────────────────────
        user_ids: dict[str, str] = {}
        for u in USERS:
            uid = str(uuid.uuid4())
            db.add(User(
                id=uid,
                email=u["email"],
                username=u["username"],
                full_name=u["full_name"],
                hashed_password=hash_password("password123"),
                bio=u.get("bio"),
                avatar_url=u.get("avatar"),
                location=u.get("location"),
                is_verified=u.get("verified", False),
                category_preferences=u.get("prefs"),
                onboarding_completed=True,
                role=u.get("role", "attendee"),
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

        # ── Events + Tiers ─────────────────────────────────────────────────────
        events_data = make_events(user_ids, cat_ids)
        event_ids: dict[str, str] = {}
        tier_ids: dict[str, dict] = {}   # event_title -> {tier_name -> tier_id}

        for ev in events_data:
            eid = str(uuid.uuid4())
            slug = slugify(ev["title"], eid)
            db.add(Event(
                id=eid, slug=slug,
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
            event_ids[ev["title"]] = eid
            tier_ids[ev["title"]] = {}

            for t in ev.get("tiers", []):
                tid = str(uuid.uuid4())
                db.add(TicketTier(
                    id=tid, event_id=eid,
                    name=t["name"],
                    description=t.get("desc"),
                    price=float(t["price"]),
                    currency="NGN",
                    quantity=t.get("qty"),
                    max_per_order=t.get("max_per", 4),
                    is_active=True,
                ))
                tier_ids[ev["title"]][t["name"]] = tid

        await db.commit()
        print(f"✓ {len(events_data)} events with tiers")

        # ── Follows ────────────────────────────────────────────────────────────
        # adaeze follows seun, tunde, chiamaka, dayo
        # seun follows adaeze, dayo
        # tunde follows adaeze, seun
        # chiamaka follows adaeze, tunde
        # dayo follows seun, adaeze
        follow_pairs = [
            ("adaeze_sounds", "seun_pg",        utc(-45)),
            ("adaeze_sounds", "tunde_vibes",     utc(-38)),
            ("adaeze_sounds", "chiamaka_lit",    utc(-20)),
            ("adaeze_sounds", "dayo_hype",       utc(-10)),
            ("seun_pg",       "adaeze_sounds",   utc(-60)),
            ("seun_pg",       "dayo_hype",       utc(-5)),
            ("tunde_vibes",   "adaeze_sounds",   utc(-55)),
            ("tunde_vibes",   "seun_pg",         utc(-3)),
            ("chiamaka_lit",  "adaeze_sounds",   utc(-30)),
            ("chiamaka_lit",  "tunde_vibes",     utc(-15)),
            ("dayo_hype",     "seun_pg",         utc(-7)),
            ("dayo_hype",     "adaeze_sounds",   utc(-50)),
        ]
        follow_obj_ids: dict[tuple, str] = {}
        for follower, following, created_at in follow_pairs:
            fid = str(uuid.uuid4())
            f = Follow(
                id=fid,
                follower_id=user_ids[follower],
                following_id=user_ids[following],
                created_at=created_at,
            )
            db.add(f)
            follow_obj_ids[(follower, following)] = fid

            # Update follower/following counts on User
            await db.flush()

        # Update follower/following counts manually
        counts: dict[str, dict] = {u: {"followers": 0, "following": 0} for u in user_ids}
        for follower, following, _ in follow_pairs:
            counts[follower]["following"] += 1
            counts[following]["followers"] += 1

        for uname, c in counts.items():
            await db.execute(
                text("UPDATE users SET followers_count=:f, following_count=:fo WHERE id=:id"),
                {"f": c["followers"], "fo": c["following"], "id": user_ids[uname]},
            )
        await db.commit()
        print(f"✓ {len(follow_pairs)} follows")

        # ── Event Attendance ───────────────────────────────────────────────────
        # Build realistic attendance records so activity feed has content
        # adaeze is the "current user" logged in for screenshots
        attendance = [
            # adaeze's own past attendance
            ("adaeze_sounds", "Headies Awards After-Party 2025", "going", utc(-30, 21)),
            ("adaeze_sounds", "Burna Boy: I Told Them Listening Party", "going", utc(-14, 20)),
            # seun going to upcoming events (adaeze follows seun → shows in feed)
            ("seun_pg", "Detty December Kickoff: Pool Party & Afrobeats", "going", utc(-2)),
            ("seun_pg", "Flytime Music Festival 2026", "going", utc(-1, 10)),
            ("seun_pg", "Stand Up Lagos: New Money Edition", "interested", utc(-1, 14)),
            # tunde going (adaeze follows tunde → shows in feed)
            ("tunde_vibes", "Naija Jollof Wars 2026", "going", utc(-1, 8)),
            ("tunde_vibes", "Lagos Comic Con 2026", "interested", utc(-3, 12)),
            # chiamaka going (adaeze follows chiamaka → shows in feed)
            ("chiamaka_lit", "Naija Jollof Wars 2026", "going", utc(-1, 9)),
            ("chiamaka_lit", "Sunrise Yoga at Bar Beach", "going", utc(-1, 16)),
            # dayo going (adaeze follows dayo)
            ("dayo_hype", "Stand Up Lagos: New Money Edition", "going", utc(-2, 18)),
            ("dayo_hype", "Abuja Dinner Jazz: Highlife & Wine", "going", utc(-4, 11)),
        ]
        att_count = 0
        for username, event_title, status, created_at in attendance:
            if username not in user_ids or event_title not in event_ids:
                print(f"  skip attendance: {username} / {event_title}")
                continue
            db.add(EventAttendee(
                id=str(uuid.uuid4()),
                user_id=user_ids[username],
                event_id=event_ids[event_title],
                status=status,
                created_at=created_at,
            ))
            att_count += 1
        await db.commit()
        print(f"✓ {att_count} attendance records")

        # ── Ticket Orders for adaeze (My Tickets page) ────────────────────────
        def ref():
            return f"TUP-{str(uuid.uuid4())[:8].upper()}"

        ticket_orders = [
            # Past — confirmed
            dict(
                event="Headies Awards After-Party 2025",
                tier="General",
                qty=2, unit_price=20000, status="confirmed",
                ref=ref(), channel="card",
                created_at=utc(-31, 14),
            ),
            dict(
                event="Burna Boy: I Told Them Listening Party",
                tier="Listening Session Pass",
                qty=1, unit_price=30000, status="confirmed",
                ref=ref(), channel="bank_transfer",
                created_at=utc(-15, 11),
            ),
            # Upcoming — confirmed
            dict(
                event="Detty December Kickoff: Pool Party & Afrobeats",
                tier="Premium",
                qty=2, unit_price=35000, status="confirmed",
                ref=ref(), channel="card",
                created_at=utc(-3, 16),
            ),
            dict(
                event="Flytime Music Festival 2026",
                tier="Golden Circle",
                qty=1, unit_price=75000, status="confirmed",
                ref=ref(), channel="card",
                created_at=utc(-2, 10),
            ),
            dict(
                event="New Afrika Shrine: Felabration Pre-Party",
                tier="General",
                qty=3, unit_price=5000, status="confirmed",
                ref=ref(), channel="ussd",
                created_at=utc(-1, 20),
            ),
        ]

        order_count = 0
        for o in ticket_orders:
            et = o["event"]
            tn = o["tier"]
            if et not in event_ids or tn not in tier_ids.get(et, {}):
                print(f"  skip order: {et} / {tn}")
                continue
            total = float(o["unit_price"] * o["qty"])
            event_start = next(e["start"] for e in events_data if e["title"] == et)
            is_past = event_start < datetime.now(timezone.utc)
            db.add(TicketOrder(
                id=str(uuid.uuid4()),
                user_id=user_ids["adaeze_sounds"],
                event_id=event_ids[et],
                tier_id=tier_ids[et][tn],
                quantity=o["qty"],
                unit_price=float(o["unit_price"]),
                total_price=total,
                status=o["status"],
                payment_reference=o["ref"],
                payment_channel=o.get("channel"),
                created_at=o["created_at"],
                # What a real confirmed order carries: the QR code value, the fee snapshot,
                # and (for events that already happened) a door check-in.
                ticket_code=str(uuid.uuid4()),
                platform_fee_percent=5.0,
                platform_fee_amount=round(total * 0.05, 2),
                checked_in_at=event_start + timedelta(minutes=40) if is_past else None,
            ))
            tier = (await db.execute(select(TicketTier).where(
                TicketTier.id == tier_ids[et][tn]))).scalar_one()
            tier.quantity_sold += o["qty"]  # keep "tickets left" consistent with the orders
            order_count += 1
        await db.commit()
        print(f"✓ {order_count} ticket orders for adaeze_sounds")

        # ── Notifications for adaeze ───────────────────────────────────────────
        detty_id = event_ids["Detty December Kickoff: Pool Party & Afrobeats"]
        flytime_id = event_ids["Flytime Music Festival 2026"]
        seun_id = user_ids["seun_pg"]
        tunde_id = user_ids["tunde_vibes"]
        dayo_id = user_ids["dayo_hype"]
        adaeze_id = user_ids["adaeze_sounds"]

        notifications = [
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="follow",
                title="seun_pg started following you",
                body=None,
                reference_id=user_ids["seun_pg"],
                reference_type="user",
                actor_id=seun_id,
                is_read=True,
                created_at=utc(-60),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="follow",
                title="tunde_vibes started following you",
                body=None,
                reference_id=tunde_id,
                reference_type="user",
                actor_id=tunde_id,
                is_read=True,
                created_at=utc(-55),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="going",
                title="seun_pg is going to Flytime Music Festival 2026",
                body="seun_pg and 2 others you follow are attending this event.",
                reference_id=flytime_id,
                reference_type="event",
                actor_id=seun_id,
                is_read=True,
                created_at=utc(-1, 10),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="event_reminder",
                title="Reminder: Detty December Kickoff in 4 days",
                body="Don't forget — Detty December Kickoff: Pool Party & Afrobeats is on Saturday at Hard Rock Hotel Lagos.",
                reference_id=detty_id,
                reference_type="event",
                actor_id=None,
                is_read=False,
                created_at=utc(-1, 8),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="going",
                title="dayo_hype is going to Stand Up Lagos: New Money Edition",
                body=None,
                reference_id=event_ids["Stand Up Lagos: New Money Edition"],
                reference_type="event",
                actor_id=dayo_id,
                is_read=False,
                created_at=utc(-2, 18),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="follow",
                title="dayo_hype started following you",
                body=None,
                reference_id=dayo_id,
                reference_type="user",
                actor_id=dayo_id,
                is_read=False,
                created_at=utc(-10),
            ),
            Notification(
                id=str(uuid.uuid4()),
                user_id=adaeze_id,
                type="event_invite",
                title="seun_pg invited you to co-host Naija Jollof Wars 2026",
                body="You've been invited to co-host this event. Accept to be listed as an organiser.",
                reference_id=event_ids["Naija Jollof Wars 2026"],
                reference_type="event",
                actor_id=seun_id,
                is_read=False,
                created_at=utc(-1, 12),
            ),
        ]
        for n in notifications:
            db.add(n)
        await db.commit()
        print(f"✓ {len(notifications)} notifications for adaeze_sounds")

        # ── Event saves for adaeze ─────────────────────────────────────────────
        saves = [
            "Flytime Music Festival 2026",
            "Lagos Comic Con 2026",
            "Naija Jollof Wars 2026",
        ]
        for title in saves:
            if title in event_ids:
                db.add(EventSave(
                    id=str(uuid.uuid4()),
                    user_id=adaeze_id,
                    event_id=event_ids[title],
                ))
        await db.commit()
        print(f"✓ {len(saves)} saves for adaeze_sounds")

        await _seed_extras(db, user_ids, event_ids, cat_ids, events_data)
        from app.demo_marketplace import seed_marketplace
        await seed_marketplace(db, user_ids, event_ids)

    # A --reset wipe also removes the ai_scout bot account and platform settings that
    # init_db() creates; recreate them now that the demo users are back in place.
    await init_db()

    print()
    print("🎉  Seed complete!")
    print("   Login: adaeze@turnup.ng / password123")
    print("   All users share password: password123")
    print()
    print("   Users:")
    for u in USERS:
        print(f"   • {u['email']}  ({u['username']}, {u['role']})")


async def _seed_extras(db, user_ids: dict, event_ids: dict, cat_ids: dict, events_data: list[dict]):
    """Data for the newer screens: organizer profiles & verification, communities, reviews,
    comments, a waitlist, and an event waiting in the admin approval queue."""
    import json
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    start_of = {e["title"]: e["start"] for e in events_data}

    # ── Organizer profiles (one verified, one with a pending verification request) ──
    profiles = {
        "adaeze_sounds": dict(organization_name="Adaeze Sounds Collective",
                              organizer_bio="Curating Lagos' best live music nights since 2019.",
                              website="https://adaezesounds.example", is_verified_organizer=True,
                              verification_status="approved", reviewed_at=utc(-40)),
        "seun_pg": dict(organization_name="PG Nights",
                        organizer_bio="Island nightlife, after-parties and award-season events.",
                        verification_status="none"),
        "dayo_hype": dict(organization_name="Hype House Events",
                          organizer_bio="Comedy, art and culture across Abuja and Lagos.",
                          verification_status="pending", verification_requested_at=utc(-2),
                          verification_note="We've run 30+ shows; links to past events on our site."),
    }
    for username, fields in profiles.items():
        db.add(OrganizerProfile(user_id=user_ids[username], **fields))
    print(f"✓ {len(profiles)} organizer profiles (1 verified, 1 pending review)")

    # ── Communities ───────────────────────────────────────────────────────────────
    communities = [
        dict(name="Lagos Afrobeats Heads", icon="🎶", city="Lagos", cat="music", creator="adaeze_sounds",
             desc="For everyone who lives for live Afrobeats: gig alerts, ticket swaps and meetups.",
             cover="https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?w=800",
             members={"seun_pg": "moderator", "tunde_vibes": "member", "chiamaka_lit": "member", "dayo_hype": "member"},
             events=["Flytime Music Festival 2026", "Detty December Kickoff: Pool Party & Afrobeats",
                     "Afrobeats & Asoebi: Terra Kulture Jazz Night"],
             links={"instagram": "https://instagram.com/lagosafrobeatsheads"}),
        dict(name="Naija Foodies", icon="🍲", city="Lagos", cat="food", creator="chiamaka_lit",
             desc="Jollof debates, pop-ups and the best street food in town.",
             cover="https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800",
             members={"tunde_vibes": "member", "adaeze_sounds": "member"},
             events=["Naija Jollof Wars 2026"], links={}),
        dict(name="Inner Circle Comedy", icon="😂", city="Abuja", cat="comedy", creator="dayo_hype",
             desc="Private: first dibs on tickets and secret shows for regulars.", private=True,
             cover=None, members={"chiamaka_lit": "member"},
             events=["Stand Up Lagos: New Money Edition"], links={}),
    ]
    for c in communities:
        cid = str(uuid.uuid4())
        db.add(Community(
            id=cid, name=c["name"], slug=slugify(c["name"], cid), description=c["desc"],
            cover_image=c["cover"], icon=c["icon"], city=c["city"], category_id=cat_ids.get(c["cat"]),
            is_private=c.get("private", False),
            invite_token=str(uuid.uuid4()) if c.get("private") else None,
            social_links=json.dumps(c["links"]), creator_id=user_ids[c["creator"]],
            member_count=1 + len(c["members"]), event_count=len(c["events"]),
        ))
        db.add(CommunityMember(community_id=cid, user_id=user_ids[c["creator"]], role="admin"))
        for username, role in c["members"].items():
            db.add(CommunityMember(community_id=cid, user_id=user_ids[username], role=role))
        for title in c["events"]:
            db.add(CommunityEvent(community_id=cid, event_id=event_ids[title], shared_by=user_ids[c["creator"]]))
    print(f"✓ {len(communities)} communities (1 private) with members and shared events")

    # ── Reviews on past events (reviewers must have attended: "going") ─────────────
    reviews = [
        ("Headies Awards After-Party 2025", "tunde_vibes", 5, "Best after-party of the year. The DJ line-up was unreal."),
        ("Headies Awards After-Party 2025", "chiamaka_lit", 4, "Great vibes, but the queue at the door was long."),
        ("Headies Awards After-Party 2025", "adaeze_sounds", 5, "Worth every naira. See you next year!"),
        ("Burna Boy: I Told Them Listening Party", "seun_pg", 5, "Hearing the album with that sound system... chills."),
        ("Burna Boy: I Told Them Listening Party", "dayo_hype", 4, "Intimate and well organised. Drinks were pricey."),
    ]
    for title, username, rating, body in reviews:
        eid, uid = event_ids[title], user_ids[username]
        attending = (await db.execute(select(EventAttendee).where(
            EventAttendee.event_id == eid, EventAttendee.user_id == uid))).scalar_one_or_none()
        if attending:
            attending.status = "going"
        else:
            db.add(EventAttendee(id=str(uuid.uuid4()), event_id=eid, user_id=uid, status="going"))
        db.add(EventReview(id=str(uuid.uuid4()), event_id=eid, user_id=uid, rating=rating, body=body,
                           created_at=start_of[title] + timedelta(days=1)))
    print(f"✓ {len(reviews)} reviews on past events")

    # ── Comments (with a reply thread) ────────────────────────────────────────────
    thread_root = str(uuid.uuid4())
    comments = [
        (thread_root, None, "Flytime Music Festival 2026", "tunde_vibes", "Who else is going on day 1? 🙌"),
        (None, thread_root, "Flytime Music Festival 2026", "chiamaka_lit", "Me! Golden Circle or nothing."),
        (None, None, "Naija Jollof Wars 2026", "adaeze_sounds", "Ghana jollof doesn't stand a chance."),
        (None, None, "Lagos Tech Fest: AI & Startups", "dayo_hype", "Will the talks be recorded?"),
    ]
    for i, (cid, parent, title, username, content) in enumerate(comments):
        db.add(Comment(id=cid or str(uuid.uuid4()), parent_id=parent, event_id=event_ids[title],
                       user_id=user_ids[username], content=content, created_at=now - timedelta(hours=10 - i)))
    print(f"✓ {len(comments)} comments")

    # ── A sold-out event with a waitlist ──────────────────────────────────────────
    yoga = "Sunrise Yoga at Bar Beach"
    ev = (await db.execute(select(Event).where(Event.id == event_ids[yoga]))).scalar_one()
    ev.capacity = max(ev.attendees_count, 1)
    ev.waitlist_enabled = True
    waiting = ["tunde_vibes", "dayo_hype", "seun_pg"]
    for pos, username in enumerate(waiting, start=1):
        db.add(EventWaitlist(id=str(uuid.uuid4()), event_id=ev.id, user_id=user_ids[username], position=pos))
    ev.waitlist_count = len(waiting)
    print(f"✓ waitlist of {len(waiting)} on '{yoga}' (at capacity)")

    # ── An organizer submission waiting for admin approval ────────────────────────
    eid = str(uuid.uuid4())
    db.add(Event(
        id=eid, slug=slugify("Abuja Spoken Word Night", eid), title="Abuja Spoken Word Night",
        description="An evening of poetry, live soul band and open mic. Bring your verses.",
        venue_name="Silverbird Galleria", address="Plot 1161 Memorial Drive", city="Abuja",
        start_date=utc(12, 19), end_date=utc(12, 23), is_free=True,
        host_id=user_ids["dayo_hype"], category_id=cat_ids.get("arts"),
        status="draft", review_status="pending", tags="poetry,open-mic,abuja",
    ))
    print("✓ 1 event waiting in the admin approval queue")

    await db.commit()

