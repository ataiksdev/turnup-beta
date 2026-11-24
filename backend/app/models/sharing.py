"""Share links with a ref code, and the people they brought in (app/services/sharing.py)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShareLink(Base):
    """One per sharer, event and channel: /events/<slug>?ref=<code>."""
    __tablename__ = "share_links"
    __table_args__ = (UniqueConstraint("user_id", "event_id", "channel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp | native | copy_link
    opens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # distinct people/devices
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShareConversion(Base):
    """Someone who opened a share link and then saved, RSVP'd "going" or bought within
    ATTRIBUTION_DAYS. Credit goes to the sharer."""
    __tablename__ = "share_conversions"
    __table_args__ = (UniqueConstraint("share_link_id", "user_id", "kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    share_link_id: Mapped[str] = mapped_column(ForeignKey("share_links.id", ondelete="CASCADE"), nullable=False, index=True)
    sharer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # save | going | order
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
