"""Agent connections: API keys, the Telegram bot's credentials, and turning what arrives (fields
an outside program already extracted, or a poster / link / text for Turnup's AI to read) into
an event waiting for admin approval, then telling the sender how the review went.

Nothing an agent sends is published directly: every event is created as a draft with
review_status "pending", exactly like a scouted or moderator-submitted event, and goes live
only when an admin approves it in the Events queue.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
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


def new_webhook_secret() -> str:
    # Telegram's secret_token allows only A-Z, a-z, 0-9, _ and -: token_urlsafe fits.
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    # Derived from SECRET_KEY: changing SECRET_KEY means re-entering the bot token and
    # rotating callback secrets.
    digest = hashlib.sha256(f"agent-connections:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secrets(values: dict) -> str | None:
    values = {k: v for k, v in values.items() if v}
    return _fernet().encrypt(json.dumps(values).encode()).decode() if values else None


def connection_secrets(conn: AgentConnection) -> dict:
    if not conn.secrets_encrypted:
        return {}
    try:
        return json.loads(_fernet().decrypt(conn.secrets_encrypted.encode()))
    except (InvalidToken, ValueError):
        logger.error("Agent connection %s credentials can't be decrypted (was SECRET_KEY changed?)", conn.id)
        return {}


def set_secrets(conn: AgentConnection, **changes) -> None:
    conn.secrets_encrypted = encrypt_secrets({**connection_secrets(conn), **changes})


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """X-Turnup-Signature: HMAC-SHA256 over "<timestamp>.<raw body>", hex, prefixed "sha256="."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def event_public_url(ev: Event) -> str:
    return f"{settings.frontend_url.rstrip('/')}/events/{ev.slug}"


def telegram_webhook_url(conn: AgentConnection) -> str:
    base = (settings.public_base_url or settings.frontend_url).rstrip("/")
    return f"{base}/api/integrations/telegram/{conn.id}"


def parse_allowed_senders(raw: str | None) -> set[str]:
    return {p.strip().lstrip("@").lower() for p in re.split(r"[,\s]+", raw or "") if p.strip()}


def sender_allowed(conn: AgentConnection, user_id: str | None) -> bool:
    """Telegram: only allowlisted user ids may submit. An empty allowlist lets nobody in."""
    return bool(user_id) and user_id.lower() in parse_allowed_senders(conn.allowed_senders)


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
    reply_chat_id: str | None = None
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
        reply_chat_id=sub.reply_chat_id,
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
        db, draft, host_id=host_id, created_via="telegram" if conn.kind == "telegram" else CREATED_VIA,
        categories_by_name=categories_by_name, ticket_url=sub.ticket_url,
    )
    return await _done(status, event)


def record_refusal(db: AsyncSession, conn: AgentConnection, sub: Submission) -> None:
    """Log a message from a sender who isn't allowed (doesn't count toward the daily limit)."""
    db.add(AgentSubmission(
        connection_id=conn.id, status="sender_not_allowed",
        submitted_by=(sub.submitted_by or None) and sub.submitted_by[:200],
        reply_chat_id=sub.reply_chat_id,
        input_text=(sub.text or ("[image]" if sub.image_bytes else None) or "")[:_MAX_INPUT_CHARS] or None,
    ))


# ── Replies in the chat (Telegram) ───────────────────────────────────────────

def _when(ev: Event) -> str:
    return ev.start_date.strftime("%a %d %b %Y, %H:%M UTC")


def chat_reply(result: SubmitResult) -> str:
    s, ev = result.submission, result.event
    if s.status == "created" and ev:
        return (f"Got it! I drafted \u201c{ev.title}\u201d ({_when(ev)}, {ev.venue_name}). "
                "It's in the approval queue now. I'll message you here once it's reviewed.")
    if s.status == "skipped_duplicate" and ev:
        return f"\u201c{ev.title}\u201d is already on Turnup, so I didn't add it again."
    if s.status == "skipped_no_event":
        return ("I couldn't find an event in that. Send a clear photo of the poster, a link to the "
                "event page, or the name, date, time and venue as text.")
    if s.status == "over_limit":
        return "This bot has reached today's limit of events. Please try again tomorrow."
    return "Something went wrong reading that. Please try again in a little while."


TELEGRAM_HELP = (
    "Send me an event and I'll add it to Turnup's approval queue:\n"
    "\u2022 a photo of the poster or flyer (add any extra details as the caption)\n"
    "\u2022 a link to the event's page\n"
    "\u2022 or the details as text: name, date, time, venue, price\n\n"
    "I'll message you here when it's approved or rejected. /whoami shows your Telegram id."
)
TELEGRAM_NOT_OPEN = "Thanks for your interest! This bot isn't open yet."


# ── Review outcomes back to the sender ───────────────────────────────────────

@dataclass
class ReviewNotice:
    kind: str                    # "api" (POST to callback_url) or "telegram" (chat message)
    payload: dict | None = None  # api
    url: str | None = None
    secret: str | None = None
    bot_token: str | None = None  # telegram
    chat_id: str | None = None
    text: str | None = None


async def review_notice(db: AsyncSession, ev: Event) -> ReviewNotice | None:
    """After an admin approves or rejects an event, what to send to whoever submitted it
    (once per outcome), or None."""
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
    if not conn.is_active or sub.notified_status == ev.review_status:
        return None
    secrets_ = connection_secrets(conn)
    approved = ev.review_status == "approved"

    if conn.kind == "telegram":
        if not sub.reply_chat_id or not secrets_.get("bot_token"):
            return None
        if approved:
            text = f"\U0001F389 Approved: \u201c{ev.title}\u201d is live on Turnup\n{event_public_url(ev)}"
        else:
            text = f"\u201c{ev.title}\u201d wasn't approved."
            if ev.review_note:
                text += f"\nNote: {ev.review_note}"
        notice = ReviewNotice(kind="telegram", bot_token=secrets_["bot_token"], chat_id=sub.reply_chat_id, text=text)
    else:
        if not conn.callback_url or not secrets_.get("callback_secret"):
            return None
        notice = ReviewNotice(kind="api", url=conn.callback_url, secret=secrets_["callback_secret"], payload={
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
    sub.notified_status = ev.review_status
    return notice


async def send_review_notice(notice: ReviewNotice) -> bool:
    """Best effort: the review stands whether or not this gets through. API callers can always
    poll GET /api/integrations/v1/submissions/{id}."""
    if notice.kind == "telegram":
        from app.services import telegram
        try:
            await telegram.send_message(notice.bot_token, notice.chat_id, notice.text)
            return True
        except Exception as e:
            logger.warning("Couldn't send the review outcome over Telegram: %s", e)
            return False

    body = json.dumps(notice.payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    try:
        resp = await post_json_safely(notice.url, body, timeout=_CALLBACK_TIMEOUT, headers={
            "User-Agent": "Turnup-Webhooks/1.0",
            "X-Turnup-Event": notice.payload["type"],
            "X-Turnup-Timestamp": timestamp,
            "X-Turnup-Signature": sign(notice.secret, timestamp, body),
        })
        if resp.status_code >= 300:
            logger.warning("Agent callback to %s answered %s", notice.url, resp.status_code)
            return False
        return True
    except Exception as e:
        logger.warning("Agent callback to %s failed: %s", notice.url, e)
        return False
