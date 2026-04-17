"""
Organizer-specific models:
  OrganizerProfile — extended profile for organizer accounts
  TicketTier       — ticket types/pricing per event
  TicketOrder      — ticket purchases by attendees
  EventTemplate    — reusable event config blobs
  EventCoHost      — co-organizer invitations per event
  EventWaitlist    — waitlist entries when event is at capacity
  EventView        — per-request view tracking for analytics
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizerProfile(Base):
    __tablename__ = "organizer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, unique=True, index=True)
    organization_name: Mapped[str | None] = mapped_column(String(200))
    organizer_bio: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(255))
    is_verified_organizer: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="organizer_profile")


class TicketTier(Base):
    __tablename__ = "ticket_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    quantity: Mapped[int | None] = mapped_column(Integer)          # null = unlimited
    quantity_sold: Mapped[int] = mapped_column(Integer, default=0)
    max_per_order: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sale_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sale_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event = relationship("Event", back_populates="ticket_tiers")
    orders = relationship("TicketOrder", back_populates="tier", cascade="all, delete-orphan")


class TicketOrder(Base):
    __tablename__ = "ticket_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    tier_id: Mapped[str] = mapped_column(ForeignKey("ticket_tiers.id", ondelete="CASCADE"),
                                         nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    # pending | confirmed | cancelled | refunded
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="ticket_orders")
    event = relationship("Event", back_populates="ticket_orders")
    tier = relationship("TicketTier", back_populates="orders")


class EventTemplate(Base):
    __tablename__ = "event_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organizer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                              nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # JSON blob of EventCreate-compatible fields (minus dates/title)
    template_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organizer = relationship("User", back_populates="event_templates")


class EventCoHost(Base):
    __tablename__ = "event_cohosts"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    # invited | accepted | declined
    status: Mapped[str] = mapped_column(String(20), default="invited")
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event = relationship("Event", back_populates="cohosts")
    user = relationship("User", back_populates="cohost_invites")


class EventWaitlist(Base):
    __tablename__ = "event_waitlist"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # waiting | notified | converted | cancelled
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event = relationship("Event", back_populates="waitlist_entries")
    user = relationship("User", back_populates="waitlist_entries")


class EventView(Base):
    __tablename__ = "event_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"),
                                          nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    event = relationship("Event", back_populates="views")
