"""Tests for the daily scout agent: RSS/Atom + listing-page discovery, drafting, dedup, and
admin endpoints.

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
        cover_image=f"https://cdn.example.com/{unique}.jpg",
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

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
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
    assert ev.cover_image == draft["cover_image"]


@pytest.mark.asyncio
async def test_run_daily_scout_skips_already_seen_urls(db, bot_user):
    source = await _make_source(db)
    url = _unique_url()
    draft_mock = AsyncMock(return_value=_fake_draft())

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[url])), \
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

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url(), _unique_url()])), \
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

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
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
async def test_run_daily_scout_with_source_id_only_polls_that_source(db, bot_user):
    target = await _make_source(db)
    # A second active source that must NOT be touched when we pass source_id=target.id.
    other = ScoutSource(id=str(uuid.uuid4()), name=f"Other {uuid.uuid4().hex[:6]}", url=_unique_url(), is_active=True)
    db.add(other)
    await db.commit()

    draft = _fake_draft()
    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        summary = await scout_agent.run_daily_scout(db, source_id=target.id)

    assert summary.sources_polled == 1
    await db.refresh(other)
    assert other.last_polled_at is None


@pytest.mark.asyncio
async def test_run_daily_scout_with_source_id_runs_paused_source(db, bot_user):
    source = await _make_source(db)
    source.is_active = False
    await db.commit()

    draft = _fake_draft()
    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        summary = await scout_agent.run_daily_scout(db, source_id=source.id)

    assert summary.sources_polled == 1
    assert summary.events_created == 1


@pytest.mark.asyncio
async def test_admin_scout_source_run_endpoint(db, client, admin_auth, bot_user):
    source = await _make_source(db)
    draft = _fake_draft()

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        resp = await client.post(f"/api/admin/scout/sources/{source.id}/run", headers=admin_auth["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources_polled"] == 1
    assert body["events_created"] == 1


@pytest.mark.asyncio
async def test_admin_scout_source_run_endpoint_404_for_unknown_source(client, admin_auth):
    resp = await client.post(f"/api/admin/scout/sources/{uuid.uuid4()}/run", headers=admin_auth["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_scout_log_reflects_run(db, client, admin_auth, bot_user):
    source = await _make_source(db)
    draft = _fake_draft()

    with patch.object(scout_agent, "_fetch_candidate_links", new=AsyncMock(return_value=[_unique_url()])), \
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


# ── Listing-page fallback (sites with no RSS/Atom feed) ────────────────────────

def test_parse_listing_links_filters_to_same_domain():
    html = """
    <html><body>
    <nav><a href="/about">About</a><a href="https://twitter.com/x">Twitter</a></nav>
    <div class="events">
      <a href="/events/afrobeats-night">Afrobeats Night</a>
      <a href="/events/comedy-show">Comedy Show</a>
      <a href="https://example.com/events/comedy-show">same link, absolute form</a>
      <a href="#top">Back to top</a>
      <a href="mailto:x@example.com">Email</a>
      <a href="">Empty href</a>
    </div>
    </body></html>
    """
    links = scout_agent._parse_listing_links(html, "https://example.com/events", limit=25)
    assert links == [
        "https://example.com/about",
        "https://example.com/events/afrobeats-night",
        "https://example.com/events/comedy-show",
    ]


def test_parse_listing_links_respects_limit():
    html = "".join(f'<a href="/events/{i}">Event {i}</a>' for i in range(50))
    links = scout_agent._parse_listing_links(html, "https://example.com/events", limit=10)
    assert len(links) == 10


def test_parse_listing_links_excludes_self():
    html = '<a href="/events">Back to listing</a><a href="/events/real-one">Real Event</a>'
    links = scout_agent._parse_listing_links(html, "https://example.com/events", limit=25)
    assert links == ["https://example.com/events/real-one"]


def test_parse_feed_links_returns_empty_for_plain_html():
    # This is the trigger condition _fetch_candidate_links uses to fall back to link-scraping.
    html = "<html><body><a href=\"/events/x\">X</a></body></html>"
    assert scout_agent._parse_feed_links(html) == []


@pytest.mark.asyncio
async def test_fetch_candidate_links_falls_back_to_listing_page():
    html = (
        "<html><body>"
        '<a href="/events/afrobeats-night">Afrobeats Night</a>'
        '<a href="https://elsewhere.com/spam">Spam</a>'
        "</body></html>"
    )

    class _FakeResponse:
        text = html
        url = "https://example.com/whats-on"

        def raise_for_status(self):
            pass

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    with patch.object(scout_agent.httpx, "AsyncClient", return_value=_FakeClient()):
        links = await scout_agent._fetch_candidate_links("https://example.com/whats-on")

    assert links == ["https://example.com/events/afrobeats-night"]


@pytest.mark.asyncio
async def test_run_daily_scout_via_listing_page_fallback(db, bot_user):
    """End-to-end: a source with no RSS feed still gets polled via the HTML fallback."""
    source = await _make_source(db)
    draft = _fake_draft()
    event_url = _unique_url()
    html = f'<html><body><a href="{event_url}">An Event</a></body></html>'

    class _FakeResponse:
        text = html
        url = source.url

        def raise_for_status(self):
            pass

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    with patch.object(scout_agent.httpx, "AsyncClient", return_value=_FakeClient()), \
         patch.object(scout_agent, "draft_event", new=AsyncMock(return_value=draft)):
        summary = await scout_agent.run_daily_scout(db)

    assert summary.events_created == 1
    ev = (await db.execute(select(Event).where(Event.title == draft["title"]))).scalar_one_or_none()
    assert ev is not None
