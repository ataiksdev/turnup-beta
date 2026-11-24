"""Local context for the ranker: travel time, holidays, payday and rain (app/services/lagos_context.py)."""
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import delete

from app.models.discovery import WeatherForecast
from app.services import lagos_context as lc
from app.services.recommender import Viewer, score_event
from tests.test_recommendations import NOW, make_event, make_user

YABA = (6.5095, 3.3711)        # mainland
LEKKI = (6.4400, 3.4700)       # island side
SURULERE = (6.5000, 3.3500)    # mainland, about as far from Yaba as Lekki is... nearly
WAT = timezone(timedelta(hours=1))


def test_crossing_the_lagoon_in_rush_hour_takes_longest():
    tue_rush = datetime(2026, 12, 1, 19, 0, tzinfo=WAT)
    sun_noon = datetime(2026, 12, 6, 13, 0, tzinfo=WAT)
    cross_rush = lc.travel_minutes(YABA, LEKKI, tue_rush)
    cross_sun = lc.travel_minutes(YABA, LEKKI, sun_noon)
    same_side = lc.travel_minutes(YABA, SURULERE, tue_rush)
    assert cross_rush > cross_sun > same_side
    assert 60 <= cross_rush <= 120
    assert lc.in_lagos(*LEKKI) and not lc.in_lagos(9.06, 7.49)  # Abuja


def test_holidays_including_easter_and_observed_days():
    h = lc.nigerian_holidays(2026)
    assert h[date(2026, 4, 3)] == "Good Friday" and h[date(2026, 4, 6)] == "Easter Monday"
    assert h[date(2026, 10, 1)] == "Independence Day"
    assert h[date(2026, 3, 20)] == "Eid al-Fitr"
    # Democracy Day 2027 is a Saturday: observed on Monday 14 June.
    assert lc.holiday(date(2027, 6, 14)) == "Democracy Day (observed)"
    assert lc.free_next_day(date(2026, 9, 30))       # eve of Independence Day (a Wednesday)
    assert not lc.free_next_day(date(2026, 9, 29))


def test_payday_phases():
    assert lc.payday_phase(date(2026, 11, 27)) == "payday"
    assert lc.payday_phase(date(2026, 12, 2)) == "payday"
    assert lc.payday_phase(date(2026, 11, 18)) == "tight"
    assert lc.payday_phase(date(2026, 11, 8)) == "normal"
    assert lc.payday_phase(date(2027, 2, 28)) == "payday"


async def test_forecast_fetch_saves_hours_and_survives_an_outage(db, monkeypatch):
    hour = NOW().replace(minute=0, second=0, microsecond=0)
    def handler(request: httpx.Request):
        if request.url.params["latitude"] == "6.45":
            times = [(hour + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(3)]
            return httpx.Response(200, json={"hourly": {"time": times, "precipitation_probability": [20, 80, None]}})
        return httpx.Response(503)
    await db.execute(delete(WeatherForecast))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await lc.fetch_forecasts(db, client)
    assert result == {"hours": 2}
    chances = await lc.rain_chances(db, hour, hour + timedelta(hours=5))
    assert lc.rain_at(chances, "Lekki, Lagos", hour) == 0.8
    assert lc.rain_at(chances, "Abuja", hour) is None
    monkeypatch.setattr(lc.settings, "weather_enabled", False)
    assert "skipped" in await lc.fetch_forecasts(db)


async def _load(db, eid):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.event import Event
    return (await db.execute(select(Event).options(selectinload(Event.host), selectinload(Event.category))
                             .where(Event.id == eid))).scalar_one()


async def test_ranker_uses_travel_time_holidays_payday_and_rain(db):
    _, host = await make_user(db, role="organizer")
    # Christmas Day, 7 pm in Lagos (stored in UTC, as the app does); also "payday".
    when = datetime(2026, 12, 25, 18, 0, tzinfo=timezone.utc)
    beach = await _load(db, await make_event(db, host, title="Beach Party", start=when, is_free=False,
                                                 latitude=LEKKI[0], longitude=LEKKI[1], city="Lagos"))
    hall = await _load(db, await make_event(db, host, title="Hall Party", start=when, is_free=False,
                                                latitude=LEKKI[0], longitude=LEKKI[1], city="Lagos"))
    now = when - timedelta(days=2)
    v = Viewer(user=None, anonymous_id="x", now=now, lat=YABA[0], lon=YABA[1])
    hour = when.astimezone(timezone.utc)
    v.rain = {("lagos", hour): 0.9}
    b, h = score_event(v, beach, None), score_event(v, hall, None)
    assert b.parts["holiday"] > 0 and b.parts["payday"] > 0
    assert b.parts["rain"] < 0 and "rain" not in h.parts            # only the outdoor one
    assert b.travel_min and b.travel_min > 30
    assert h.score > b.score
    v.rain = {}
    assert score_event(v, beach, None).reason in ("On Christmas Day", f"About {b.travel_min:.0f} min away",
                                                  "Popular right now")
