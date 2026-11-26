"""Agent connections: API keys, and turning what an outside bot submits (fields it already
extracted, or raw text / a link / a poster image for Turnup's AI to read) into an event waiting
for admin approval, then telling the bot how the review went.

Nothing an agent sends is published directly: every event is created as a draft with
review_status "pending", exactly like a scouted or moderator-submitted event, and goes live
only when an admin approves it in the Events queue.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent import AgentConnection, AgentSubmission
from app.models.event import Category, Event
from app.models.user import User
from app.schemas.admin import AIEventDraft
from app.services import ai_agent
from app.services.event_drafts import create_pending_event
from app.services.url_safety import post_json_safely

logger = logging.getLogger("turnup.agents")

API_KEY_PREFIX = "tuk_"
CREATED_VIA = "agent_api"
_MAX_INPUT_CHARS = 4000
# Statuses that used up the connection's daily allowance (did work, possibly an AI call).
_COUNTED_STATUSES = ("created", "skipped_duplicate", "skipped_no_event", "failed")
_CALLBACK_TIMEOUT = 10


# ── Keys and secrets ─────────────────────────────────────────────────────────

def new_api_key() -> tuple[str, str, str]:
    """Returns (key, sha256 hex, display prefix). Only the hash and prefix are stored."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, hash_api_key(key), key[:12]


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_callback_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    # Derived from SECRET_KEY: rotating SECRET_KEY means rotating callback secrets too.
    digest = hashlib.sha256(f"agent-connections:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str | None) -> str | None:
    return _fernet().encrypt(value.encode()).decode() if value else None


def decrypt(blob: str | None) -> str | None:
    if not blob:
        return None
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        logger.error("An agent connection's callback secret can't be decrypted (was SECRET_KEY changed?)")
        return None


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """X-Turnup-Signature: HMAC-SHA256 over "<timestamp>.<raw body>", hex, prefixed "sha256="."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def event_public_url(ev: Event) -> str:
    return f"{settings.frontend_url.rstrip('/')}/events/{ev.slug}"


# ── Limits and hosting ───────────────────────────────────────────────────────

async def used_today(db: AsyncSession, conn: AgentConnection) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return (await db.execute(
        select(func.count(AgentSubmission.id)).where(
            AgentSubmission.connection_id == conn.id,
            AgentSubmission.created_at >= since,
            AgentSubmission.status.in_(_COUNTED_STATUSES),
        )
    )).scalar_one()


async def host_id_for(db: AsyncSession, conn: AgentConnection) -> str:
    if conn.host_user_id:
        return conn.host_user_id
    bot = (await db.execute(
        select(User.id).where(User.username == settings.scout_bot_username)
    )).scalar_one_or_none()
    if not bot:
        raise RuntimeError(f"Scout bot account '{settings.scout_bot_username}' not found — run init_db first.")
    return bot


# ── Submitting ───────────────────────────────────────────────────────────────

@dataclass
class Submission:
    """What a bot sent: either `draft` (fields it already extracted) or raw material (text, a
    url, a poster image) for Turnup's AI drafter."""
    submitted_by: str | None = None
    external_id: str | None = None
    text: str | None = None
    url: str | None = None
    image_bytes: bytes | None = None
    image_media_type: str | None = None
    draft: AIEventDraft | None = None
    ticket_url: str | None = None


@dataclass
class SubmitResult:
    submission: AgentSubmission
    event: Event | None
    repeated: bool = False  # the same external_id was submitted before; nothing was redone


async def submit(db: AsyncSession, conn: AgentConnection, sub: Submission) -> SubmitResult:
    """Record a submission and, if it's within the limit and looks like a real event, create
    the event pending admin review. Never raises for bad input: the outcome is in .status."""
    if sub.external_id:
        existing = (await db.execute(
            select(AgentSubmission).where(
                AgentSubmission.connection_id == conn.id,
                AgentSubmission.external_id == sub.external_id,
            )
        )).scalar_one_or_none()
        if existing:
            ev = await db.get(Event, existing.event_id) if existing.event_id else None
            return SubmitResult(existing, ev, repeated=True)

    input_text = "\n".join(filter(None, [sub.url, sub.text, sub.draft.title if sub.draft else None]))
    record = AgentSubmission(
        connection_id=conn.id,
        submitted_by=(sub.submitted_by or None) and sub.submitted_by[:200],
        external_id=(sub.external_id or None) and sub.external_id[:200],
        input_text=input_text[:_MAX_INPUT_CHARS] or ("[image]" if sub.image_bytes else None),
    )
    conn.last_used_at = datetime.now(timezone.utc)

    async def _done(status: str, event: Event | None = None, note: str | None = None) -> SubmitResult:
        record.status = status
        record.event_id = event.id if event else None
        record.error_note = note
        db.add(record)
        await db.flush()
        return SubmitResult(record, event)

    if await used_today(db, conn) >= conn.daily_limit:
        return await _done("over_limit", note=f"Daily limit of {conn.daily_limit} reached")

    categories = (await db.execute(select(Category))).scalars().all()
    categories_by_name = {c.name.lower(): c.id for c in categories}

    draft = sub.draft
    if draft is None:
        try:
            raw = await ai_agent.draft_event(
                text=sub.text, url=sub.url, image_bytes=sub.image_bytes,
                image_media_type=sub.image_media_type,
                category_names=[c.name for c in categories],
            )
        except ai_agent.AIAgentError as e:
            return await _done("failed", note=str(e))
        draft = AIEventDraft(**raw)

    try:
        host_id = await host_id_for(db, conn)
    except RuntimeError as e:
        return await _done("failed", note=str(e))

    status, event = await create_pending_event(
        db, draft, host_id=host_id, created_via=CREATED_VIA,
        categories_by_name=categories_by_name, ticket_url=sub.ticket_url,
    )
    return await _done(status, event)


# ── Review callbacks ─────────────────────────────────────────────────────────

@dataclass
class ReviewCallback:
    url: str
    secret: str
    payload: dict


async def review_callback(db: AsyncSession, ev: Event) -> ReviewCallback | None:
    """After an admin approves or rejects an event, the callback to send to the connection
    that submitted it (once per outcome), or None."""
    if ev.review_status not in ("approved", "rejected"):
        return None
    row = (await db.execute(
        select(AgentSubmission, AgentConnection)
        .join(AgentConnection, AgentConnection.id == AgentSubmission.connection_id)
        .where(AgentSubmission.event_id == ev.id, AgentSubmission.status == "created")
        .order_by(AgentSubmission.created_at.asc())
        .limit(1)
    )).first()
    if not row:
        return None
    sub, conn = row
    secret = decrypt(conn.callback_secret_encrypted)
    if not conn.is_active or not conn.callback_url or not secret:
        return None
    if sub.notified_status == ev.review_status:
        return None
    sub.notified_status = ev.review_status

    approved = ev.review_status == "approved"
    return ReviewCallback(url=conn.callback_url, secret=secret, payload={
        "type": "event.approved" if approved else "event.rejected",
        "submission_id": sub.id,
        "external_id": sub.external_id,
        "submitted_by": sub.submitted_by,
        "event_id": ev.id,
        "event_title": ev.title,
        "start_date": ev.start_date.isoformat(),
        "review_status": ev.review_status,
        "review_note": None if approved else ev.review_note,
        "event_url": event_public_url(ev) if approved else None,
    })


async def send_review_callback(cb: ReviewCallback) -> bool:
    """POST the outcome, signed. Best effort: the review stands whether or not the bot's server
    answers; the bot can always poll GET /api/integrations/v1/submissions/{id}."""
    body = json.dumps(cb.payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    try:
        resp = await post_json_safely(cb.url, body, timeout=_CALLBACK_TIMEOUT, headers={
            "User-Agent": "Turnup-Webhooks/1.0",
            "X-Turnup-Event": cb.payload["type"],
            "X-Turnup-Timestamp": timestamp,
            "X-Turnup-Signature": sign(cb.secret, timestamp, body),
        })
        if resp.status_code >= 300:
            logger.warning("Agent callback to %s answered %s", cb.url, resp.status_code)
            return False
        return True
    except Exception as e:
        logger.warning("Agent callback to %s failed: %s", cb.url, e)
        return False
