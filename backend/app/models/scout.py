import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScoutSource(Base):
    """A public page the daily scout agent polls for candidate events — an RSS/Atom feed if the
    site has one, otherwise a regular events/news listing page (see scout_agent._fetch_candidate_links,
    which tries a feed parse first and falls back to scraping <a href> links off the page)."""
    __tablename__ = "scout_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items = relationship("ScoutedItem", back_populates="source", cascade="all, delete-orphan")


class ScoutedItem(Base):
    """Audit trail + dedup guard: one row per feed entry URL the agent has looked at."""
    __tablename__ = "scouted_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("scout_sources.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # created | skipped_duplicate | skipped_no_event | failed
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    error_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source = relationship("ScoutSource", back_populates="items")
    event = relationship("Event")
