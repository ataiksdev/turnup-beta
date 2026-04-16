from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="🎉")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#FF4500")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    events = relationship("Event", back_populates="category")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gallery: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of URLs

    # Location
    venue_name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="US")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timing
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/New_York")

    # Pricing
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    price_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    ticket_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Capacity & attendance
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attendees_count: Mapped[int] = mapped_column(Integer, default=0)
    interested_count: Mapped[int] = mapped_column(Integer, default=0)
    saves_count: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    status: Mapped[str] = mapped_column(
        Enum("draft", "published", "cancelled", "completed", name="event_status"),
        default="published",
        nullable=False,
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False)

    # Tags (stored as comma-separated string for simplicity)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relations
    host_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    host = relationship("User", back_populates="events", foreign_keys=[host_id])
    category = relationship("Category", back_populates="events")
    attendees = relationship("EventAttendee", back_populates="event", cascade="all, delete-orphan")
    saves = relationship("EventSave", back_populates="event", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="event", cascade="all, delete-orphan")


class EventAttendee(Base):
    __tablename__ = "event_attendees"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum("going", "interested", name="attendance_status"),
        nullable=False,
        default="going",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="attendances")
    event = relationship("Event", back_populates="attendees")


class EventSave(Base):
    __tablename__ = "event_saves"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="saves")
    event = relationship("Event", back_populates="saves")
