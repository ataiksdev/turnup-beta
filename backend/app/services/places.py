"""States and areas (docs/venues-spec.md 4.11).

Nigeria's 36 states plus the FCT are a fixed list. Areas (cities and districts) are an
admin-managed table, seeded here with the main places for launch; venues pick "Other" and an
admin adds or maps new ones.
"""
import math
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venue import Area

STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe",
    "Zamfara",
]
STATE_LABELS = {"FCT": "FCT (Abuja)"}

# (name, kind, lat, lng). Coordinates are approximate area centres, used for "near me" when
# a venue has no pin and for map framing.
SEED_AREAS: dict[str, list[tuple[str, str, float, float]]] = {
    "FCT": [
        ("Maitama", "district", 9.0882, 7.4934), ("Asokoro", "district", 9.0453, 7.5262),
        ("Wuse", "district", 9.0765, 7.4683), ("Wuse 2", "district", 9.0799, 7.4710),
        ("Garki", "district", 9.0336, 7.4885), ("Central Business District", "district", 9.0575, 7.4951),
        ("Jabi", "district", 9.0697, 7.4229), ("Utako", "district", 9.0700, 7.4410),
        ("Gudu", "district", 9.0080, 7.4720), ("Apo", "district", 8.9921, 7.5090),
        ("Life Camp", "district", 9.0786, 7.3990), ("Gwarinpa", "district", 9.1099, 7.4042),
        ("Katampe", "district", 9.1170, 7.4630), ("Kubwa", "city", 9.1580, 7.3310),
        ("Lugbe", "city", 8.9790, 7.3790), ("Karu", "city", 9.0150, 7.5660),
        ("Lokogoma", "district", 8.9840, 7.4660), ("Gwagwalada", "city", 8.9420, 7.0830),
    ],
    "Lagos": [
        ("Victoria Island", "district", 6.4281, 3.4219), ("Ikoyi", "district", 6.4549, 3.4366),
        ("Lekki", "district", 6.4698, 3.5852), ("Ajah", "district", 6.4667, 3.5667),
        ("Ikeja", "district", 6.6018, 3.3515), ("GRA Ikeja", "district", 6.5790, 3.3560),
        ("Surulere", "district", 6.5000, 3.3500), ("Yaba", "district", 6.5095, 3.3711),
        ("Maryland", "district", 6.5710, 3.3670), ("Gbagada", "district", 6.5550, 3.3880),
        ("Festac", "district", 6.4660, 3.2830), ("Ikorodu", "city", 6.6194, 3.5105),
        ("Epe", "city", 6.5841, 3.9834), ("Badagry", "city", 6.4316, 2.8876),
    ],
    "Rivers": [("Port Harcourt", "city", 4.8156, 7.0498), ("GRA Port Harcourt", "district", 4.8240, 7.0020),
               ("Trans-Amadi", "district", 4.8130, 7.0400)],
    "Oyo": [("Ibadan", "city", 7.3775, 3.9470), ("Ogbomosho", "city", 8.1335, 4.2407)],
    "Enugu": [("Enugu", "city", 6.4584, 7.5464), ("Nsukka", "city", 6.8567, 7.3958)],
    "Edo": [("Benin City", "city", 6.3350, 5.6037)],
    "Kano": [("Kano", "city", 12.0022, 8.5920)],
    "Akwa Ibom": [("Uyo", "city", 5.0377, 7.9128), ("Eket", "city", 4.6423, 7.9244)],
    "Cross River": [("Calabar", "city", 4.9757, 8.3417)],
    "Ogun": [("Abeokuta", "city", 7.1475, 3.3619), ("Ota", "city", 6.6800, 3.2300),
             ("Ijebu Ode", "city", 6.8200, 3.9200)],
    "Kaduna": [("Kaduna", "city", 10.5105, 7.4165), ("Zaria", "city", 11.0855, 7.7199)],
    "Delta": [("Asaba", "city", 6.2000, 6.7333), ("Warri", "city", 5.5167, 5.7500)],
    "Anambra": [("Awka", "city", 6.2120, 7.0740), ("Onitsha", "city", 6.1450, 6.7850)],
    "Imo": [("Owerri", "city", 5.4836, 7.0333)],
    "Abia": [("Umuahia", "city", 5.5250, 7.4940), ("Aba", "city", 5.1066, 7.3667)],
    "Plateau": [("Jos", "city", 9.8965, 8.8583)],
    "Kwara": [("Ilorin", "city", 8.4966, 4.5421)],
    "Osun": [("Osogbo", "city", 7.7827, 4.5418), ("Ile-Ife", "city", 7.4824, 4.5603)],
    "Ondo": [("Akure", "city", 7.2571, 5.2058)],
    "Ekiti": [("Ado Ekiti", "city", 7.6211, 5.2214)],
    "Bayelsa": [("Yenagoa", "city", 4.9267, 6.2676)],
    "Nasarawa": [("Lafia", "city", 8.4939, 8.5153), ("Keffi", "city", 8.8490, 7.8730)],
    "Niger": [("Minna", "city", 9.6139, 6.5569)],
    "Kogi": [("Lokoja", "city", 7.8023, 6.7333)],
    "Benue": [("Makurdi", "city", 7.7322, 8.5391)],
    "Bauchi": [("Bauchi", "city", 10.3158, 9.8442)],
    "Borno": [("Maiduguri", "city", 11.8311, 13.1510)],
    "Sokoto": [("Sokoto", "city", 13.0059, 5.2476)],
    "Adamawa": [("Yola", "city", 9.2035, 12.4954)],
    "Ebonyi": [("Abakaliki", "city", 6.3249, 8.1137)],
    "Gombe": [("Gombe", "city", 10.2897, 11.1673)],
    "Jigawa": [("Dutse", "city", 11.7566, 9.3390)],
    "Katsina": [("Katsina", "city", 12.9908, 7.6018)],
    "Kebbi": [("Birnin Kebbi", "city", 12.4539, 4.1975)],
    "Taraba": [("Jalingo", "city", 8.8937, 11.3600)],
    "Yobe": [("Damaturu", "city", 11.7470, 11.9608)],
    "Zamfara": [("Gusau", "city", 12.1628, 6.6614)],
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize_state(value: str) -> str | None:
    """Accepts 'fct', 'Abuja', 'FCT (Abuja)', 'akwa ibom'. Returns the canonical name or None."""
    v = (value or "").strip().lower()
    if v in ("abuja", "fct (abuja)", "federal capital territory"):
        return "FCT"
    for s in STATES:
        if s.lower() == v:
            return s
    return None


async def ensure_areas(db: AsyncSession) -> int:
    """Insert seed areas that don't exist yet. Never touches admin edits."""
    existing = {(s, slug) for s, slug in (await db.execute(select(Area.state, Area.slug))).all()}
    added = 0
    for state, areas in SEED_AREAS.items():
        for i, (name, kind, lat, lng) in enumerate(areas):
            slug = slugify(name)
            if (state, slug) in existing:
                continue
            db.add(Area(state=state, name=name, slug=slug, kind=kind,
                        latitude=lat, longitude=lng, sort_order=i))
            added += 1
    if added:
        await db.flush()
    return added


async def area_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Area))).scalar_one()


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """A cheap SQL pre-filter for radius searches; exact distance is checked in Python."""
    dlat = radius_m / 111_320.0
    dlng = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng
