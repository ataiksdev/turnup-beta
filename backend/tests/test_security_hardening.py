"""Tests for the four hardening items from the security audit:

1. Refuse to boot with the default SECRET_KEY outside debug mode.
2. Rate limiting extended to checkout/refund/checkin/comment/review/follow.
3. SSRF guard on the AI-agent/scout-agent outbound URL fetches.
4. AI-draft image upload is bounded before being fully read into memory.

Note: conftest's `engine`/`db`/`client` fixtures are session-scoped, and slowapi's Limiter
keeps its counters in a process-global in-memory store (not reset between tests). The rate
limit test explicitly calls `limiter.reset()` before and after so it doesn't pollute --
or get polluted by -- any other test in the session.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.config import Settings
from app.middleware.rate_limit import limiter
from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.user import User
from app.services.ai_agent import MAX_IMAGE_BYTES
from app.services.auth import create_access_token
from app.services.url_safety import UnsafeURLError, _validate_url, fetch_safely


def _unique() -> str:
    return uuid.uuid4().hex[:10]


async def _make_auth(db, role: str) -> tuple[dict, str]:
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    unique = _unique()
    db.add(User(
        id=user_id, username=f"{role}_{unique}", email=f"{role}_{unique}@example.com",
        full_name=role.title(), role=role, is_active=True, is_deleted=False,
    ))
    db.add(UserSession(
        id=str(uuid.uuid4()), user_id=user_id, jti=jti, is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    ))
    await db.commit()
    token, _ = create_access_token(user_id, jti)
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest_asyncio.fixture
async def buyer_auth(db):
    return await _make_auth(db, "attendee")


@pytest_asyncio.fixture
async def organizer_auth(db):
    return await _make_auth(db, "organizer")


@pytest_asyncio.fixture
async def admin_auth(db):
    return await _make_auth(db, "admin")


async def _make_event(db, host_id: str) -> str:
    unique = _unique()
    start = datetime.now(timezone.utc) + timedelta(days=5)
    event = Event(
        id=str(uuid.uuid4()), slug=f"event-{unique}", title=f"Test Event {unique}",
        description="A test event.", venue_name="Test Venue", address="1 Test St",
        city="Lagos", country="Nigeria", start_date=start, end_date=start + timedelta(hours=3),
        host_id=host_id, status="published", review_status="approved",
    )
    db.add(event)
    await db.commit()
    return event.id


# ── 1. SECRET_KEY fail-closed ─────────────────────────────────────────────────────

def test_default_secret_key_rejected_outside_debug():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(debug=False, secret_key="changeme")


def test_default_secret_key_allowed_in_debug():
    s = Settings(debug=True, secret_key="changeme")
    assert s.secret_key == "changeme"


def test_real_secret_key_allowed_outside_debug():
    s = Settings(debug=False, secret_key="a-real-production-secret")
    assert s.secret_key == "a-real-production-secret"


# ── 2. Rate limiting ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_creation_is_rate_limited(client, db, organizer_auth, buyer_auth):
    _, organizer_id = organizer_auth
    headers, _ = buyer_auth
    event_id = await _make_event(db, organizer_id)

    limiter.reset()
    try:
        statuses = []
        for i in range(21):
            resp = await client.post(
                f"/api/social/events/{event_id}/comments",
                json={"content": f"comment {i}"},
                headers=headers,
            )
            statuses.append(resp.status_code)
        assert statuses[:20] == [201] * 20
        assert statuses[20] == 429
    finally:
        limiter.reset()


# ── 3. SSRF guard ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejects_loopback_url():
    with pytest.raises(UnsafeURLError):
        await _validate_url("http://127.0.0.1/secret")


@pytest.mark.asyncio
async def test_rejects_private_ip_url():
    with pytest.raises(UnsafeURLError):
        await _validate_url("http://10.0.0.5/internal")


@pytest.mark.asyncio
async def test_rejects_cloud_metadata_link_local_url():
    with pytest.raises(UnsafeURLError):
        await _validate_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        await _validate_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_allows_public_url():
    await _validate_url("https://example.com/page")  # should not raise


@pytest.mark.asyncio
async def test_fetch_safely_blocks_redirect_to_private_ip():
    """The initial URL is public, but it 302s to a loopback address -- must still be blocked,
    since a naive check of only the first URL would miss this."""
    class _RedirectResp:
        is_redirect = True
        headers = {"location": "http://127.0.0.1/admin"}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _RedirectResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        with pytest.raises(UnsafeURLError):
            await fetch_safely("https://example.com/redirector", timeout=5, user_agent="test")


# ── 4. AI-draft image upload size cap ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_draft_rejects_oversized_image(client, admin_auth):
    headers, _ = admin_auth
    oversized = b"x" * (MAX_IMAGE_BYTES + 1)
    resp = await client.post(
        "/api/admin/events/draft",
        data={"text": "A cool event happening this weekend."},
        files={"image": ("flyer.jpg", oversized, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 413
