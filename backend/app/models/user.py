import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255))  # nullable for OAuth-only users
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(255))

    # Account state
    role: Mapped[str] = mapped_column(String(20), default="attendee", index=True)  # attendee | organizer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 2FA
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stats
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    events_hosted: Mapped[int] = mapped_column(Integer, default=0)
    events_attended: Mapped[int] = mapped_column(Integer, default=0)

    # Preferences
    category_preferences: Mapped[str | None] = mapped_column(Text)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships — core
    events = relationship("Event", back_populates="host", foreign_keys="Event.host_id")
    attendances = relationship("EventAttendee", back_populates="user")
    saves = relationship("EventSave", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    notifications = relationship("Notification", foreign_keys="Notification.user_id", back_populates="user")
    followers = relationship("Follow", foreign_keys="Follow.following_id", back_populates="following")
    following = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    two_factor = relationship("TwoFactor", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # Relationships — organizer
    organizer_profile = relationship("OrganizerProfile", back_populates="user",
                                     uselist=False, cascade="all, delete-orphan")
    event_templates = relationship("EventTemplate", back_populates="organizer", cascade="all, delete-orphan")
    ticket_orders = relationship("TicketOrder", back_populates="user")
    cohost_invites = relationship("EventCoHost", back_populates="user", cascade="all, delete-orphan")
    waitlist_entries = relationship("EventWaitlist", back_populates="user", cascade="all, delete-orphan")
