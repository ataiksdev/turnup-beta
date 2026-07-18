"""Tests for the recurring-event series backend."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.event import Event, EventSeries
from app.models.auth_tokens import UserSession
from app.models.user import User
from app.routers.series import _next_occurrence
from app.services.auth import create_access_token


# ── Shared fixture ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def organizer_auth(db):
    """Insert a fresh organizer user + session; return (user_id, auth_headers)."""
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())

    user = User(
        id=user_id,
        username=f"org_{user_id[:8]}",
        role="organizer",
        is_active=True,
        is_deleted=False,
    )
    db.add(user)

    session_obj = UserSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        jti=jti,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(session_obj)
    await db.commit()

    token, _ = create_access_token(user_id, jti)
    return {
        "user_id": user_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _series_payload(**overrides) -> dict:
    """Base valid payload for POST /api/series."""
    base = {
        "title": "Test Recurring Series",
        "description": "A test series",
        "recurrence_rule": "weekly",
        "occurrences": 4,
        "event_title": "Weekly Tech Meetup",
        "event_description": "A weekly gathering for tech enthusiasts in Lagos.",
        "venue_name": "Tech Hub Lagos",
        "address": "123 Innovation Drive",
        "city": "Lagos",
        "start_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).isoformat(),
    }
    base.update(overrides)
    return base


# ── Unit tests: _next_occurrence ────────────────────────────────────────────

def test_next_occurrence_weekly():
    dt = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    result = _next_occurrence(dt, "weekly")
    assert result == datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)


def test_next_occurrence_biweekly():
    dt = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    result = _next_occurrence(dt, "bi-weekly")
    assert result == datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)


def test_next_occurrence_monthly():
    dt = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    result = _next_occurrence(dt, "monthly")
    assert result == datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def test_next_occurrence_bimonthly():
    dt = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    result = _next_occurrence(dt, "bi-monthly")
    assert result == datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)


def test_next_occurrence_monthly_end_of_month():
    """Jan 31 + 1 month should clamp to Feb 28 (non-leap year)."""
    dt = datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc)
    result = _next_occurrence(dt, "monthly")
    assert result == datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc)


# ── Integration: POST /api/series ───────────────────────────────────────────

async def test_create_series_weekly(client, organizer_auth):
    payload = _series_payload(occurrences=4, recurrence_rule="weekly")
    resp = await client.post("/api/series", json=payload, headers=organizer_auth["headers"])
    assert resp.status_code == 201
    data = resp.json()

    assert data["recurrence_rule"] == "weekly"
    assert data["total_occurrences"] == 4
    assert len(data["events"]) == 4

    def _as_utc(s: str) -> datetime:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    starts = [_as_utc(e["start_date"]) for e in data["events"]]
    for i in range(1, len(starts)):
        diff = starts[i] - starts[i - 1]
        assert diff == timedelta(weeks=1), f"Gap at index {i} was {diff}"


async def test_create_series_generates_slugs(client, organizer_auth):
    payload = _series_payload(occurrences=6, recurrence_rule="weekly")
    resp = await client.post("/api/series", json=payload, headers=organizer_auth["headers"])
    assert resp.status_code == 201
    slugs = [e["slug"] for e in resp.json()["events"]]
    assert len(slugs) == len(set(slugs)), "Duplicate slugs found"


async def test_get_series(client, organizer_auth):
    payload = _series_payload(occurrences=3, recurrence_rule="weekly")
    post_resp = await client.post("/api/series", json=payload, headers=organizer_auth["headers"])
    assert post_resp.status_code == 201
    series_id = post_resp.json()["id"]

    get_resp = await client.get(f"/api/series/{series_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert data["id"] == series_id
    def _as_utc(s: str) -> datetime:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    starts = [_as_utc(e["start_date"]) for e in data["events"]]
    assert starts == sorted(starts), "Events are not sorted by start_date"


async def test_delete_series_nullifies_series_id(client, db, organizer_auth):
    payload = _series_payload(occurrences=3, recurrence_rule="weekly")
    post_resp = await client.post("/api/series", json=payload, headers=organizer_auth["headers"])
    assert post_resp.status_code == 201
    series_data = post_resp.json()
    series_id = series_data["id"]
    event_ids = [e["id"] for e in series_data["events"]]
    assert event_ids, "No events in series to check"

    del_resp = await client.delete(
        f"/api/series/{series_id}", headers=organizer_auth["headers"]
    )
    assert del_resp.status_code == 204

    # Series should be gone
    get_resp = await client.get(f"/api/series/{series_id}")
    assert get_resp.status_code == 404

    # Events must still exist but with series_id = NULL
    for eid in event_ids:
        evt = (await db.execute(select(Event).where(Event.id == eid))).scalar_one_or_none()
        assert evt is not None, f"Event {eid} was deleted — should have been kept"
        assert evt.series_id is None, f"Event {eid} still has series_id set"


# ── Rolling horizon tests ────────────────────────────────────────────────────

async def test_series_only_creates_events_within_3_months(client, organizer_auth):
    """20 weekly events starting today: only those within 92 days should be created."""
    today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    payload = _series_payload(
        occurrences=20,
        recurrence_rule="weekly",
        start_date=today.isoformat(),
        end_date=(today + timedelta(hours=2)).isoformat(),
    )
    resp = await client.post("/api/series", json=payload, headers=organizer_auth["headers"])
    assert resp.status_code == 201
    data = resp.json()

    # Fewer than 20 events materialised
    assert len(data["events"]) < 20
    # next_occurrence_date is set (some are pending)
    assert data["next_occurrence_date"] is not None
    # total_occurrences preserved
    assert data["total_occurrences"] == 20


async def test_get_series_auto_advances(client, db, organizer_auth):
    """
    Manually insert a series whose next_occurrence_date is tomorrow.
    A GET should trigger auto-advance and create a new event for that date.
    """
    user_id = organizer_auth["user_id"]
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    yesterday = now - timedelta(days=1)

    series_id = str(uuid.uuid4())
    series = EventSeries(
        id=series_id,
        title="Auto Advance Series",
        description="Testing auto-advance on GET",
        recurrence_rule="weekly",
        organizer_id=user_id,
        total_occurrences=5,
        next_occurrence_date=tomorrow,
    )
    db.add(series)

    # One existing event to serve as the template for auto-advance
    eid = str(uuid.uuid4())
    existing_event = Event(
        id=eid,
        title="Auto Advance Event",
        slug=f"auto-advance-event-{eid[:8]}",
        description="This is an existing event used as a template for auto-advance.",
        venue_name="Test Venue",
        address="1 Test Road",
        city="Lagos",
        start_date=yesterday,
        end_date=yesterday + timedelta(hours=2),
        status="published",
        host_id=user_id,
        series_id=series_id,
    )
    db.add(existing_event)
    await db.commit()

    # GET the series — should trigger auto-advance
    resp = await client.get(f"/api/series/{series_id}")
    assert resp.status_code == 200
    data = resp.json()

    event_starts = [
        datetime.fromisoformat(e["start_date"]).replace(tzinfo=timezone.utc)
        if datetime.fromisoformat(e["start_date"]).tzinfo is None
        else datetime.fromisoformat(e["start_date"])
        for e in data["events"]
    ]

    # More events than the original 1
    assert len(data["events"]) > 1, (
        f"Expected auto-advance to create events, got {len(data['events'])} events"
    )
    # One of the events should be at or near tomorrow
    tomorrow_utc = tomorrow.replace(tzinfo=timezone.utc) if tomorrow.tzinfo is None else tomorrow
    near_tomorrow = [
        s for s in event_starts
        if abs((s - tomorrow_utc).total_seconds()) < 60
    ]
    assert near_tomorrow, (
        f"No event found near tomorrow ({tomorrow_utc}). "
        f"Got start dates: {event_starts}"
    )
