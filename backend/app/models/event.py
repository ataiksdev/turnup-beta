import uuid
from datetime import datetime, timezone
from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventSeries(Base):
    __tablename__ = "event_series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    recurrence_rule: Mapped[str] = mapped_column(String(20), nullable=False)
    # "weekly" | "bi-weekly" | "monthly" | "bi-monthly"
    organizer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    total_occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_occurrence_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events = relationship("Event", back_populates="series", order_by="Event.start_date")
    organizer = relationship("User")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(50), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    icon: Mapped[str] = mapped_column(String(50), default="🎉")
    color: Mapped[str] = mapped_column(String(20), default="#F97316")
    description: Mapped[str | None] = mapped_column(Text)

    events = relationship("Event", back_populates="category")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(230), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    gallery: Mapped[str | None] = mapped_column(Text)  # JSON array

    venue_name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), default="US")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Africa/Lagos")

    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    price_min: Mapped[float | None] = mapped_column(Float)
    price_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    ticket_url: Mapped[str | None] = mapped_column(String(500))

    capacity: Mapped[int | None] = mapped_column(Integer)
    attendees_count: Mapped[int] = mapped_column(Integer, default=0)
    interested_count: Mapped[int] = mapped_column(Integer, default=0)
    saves_count: Mapped[int] = mapped_column(Integer, default=0)
    waitlist_count: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)

    # Event format
    event_type: Mapped[str] = mapped_column(
        Enum("physical", "virtual", "hybrid", name="event_type_enum"),
        default="physical",
        server_default="physical",
    )
    meeting_url: Mapped[str | None] = mapped_column(String(500))

    # Waitlist
    waitlist_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Template reference (no FK, just a reference ID for UI)
    template_id: Mapped[str | None] = mapped_column(String(36))

    # Recurring series reference
    series_id: Mapped[str | None] = mapped_column(ForeignKey("event_series.id"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        Enum("draft", "published", "cancelled", "completed", name="event_status"),
        default="published",
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    tags: Mapped[str | None] = mapped_column(Text)  # comma-separated

    host_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Core relationships
    host = relationship("User", back_populates="events", foreign_keys=[host_id])
    category = relationship("Category", back_populates="events")
    series = relationship("EventSeries", back_populates="events", foreign_keys=[series_id])
    attendees = relationship("EventAttendee", back_populates="event", cascade="all, delete-orphan")
    saves = relationship("EventSave", back_populates="event", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="event", cascade="all, delete-orphan")

    # Organizer relationships
    ticket_tiers = relationship("TicketTier", back_populates="event", cascade="all, delete-orphan")
    ticket_orders = relationship("TicketOrder", back_populates="event", cascade="all, delete-orphan")
    cohosts = relationship("EventCoHost", back_populates="event", cascade="all, delete-orphan")
    waitlist_entries = relationship("EventWaitlist", back_populates="event", cascade="all, delete-orphan")
    views = relationship("EventView", back_populates="event", cascade="all, delete-orphan")
    reviews = relationship("EventReview", back_populates="event", cascade="all, delete-orphan")


class EventAttendee(Base):
    __tablename__ = "event_attendees"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum("going", "interested", name="attendance_status"), default="going"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="attendances")
    event = relationship("Event", back_populates="attendees")


class EventSave(Base):
    __tablename__ = "event_saves"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="saves")
    event = relationship("Event", back_populates="saves")
