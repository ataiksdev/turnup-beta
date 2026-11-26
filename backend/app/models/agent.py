"""Agent connections: ways events reach Turnup's approval queue from outside the app.

kind "telegram": a Telegram bot Turnup runs itself. People (only allowlisted Telegram users)
DM it a poster, a link or the details; Telegram posts each message to Turnup's webhook, the AI
drafter turns it into a pending event, and the bot replies in the chat, again once reviewed.
kind "api": any outside program (an LLM agent, n8n, a partner's bot) calls
/api/integrations/v1 with an API key, and can get review outcomes at a callback URL.

Nothing they send is published directly: each event waits in the admin approval queue.
Credentials (bot token, webhook and callback secrets) are stored encrypted, with a key derived
from SECRET_KEY (app/services/agent_intake.py). See docs/agent-connections.md.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentConnection(Base):
    __tablename__ = "agent_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="api", server_default="api")  # api | telegram
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # kind "api": only the key's SHA-256 is stored, plus its first characters so admins can
    # tell keys apart.
    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    api_key_prefix: Mapped[str | None] = mapped_column(String(16))
    # kind "api": where review outcomes are POSTed (optional).
    callback_url: Mapped[str | None] = mapped_column(String(500))

    # Encrypted JSON: {"callback_secret"} for api, {"bot_token", "webhook_secret"} for telegram.
    secrets_encrypted: Mapped[str | None] = mapped_column(Text)
    # kind "telegram": the bot's @username, filled in when the webhook is connected.
    telegram_bot_username: Mapped[str | None] = mapped_column(String(64))
    # kind "telegram": Telegram user ids allowed to submit, comma or newline separated. Anyone
    # else is told the bot isn't open yet. Empty: nobody can submit.
    allowed_senders: Mapped[str | None] = mapped_column(Text)

    # Events are hosted by this account. Empty: the scout bot account hosts them, like scouted
    # events (admins can edit those).
    host_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Submissions accepted per rolling 24 hours (a poster or text submission costs an AI call).
    daily_limit: Mapped[int] = mapped_column(Integer, default=50, server_default="50")

    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    host_user = relationship("User", foreign_keys=[host_user_id])
    submissions = relationship("AgentSubmission", back_populates="connection", cascade="all, delete-orphan")


class AgentSubmission(Base):
    """One submission from a connection, and what came of it."""
    __tablename__ = "agent_submissions"
    __table_args__ = (UniqueConstraint("connection_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("agent_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    # created | skipped_duplicate | skipped_no_event | failed | over_limit | sender_not_allowed
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), index=True)
    # Who gave the event: a name or number an API caller reports, or the Telegram sender.
    submitted_by: Mapped[str | None] = mapped_column(String(200))
    # kind "telegram": the chat to reply in, including after review.
    reply_chat_id: Mapped[str | None] = mapped_column(String(40))
    # Idempotency: the caller's id, or the Telegram chat:message id. A repeat isn't redone.
    external_id: Mapped[str | None] = mapped_column(String(200))
    input_text: Mapped[str | None] = mapped_column(Text)  # what was sent, truncated
    error_note: Mapped[str | None] = mapped_column(Text)
    # The review outcome last sent back (approved | rejected), so it's sent once.
    notified_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    connection = relationship("AgentConnection", back_populates="submissions")
    event = relationship("Event")
