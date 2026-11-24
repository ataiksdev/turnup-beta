"""What people tell the feed directly: things they've hidden, and searches they want to hear about.

These are kept on their own, apart from any activity logging, so cleaning up old logs never
brings back an event someone said they weren't interested in.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


HIDDEN_KINDS = ("event", "organizer")


class HiddenItem(Base):
    """"Not interested" in an event, or "Hide this organizer". Removed only when the person unhides it."""
    __tablename__ = "hidden_items"
    __table_args__ = (UniqueConstraint("user_id", "kind", "target_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # event | organizer
    # An event id or an organizer's user id. No foreign key: the row stays useful (and harmless)
    # if the event or account is later removed.
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SearchAlert(Base):
    """"Notify me" on a search that found nothing: checked against new events until it expires."""
    __tablename__ = "search_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(50))  # category slug
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # New events are those created after this; moves forward on every check.
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notified_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
