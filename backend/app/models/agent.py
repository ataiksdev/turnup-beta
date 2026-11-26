"""Agent connections: outside bots and programs (your own WhatsApp or Telegram bot, an LLM
agent, n8n/Zapier, a partner's system) that submit events to Turnup with an API key.

Nothing they send is published directly: each event waits in the admin approval queue. When
an admin approves or rejects it, Turnup can POST the outcome to the connection's callback URL
so the bot can tell whoever sent it. See docs/agent-connections.md.
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # Only the key's SHA-256 is stored, plus its first characters so admins can tell keys apart.
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    # Where review outcomes are POSTed (optional), and the secret they're signed with
    # (encrypted with a key derived from SECRET_KEY: app/services/agent_intake.py).
    callback_url: Mapped[str | None] = mapped_column(String(500))
    callback_secret_encrypted: Mapped[str | None] = mapped_column(Text)

    # Events are hosted by this account (e.g. a partner organizer's bot posting their own
    # events). Empty: the scout bot account hosts them, like scouted events.
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
    # created | skipped_duplicate | skipped_no_event | failed | over_limit
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), index=True)
    # Whoever gave the bot the event (a phone number, a chat id, a name), as the bot reports it.
    # Echoed back in the review callback so the bot knows whom to tell.
    submitted_by: Mapped[str | None] = mapped_column(String(200))
    # Idempotency: the bot's own id for this submission (e.g. its message id). A repeat isn't redone.
    external_id: Mapped[str | None] = mapped_column(String(200))
    input_text: Mapped[str | None] = mapped_column(Text)  # what was sent, truncated
    error_note: Mapped[str | None] = mapped_column(Text)
    # The review outcome last delivered to the callback (approved | rejected), so it's sent once.
    notified_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    connection = relationship("AgentConnection", back_populates="submissions")
    event = relationship("Event")
