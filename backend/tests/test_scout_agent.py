"""Tests for the daily RSS scout agent: feed parsing, drafting, dedup, and admin endpoints.

Note: conftest's `engine`/`db` fixtures are session-scoped (data persists across tests in this
file), so every test uses unique URLs/titles and scopes its assertions to rows it created itself,
rather than asserting on whole-table counts.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.config import settings
from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.scout import ScoutedItem, ScoutSource
from app.models.user import User
from app.services import scout_agent
from app.services.auth import create_access_token


@pytest_asyncio.fixture
async def bot_user(db):
    # Idempotent: mirrors app.database._ensure_scout_bot, since the bot may already exist
    # from an earlier test in this session-scoped DB.
    existing = (await db.execute(select(User).where(User.username == settings.scout_bot_username))).scalar_one_or_none()
    if existing:
        return existing.id
    user_id = str(uuid.uuid4())
    db.add(User(
        id=user_id, username=settings.scout_bot_username, full_name="Turnup Scout",
        role="moderator", is_active=True, is_deleted=False,
    ))
    await db.commit()
    return user_id


@pytest_asyncio.fixture
async def admin_auth(db):
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    db.add(User(
        id=user_id, username=f"admin_{user_id[:8]}", full_name="Admin",
        role="admin", is_active=True, is_deleted=False,
    ))
    db.add(UserSession(
        id=str(uuid.uuid4()), user_id=user_id, jti=jti, is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    await db.commit()
    token, _ = create_access_token(user_id, jti)
    return {"headers": {"Authorization": f"Bearer {token}"}}


def _fake_draft(**overrides) -> dict:
    unique = uuid.uuid4().hex[:10]
    start = datetime.now(timezone.utc) + timedelta(days=5)
    base = dict(
        title=f"Afrobeats Night {unique}", description="A great night of live afrobeats music downtown.",
        venue_name=f"The Venue {unique}", address="123 Main St", city="Lagos", country="Nigeria",
        start_date=start.isoformat(), end_date=(start + timedelta(hours=3)).isoformat(),
        is_free=True, price_min=None, price_max=None, currency="NGN",
        event_type="physical", category_guess="Music", tags="afrobeats",
        confidence_notes="explicit in text",
    )
    base.update(overrides)
    return base


async def _make_source(db) -> ScoutSource:
    """A single active source, scoped to this test: deactivates any sources left over from
    other tests in the shared DB so run_daily_scout only ever touches this one."""
    await db.execute(update(ScoutSource).values(is_active=False))
    source = ScoutSource(
        id=str(uuid.uuid4()), name=f"Test Feed {uuid.uuid4().hex[:6]}",
        url=f"https://example.com/{uuid.uuid4().hex}/feed.xml", is_active=True,
    )
    db.add(source)
    await db.commit()
    return source


def _unique_url() -> str:
    return f"https://example.com/{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_run_daily_scout_creates_pending_event(db, bot_user):
    source = await _make_source(db)
    draft = _fake_draft()

    with patch.object(scout_agent, "_fetch_feed_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        summary = await scout_agent.run_daily_scout(db)

    assert summary.sources_polled == 1
    assert summary.items_seen == 1
    assert summary.events_created == 1

    items = (await db.execute(select(ScoutedItem).where(ScoutedItem.source_id == source.id))).scalars().all()
    assert len(items) == 1
    assert items[0].status == "created"

    ev = (await db.execute(select(Event).where(Event.title == draft["title"]))).scalar_one_or_none()
    assert ev is not None
    assert ev.review_status == "pending"
    assert ev.status == "draft"
    assert ev.created_via == "ai_agent"
    assert ev.host_id == bot_user


@pytest.mark.asyncio
async def test_run_daily_scout_skips_already_seen_urls(db, bot_user):
    source = await _make_source(db)
    url = _unique_url()
    draft_mock = AsyncMock(return_value=_fake_draft())

    with patch.object(scout_agent, "_fetch_feed_links", new=AsyncMock(return_value=[url])), \
         patch.object(scout_agent, "draft_event", new=draft_mock):
        summary1 = await scout_agent.run_daily_scout(db)
        summary2 = await scout_agent.run_daily_scout(db)

    assert summary1.events_created == 1
    # Second run sees the same feed link, but it's already recorded in ScoutedItem.
    assert summary2.items_seen == 0
    assert summary2.events_created == 0
    assert draft_mock.await_count == 1

    items = (await db.execute(select(ScoutedItem).where(ScoutedItem.source_id == source.id))).scalars().all()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_run_daily_scout_skips_duplicate_title(db, bot_user):
    await _make_source(db)
    shared_draft = _fake_draft()

    with patch.object(scout_agent, "_fetch_feed_links", new=AsyncMock(return_value=[_unique_url(), _unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=shared_draft)):
        summary = await scout_agent.run_daily_scout(db)

    # Both feed links draft to the same title/venue/date -> only the first becomes an Event.
    assert summary.events_created == 1
    assert summary.skipped_duplicate == 1

    events = (await db.execute(select(Event).where(Event.title == shared_draft["title"]))).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_run_daily_scout_skips_non_events(db, bot_user):
    source = await _make_source(db)
    draft = _fake_draft(title="", start_date="")

    with patch.object(scout_agent, "_fetch_feed_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        summary = await scout_agent.run_daily_scout(db)

    assert summary.skipped_no_event == 1
    assert summary.events_created == 0

    items = (await db.execute(select(ScoutedItem).where(ScoutedItem.source_id == source.id))).scalars().all()
    assert len(items) == 1
    assert items[0].status == "skipped_no_event"
    assert items[0].event_id is None


@pytest.mark.asyncio
async def test_run_daily_scout_requires_bot_account(db):
    await _make_source(db)
    # Guaranteed not to exist, regardless of other tests' leftover state in the shared DB.
    missing_username = f"no_such_bot_{uuid.uuid4().hex[:8]}"
    with patch.object(settings, "scout_bot_username", missing_username):
        with pytest.raises(RuntimeError):
            await scout_agent.run_daily_scout(db)


@pytest.mark.asyncio
async def test_admin_scout_sources_crud(client, admin_auth):
    create_resp = await client.post(
        "/api/admin/scout/sources",
        json={"name": "Lagos Events Blog", "url": _unique_url() + "/rss"},
        headers=admin_auth["headers"],
    )
    assert create_resp.status_code == 201
    source_id = create_resp.json()["id"]
    assert create_resp.json()["is_active"] is True

    list_resp = await client.get("/api/admin/scout/sources", headers=admin_auth["headers"])
    assert list_resp.status_code == 200
    assert any(s["id"] == source_id for s in list_resp.json())

    patch_resp = await client.patch(
        f"/api/admin/scout/sources/{source_id}",
        json={"is_active": False},
        headers=admin_auth["headers"],
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/admin/scout/sources/{source_id}", headers=admin_auth["headers"])
    assert delete_resp.status_code == 204

    list_resp2 = await client.get("/api/admin/scout/sources", headers=admin_auth["headers"])
    assert not any(s["id"] == source_id for s in list_resp2.json())


@pytest.mark.asyncio
async def test_admin_scout_log_reflects_run(db, client, admin_auth, bot_user):
    source = await _make_source(db)
    draft = _fake_draft()

    with patch.object(scout_agent, "_fetch_feed_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        await scout_agent.run_daily_scout(db)

    # Log is ordered newest-first, so this run's entry is at the top regardless of what
    # earlier tests left in the (shared) log table.
    log_resp = await client.get("/api/admin/scout/log?limit=1", headers=admin_auth["headers"])
    assert log_resp.status_code == 200
    entries = log_resp.json()
    assert len(entries) == 1
    assert entries[0]["source_name"] == source.name
    assert entries[0]["status"] == "created"
    assert entries[0]["event_title"] == draft["title"]
