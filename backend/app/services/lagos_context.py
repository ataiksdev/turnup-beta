"""Local context for the ranker (docs/recommendations-spec.md): travel time in Lagos traffic
instead of straight-line distance, rain, payday and public holidays.

All of it is deterministic from the date and coordinates except the rain forecast, which the
worker fetches hourly from Open-Meteo (free, no key) into `weather_forecasts`. If that host
can't be reached, there is simply no rain adjustment.
"""
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.discovery import WeatherForecast
from app.services.rec_features import haversine_km

logger = logging.getLogger("turnup.context")
LAGOS_TZ = timezone(timedelta(hours=1))

# ── Travel time ─────────────────────────────────────────────────────────────────

# Greater Lagos, roughly Badagry to Epe, Ikorodu to the coast.
LAGOS_BOX = (6.35, 6.75, 2.70, 4.10)  # lat_min, lat_max, lon_min, lon_max
ROAD_FACTOR = 1.4                     # roads vs straight line
SPEED_KMH = {"rush": 15.0, "day": 22.0, "night": 32.0}
BRIDGE_MINUTES = {"rush": 35.0, "day": 15.0, "night": 8.0}  # crossing the lagoon


def in_lagos(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and \
        LAGOS_BOX[0] <= lat <= LAGOS_BOX[1] and LAGOS_BOX[2] <= lon <= LAGOS_BOX[3]


def on_island(lat: float, lon: float) -> bool:
    """Lagos Island, Ikoyi, Victoria Island, Lekki and Ajah: south of the lagoon, east of the
    harbour. Getting there from the mainland means a bridge."""
    return lat < 6.47 and lon > 3.38


def traffic_period(when: datetime) -> str:
    local = when.astimezone(LAGOS_TZ)
    weekday, hour = local.weekday() < 5, local.hour
    if weekday and (6 <= hour < 10 or 16 <= hour < 21):
        return "rush"
    return "night" if hour >= 22 or hour < 6 else "day"


def travel_minutes(origin: tuple[float, float], dest: tuple[float, float], arrive_by: datetime) -> float:
    """A rough door-to-door estimate for getting to an event that starts at `arrive_by`: road
    distance at the speed traffic allows then, plus a bridge if it crosses the lagoon."""
    period = traffic_period(arrive_by - timedelta(minutes=45))
    km = haversine_km(*origin, *dest) * ROAD_FACTOR
    minutes = km / SPEED_KMH[period] * 60
    if on_island(*origin) != on_island(*dest):
        minutes += BRIDGE_MINUTES[period]
    return round(minutes + 5, 1)  # getting in and out


# ── Payday ──────────────────────────────────────────────────────────────────────


def payday_phase(d: date) -> str:
    """Most salaries in Nigeria land from about the 25th. 'payday': the 25th to the 3rd;
    'tight': the 15th to the 24th; otherwise 'normal'."""
    last = monthrange(d.year, d.month)[1]
    if d.day >= min(25, last) or d.day <= 3:
        return "payday"
    return "tight" if 15 <= d.day <= 24 else "normal"


# ── Public holidays ─────────────────────────────────────────────────────────────

# Islamic holidays follow the moon and are confirmed by the Federal Government shortly before;
# these are the expected dates (extend each year).
ISLAMIC_HOLIDAYS = {
    date(2025, 3, 31): "Eid al-Fitr", date(2025, 4, 1): "Eid al-Fitr",
    date(2025, 6, 6): "Eid al-Adha", date(2025, 6, 9): "Eid al-Adha",
    date(2025, 9, 5): "Mawlid",
    date(2026, 3, 20): "Eid al-Fitr", date(2026, 3, 23): "Eid al-Fitr",
    date(2026, 5, 27): "Eid al-Adha", date(2026, 5, 28): "Eid al-Adha",
    date(2026, 8, 26): "Mawlid",
    date(2027, 3, 10): "Eid al-Fitr", date(2027, 3, 11): "Eid al-Fitr",
    date(2027, 5, 17): "Eid al-Adha", date(2027, 5, 18): "Eid al-Adha",
    date(2027, 8, 16): "Mawlid",
}


def _easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(year, month, (h + l - 7 * m + 114) % 31 + 1)


def nigerian_holidays(year: int) -> dict[date, str]:
    easter = _easter(year)
    days = {
        date(year, 1, 1): "New Year's Day", easter - timedelta(days=2): "Good Friday",
        easter + timedelta(days=1): "Easter Monday", date(year, 5, 1): "Workers' Day",
        date(year, 6, 12): "Democracy Day", date(year, 10, 1): "Independence Day",
        date(year, 12, 25): "Christmas Day", date(year, 12, 26): "Boxing Day",
    }
    days.update({d: n for d, n in ISLAMIC_HOLIDAYS.items() if d.year == year})
    # A holiday on a weekend is observed on the next working day.
    for d, name in list(days.items()):
        if d.weekday() >= 5:
            nxt = d + timedelta(days=7 - d.weekday())
            while nxt in days:
                nxt += timedelta(days=1)
            days[nxt] = f"{name} (observed)"
    return days


def holiday(d: date) -> str | None:
    return nigerian_holidays(d.year).get(d)


def free_next_day(d: date) -> bool:
    """No work tomorrow: a Friday or Saturday night, or the eve of a public holiday."""
    return d.weekday() in (4, 5) or holiday(d + timedelta(days=1)) is not None


# ── Rain ────────────────────────────────────────────────────────────────────────

OUTDOOR_WORDS = ("outdoor", "open air", "open-air", "beach", "park", "garden", "rooftop", "poolside",
                 "pool party", "festival", "carnival", "field", "boat", "cruise", "picnic")
FORECAST_CITIES = {
    "lagos": (6.45, 3.40), "abuja": (9.06, 7.49), "port harcourt": (4.82, 7.03),
    "ibadan": (7.38, 3.94), "kano": (12.00, 8.52), "enugu": (6.46, 7.55), "benin city": (6.34, 5.63),
}


def is_outdoor(title: str | None, tags: str | None, venue: str | None) -> bool:
    text = " ".join(filter(None, (title, tags, venue))).lower()
    return any(w in text for w in OUTDOOR_WORDS)


def city_key(city: str | None) -> str | None:
    c = (city or "").strip().lower()
    return next((k for k in FORECAST_CITIES if k in c), None)


async def fetch_forecasts(db: AsyncSession, client: httpx.AsyncClient | None = None) -> dict:
    """Worker job: hourly rain chances for the next 7 days, per city. Keeps the old rows if
    the request fails."""
    if not settings.weather_enabled:
        return {"skipped": "WEATHER_ENABLED is off"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    saved = 0
    try:
        for key, (lat, lon) in FORECAST_CITIES.items():
            try:
                r = await client.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": lat, "longitude": lon, "hourly": "precipitation_probability",
                    "forecast_days": 7, "timezone": "UTC"})
                r.raise_for_status()
                hourly = r.json()["hourly"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning("Weather for %s unavailable: %s", key, exc)
                continue
            await db.execute(delete(WeatherForecast).where(WeatherForecast.city == key))
            for t, p in zip(hourly["time"], hourly["precipitation_probability"]):
                if p is None:
                    continue
                db.add(WeatherForecast(city=key, hour=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                                       rain_chance=p / 100))
                saved += 1
        await db.commit()
    finally:
        if own:
            await client.aclose()
    return {"hours": saved}


async def rain_chances(db: AsyncSession, start: datetime, end: datetime) -> dict[tuple[str, datetime], float]:
    rows = (await db.execute(select(WeatherForecast.city, WeatherForecast.hour, WeatherForecast.rain_chance).where(
        WeatherForecast.hour >= start - timedelta(hours=1), WeatherForecast.hour <= end))).all()
    return {(c, (h if h.tzinfo else h.replace(tzinfo=timezone.utc))): p for c, h, p in rows}


def rain_at(forecast: dict, city: str | None, when: datetime) -> float | None:
    """The highest rain chance in the three hours from `when`, or None without a forecast."""
    key = city_key(city)
    if not key:
        return None
    hour = when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    found = [forecast.get((key, hour + timedelta(hours=i))) for i in range(3)]
    found = [p for p in found if p is not None]
    return max(found) if found else None
