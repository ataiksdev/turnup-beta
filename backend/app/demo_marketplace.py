"""Demo data for the venue marketplace and Turnup+ (docs/venues-spec.md), so every screen has
something to show: venues in Lagos and Abuja at each verification stage, an agent with visits,
enquiries and quotes, bookings at every stage (confirmed, fully paid, completed with a review,
cancelled with a refund the venue still has to pay in), a featured slot, member deals, a
venue-hosted event and a Turnup+ member.

Payment rows use fake references (demo_...): nothing here touches Paystack."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.event import Event
from app.models.user import User
from app.models.venue import (
    Agent, AgentVisit, Area, Deal, EnquiryMessage, FeaturedSlot, RefundRequest, Subscription, Venue,
    VenueBooking, VenueDocument, VenueEnquiry, VenueFollow, VenueMedia, VenueMember, VenuePayment,
    VenueQuote, VenueReview, VenueSpace,
)
from app.services.places import ensure_areas
from app.services.plus import ensure_plans

IMG = "https://images.unsplash.com/photo-{}?w=1200"

VENUES = [
    dict(key="pavilion", name="The Grand Pavilion", type="hall", state="Lagos", area="Lekki",
         address="12 Admiralty Way, Lekki Phase 1", lat=6.4474, lng=3.4723, pro=True,
         description="A 1,200-guest event centre with a 60-car park, two generators, bridal suite and a full stage.",
         amenities=["Parking", "Generator backup", "Air conditioning", "Stage", "Bridal suite", "Security"],
         photos=["1519167758481-83f550bb49b3", "1464366400600-7168b8af9bc3", "1505236858219-8359eb29e329"],
         spaces=[("Main hall", 800, 1200, 250_000_000, 400_000_000, "per_day"), ("Garden marquee", 200, 350, 90_000_000, None, "per_day")],
         verification="visit_passed", status="live", owner="bola_venues", legal="Grand Pavilion Events Ltd"),
    dict(key="skyline", name="Skyline Rooftop", type="lounge", state="Lagos", area="Victoria Island",
         address="Plot 4, Akin Adesola Street, Victoria Island", lat=6.4310, lng=3.4210, pro=False,
         description="Rooftop lounge with ocean views, DJ booth and private VIP section. Great for launches and after-parties.",
         amenities=["DJ booth", "Bar", "VIP section", "Ocean view", "Valet"],
         photos=["1514525253161-7a46d19cd819", "1470337458703-46ad1756a187"],
         spaces=[("Rooftop", 80, 250, 60_000_000, 120_000_000, "per_event")],
         verification="visit_passed", status="live", owner="bola_venues", legal="Skyline Hospitality Ltd"),
    dict(key="maitama", name="Maitama Garden Court", type="outdoor", state="FCT", area="Maitama",
         address="7 Aguiyi Ironsi Street, Maitama", lat=9.0880, lng=7.4930, pro=False,
         description="Landscaped garden for weddings and festivals, with marquee options and ample parking.",
         amenities=["Parking", "Generator backup", "Marquee", "Catering kitchen"],
         photos=["1464822759023-fed622ff2c3b", "1478146896981-b80fe463b330"],
         spaces=[("Garden", 400, 900, 150_000_000, 250_000_000, "per_day")],
         verification="documents_approved", status="live", owner="dayo_hype", legal="Garden Court Abuja Ltd"),
    dict(key="studio", name="Wuse Creative Studio", type="hotel_studio", state="FCT", area="Wuse 2",
         address="21 Adetokunbo Ademola Crescent, Wuse 2", lat=9.0800, lng=7.4720, pro=False,
         description="Daylight studio for shoots, workshops and intimate showcases.",
         amenities=["Natural light", "Sound system", "Projector", "Wi-Fi"],
         photos=["1497366216548-37526070297c"],
         spaces=[("Studio A", 40, 70, 15_000_000, None, "per_hour")],
         verification="documents_submitted", status="in_review", owner="seun_pg", legal="Wuse Creative Studio Enterprises"),
]


def utc(days: float, hour: int = 18) -> datetime:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


async def seed_marketplace(db, user_ids: dict, event_ids: dict) -> None:
    await ensure_areas(db)
    await ensure_plans(db)
    await db.flush()
    areas = {(a.state, a.name): a.id for a in (await db.execute(select(Area))).scalars().all()}

    venue_ids: dict[str, str] = {}
    space_ids: dict[str, list[str]] = {}
    for n, v in enumerate(VENUES):
        vid = str(uuid.uuid4())
        venue_ids[v["key"]] = vid
        db.add(Venue(
            id=vid, slug=v["key"] + "-" + vid[:4], name=v["name"], type=v["type"], description=v["description"],
            state=v["state"], area_id=areas.get((v["state"], v["area"])), address=v["address"],
            latitude=v["lat"], longitude=v["lng"], cover_image=IMG.format(v["photos"][0]),
            amenities=json.dumps(v["amenities"]), rules="No open flames indoors. Music ends at 1am.",
            phone="08030000000", email=f"bookings@{v['key']}.example", price_display="range" if v["key"] == "skyline" else "from",
            refund_preset="moderate", deposit_type="percent", deposit_value=30, balance_due_days=7,
            status=v["status"], verification_status=v["verification"], deposits_enabled=v["verification"] == "visit_passed",
            legal_name=v["legal"], cac_number=f"RC{1_402_000 + n}", registered_address=v["address"],
            paystack_subaccount_code=f"ACCT_demo_{v['key']}", bank_name="Guaranty Trust Bank", bank_account_last4="6789",
            bank_account_name=v["legal"].upper(), bank_name_match=True,
            is_pro=v["pro"], pro_until=utc(25) if v["pro"] else None, created_by_id=user_ids[v["owner"]],
            went_live_at=utc(-60) if v["status"] == "live" else None,
            followers_count=0,
        ))
        await db.flush()
        db.add(VenueMember(venue_id=vid, user_id=user_ids[v["owner"]], role="owner"))
        space_ids[v["key"]] = []
        for i, (name, seated, standing, pfrom, pto, unit) in enumerate(v["spaces"]):
            sid = str(uuid.uuid4())
            space_ids[v["key"]].append(sid)
            db.add(VenueSpace(id=sid, venue_id=vid, name=name, capacity_seated=seated, capacity_standing=standing,
                              price_from_kobo=pfrom, price_to_kobo=pto, price_unit=unit, sort_order=i))
        for i, ph in enumerate(v["photos"]):
            db.add(VenueMedia(venue_id=vid, kind="photo", url=IMG.format(ph), sort_order=i))
        for kind in ("cac", "owner_id", "site_photo"):
            # Placeholder records only: there's no real file behind them in demo data.
            db.add(VenueDocument(venue_id=vid, kind=kind, storage_key=f"demo-missing-{kind}.webp",
                                 original_filename=f"{kind}.jpg", content_type="image/webp", size_bytes=0,
                                 uploaded_by_id=user_ids[v["owner"]],
                                 status="approved" if v["verification"] != "documents_submitted" else "pending"))
    # Manager on the Pavilion team.
    db.add(VenueMember(venue_id=venue_ids["pavilion"], user_id=user_ids["tunde_vibes"], role="manager"))
    await db.flush()

    # ── Agent and visits ───────────────────────────────────────────────────────
    agent_id = user_ids["kemi_agent"]
    admin_id = user_ids["turnup_admin"]
    db.add(Agent(user_id=agent_id, states=json.dumps(["Lagos", "Ogun", "FCT"]), phone="08031111111",
                 created_by_id=admin_id))
    for key, status in (("pavilion", "passed"), ("skyline", "passed"), ("maitama", "scheduled")):
        db.add(AgentVisit(venue_id=venue_ids[key], agent_id=agent_id, status=status, assigned_by_id=admin_id,
                          scheduled_for=utc(-20 if status == "passed" else 3, 11),
                          checked_in_at=utc(-20, 11) if status == "passed" else None,
                          distance_from_venue_m=40 if status == "passed" else None,
                          checklist=json.dumps({"capacity": True, "photos": True, "exits": True, "power": True}) if status == "passed" else None,
                          notes="Matches the listing. Two working generators." if status == "passed" else None,
                          decided_at=utc(-20, 13) if status == "passed" else None))

    # ── Enquiries, quotes, bookings ────────────────────────────────────────────
    async def booking(venue_key: str, organizer: str, days: float, total: int, status: str, paid: int,
                      message: str, reply: str) -> VenueBooking:
        vid, sid = venue_ids[venue_key], space_ids[venue_key][0]
        starts, ends = utc(days, 16), utc(days, 23)
        e = VenueEnquiry(venue_id=vid, space_id=sid, organizer_id=user_ids[organizer], starts_at=starts, ends_at=ends,
                         guest_count=300, event_type="Concert", status="booked" if status != "quoted" else "quoted",
                         last_message_at=utc(-5))
        db.add(e)
        await db.flush()
        db.add(EnquiryMessage(enquiry_id=e.id, sender_id=user_ids[organizer], sender_side="organizer", body=message, created_at=utc(-10)))
        db.add(EnquiryMessage(enquiry_id=e.id, sender_id=user_ids["bola_venues"], sender_side="venue", body=reply, created_at=utc(-9)))
        q = VenueQuote(enquiry_id=e.id, space_id=sid, starts_at=starts, ends_at=ends, total_kobo=total,
                       deposit_kobo=total * 30 // 100, balance_due_days=7, refund_preset="moderate",
                       inclusions="Chairs, tables, cleaning and security. Power for 7 hours.",
                       valid_until=utc(5), status="sent" if status == "quoted" else "accepted",
                       created_by_id=user_ids["bola_venues"])
        db.add(q)
        await db.flush()
        db.add(EnquiryMessage(enquiry_id=e.id, sender_id=user_ids["bola_venues"], sender_side="venue",
                              body=f"Quote: ₦{total // 100:,}", quote_id=q.id, created_at=utc(-8)))
        if status == "quoted":
            return None
        b = VenueBooking(quote_id=q.id, enquiry_id=e.id, venue_id=vid, space_id=sid, organizer_id=user_ids[organizer],
                         starts_at=starts, ends_at=ends, total_kobo=total, deposit_kobo=q.deposit_kobo,
                         balance_due_at=starts - timedelta(days=7), paid_kobo=paid, commission_percent=8.0,
                         commission_kobo=paid * 8 // 100, refund_preset="moderate", status=status,
                         completed_at=ends + timedelta(days=2) if status == "completed" else None,
                         cancelled_at=utc(-1) if status.startswith("cancelled") else None,
                         cancel_reason="Our dates moved." if status.startswith("cancelled") else None)
        db.add(b)
        await db.flush()
        for kind, amount in (("deposit", q.deposit_kobo), ("balance", paid - q.deposit_kobo)):
            if amount > 0:
                db.add(VenuePayment(venue_id=vid, booking_id=b.id, payer_id=user_ids[organizer], kind=kind,
                                    amount_kobo=amount, commission_kobo=amount * 8 // 100,
                                    venue_share_kobo=amount - amount * 8 // 100,
                                    reference=f"demo_{uuid.uuid4().hex[:12]}", status="success", paid_at=utc(-7)))
        return b

    b1 = await booking("pavilion", "adaeze_sounds", 40, 300_000_000, "confirmed", 90_000_000,
                       "Hi! Is the main hall free for a 300-guest concert?", "Yes, it is. Sending you a quote now.")
    await booking("skyline", "seun_pg", 12, 100_000_000, "fully_paid", 100_000_000,
                  "Album launch for 150 guests, can we have the rooftop?", "Absolutely. Quote below.")
    done = await booking("pavilion", "dayo_hype", -20, 200_000_000, "completed", 200_000_000,
                         "Comedy special, 500 guests.", "Happy to host. Here's our quote.")
    cancelled = await booking("skyline", "adaeze_sounds", 50, 80_000_000, "cancelled_by_organizer", 24_000_000,
                              "Listening party for 80.", "Quote attached.")
    await booking("pavilion", "seun_pg", 70, 250_000_000, "quoted", 0,
                  "End-of-year party, around 600 guests?", "We can do that. Quote below.")
    db.add(VenueReview(venue_id=venue_ids["pavilion"], author_id=user_ids["dayo_hype"], kind="organizer",
                       booking_id=done.id, rating=5, body="Great sound, staff were on time, generators never failed.",
                       venue_reply="Thank you, Dayo. Come back soon!", venue_reply_at=utc(-15)))
    db.add(RefundRequest(booking_id=cancelled.id, venue_id=cancelled.venue_id, organizer_id=cancelled.organizer_id,
                         reason="organizer_cancelled", amount_kobo=24_000_000, due_at=utc(2), created_at=utc(-1)))
    v = (await db.execute(select(Venue).where(Venue.id == venue_ids["pavilion"]))).scalar_one()
    v.rating_organizers, v.reviews_organizers_count = 5.0, 1
    _ = b1

    # ── Follows, featured slot, deals, Turnup+ member, a venue-hosted event ────
    for user in ("tunde_vibes", "chiamaka_lit", "adaeze_sounds"):
        db.add(VenueFollow(user_id=user_ids[user], venue_id=venue_ids["skyline"]))
    (await db.execute(select(Venue).where(Venue.id == venue_ids["skyline"]))).scalar_one().followers_count = 3
    monday = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    monday -= timedelta(days=monday.weekday())
    db.add(FeaturedSlot(venue_id=venue_ids["pavilion"], scope="state", state="Lagos", week_start=monday,
                        ends_at=monday + timedelta(days=7), amount_kobo=5_000_000, payment_reference="demo_featured",
                        status="active"))
    db.add(Deal(venue_id=venue_ids["skyline"], title="Free entry before 10pm on Fridays", kind="free_entry",
                created_by_id=user_ids["bola_venues"], max_per_member=4))
    db.add(Deal(venue_id=venue_ids["skyline"], title="Free welcome cocktail", kind="free_item",
                created_by_id=user_ids["bola_venues"]))
    chiamaka = (await db.execute(select(User).where(User.id == user_ids["chiamaka_lit"]))).scalar_one()
    chiamaka.plus_until = utc(30)
    db.add(Subscription(plan_code="turnup_plus_monthly", product="turnup_plus", user_id=chiamaka.id,
                        status="active", reference="demo_sub_chiamaka", current_period_end=chiamaka.plus_until))
    db.add(Subscription(plan_code="venue_pro_monthly", product="venue_pro", user_id=user_ids["bola_venues"],
                        venue_id=venue_ids["pavilion"], status="active", reference="demo_sub_pavilion",
                        current_period_end=utc(25)))
    eid = str(uuid.uuid4())
    db.add(Event(id=eid, slug=f"skyline-sundowner-{eid[:8]}", title="Skyline Sundowner Sessions",
                 description="Sunset sets on the rooftop every Sunday: house, amapiano and afro-soul.",
                 cover_image=IMG.format("1470337458703-46ad1756a187"), venue_name="Skyline Rooftop",
                 address="Plot 4, Akin Adesola Street, Victoria Island", city="Victoria Island", country="NG",
                 latitude=6.4310, longitude=3.4210, start_date=utc(9, 17), end_date=utc(9, 23),
                 host_id=user_ids["bola_venues"], host_venue_id=venue_ids["skyline"], venue_id=venue_ids["skyline"],
                 status="published", review_status="approved", is_free=True, fast_lane_enabled=True,
                 members_only=False))
    await db.commit()
    print("✓ venue marketplace: 4 venues (2 visited, 1 live awaiting visit, 1 in review), agent kemi@turnup.ng, "
          "5 enquiries, 4 bookings, a refund awaiting the venue, featured slot, deals, Turnup+ member chiamaka@turnup.ng")


async def run_venues_only() -> None:
    """`python -m app.cli seed-venues`: add the venue demo data to a database that was seeded
    with the demo data before the venue marketplace existed (so `seed` refuses, and only
    `seed --reset` would add it, by wiping everything). Adds any missing demo accounts
    (e.g. bola@turnup.ng, kemi@turnup.ng, password123), then the venues. Runs only on a demo
    database, and only once."""
    from sqlalchemy import func, or_

    from app.database import AsyncSessionLocal, init_db
    from app.demo_data import USERS, SeedRefused
    from app.services.auth import hash_password

    await init_db()
    async with AsyncSessionLocal() as db:
        if not (await db.execute(select(User.id).where(User.username == "adaeze_sounds"))).first():
            raise SeedRefused("This doesn't look like a demo database (no adaeze_sounds account). "
                              "Run `python -m app.cli seed` on an empty database instead.")
        venues = (await db.execute(select(func.count(Venue.id)))).scalar()
        if venues:
            raise SeedRefused(f"The database already has {venues} venue(s); nothing to add.")

        added = []
        for u in USERS:
            taken = (await db.execute(select(User.id).where(
                or_(User.username == u["username"], User.email == u["email"])))).first()
            if taken:
                continue
            db.add(User(id=str(uuid.uuid4()), email=u["email"], username=u["username"], full_name=u["full_name"],
                        hashed_password=hash_password("password123"), bio=u.get("bio"),
                        avatar_url=u.get("avatar"), location=u.get("location"),
                        is_verified=u.get("verified", False), category_preferences=u.get("prefs"),
                        onboarding_completed=True, role=u.get("role", "attendee")))
            added.append(u["email"])
        await db.flush()
        if added:
            print(f"✓ added missing demo accounts: {', '.join(added)} (password123)")

        names = [u["username"] for u in USERS]
        user_ids = dict((await db.execute(select(User.username, User.id).where(User.username.in_(names)))).all())
        await seed_marketplace(db, user_ids, {})
