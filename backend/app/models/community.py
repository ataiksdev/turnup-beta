import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    icon: Mapped[str | None] = mapped_column(String(10))          # emoji
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_token: Mapped[str | None] = mapped_column(String(36), unique=True)  # for private communities
    social_links: Mapped[str | None] = mapped_column(Text)         # JSON object
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    creator = relationship("User", foreign_keys=[creator_id], back_populates="communities_created")
    category = relationship("Category")
    members = relationship("CommunityMember", back_populates="community", cascade="all, delete-orphan")
    community_events = relationship("CommunityEvent", back_populates="community", cascade="all, delete-orphan")

    @property
    def social_links_dict(self) -> dict:
        if not self.social_links:
            return {}
        try:
            return json.loads(self.social_links)
        except Exception:
            return {}


class CommunityMember(Base):
    __tablename__ = "community_members"
    __table_args__ = (UniqueConstraint("community_id", "user_id"),)

    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # "member" | "moderator" | "admin"
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    community = relationship("Community", back_populates="members")
    user = relationship("User", back_populates="community_memberships")


class CommunityEvent(Base):
    __tablename__ = "community_events"
    __table_args__ = (UniqueConstraint("community_id", "event_id"),)

    community_id: Mapped[str] = mapped_column(ForeignKey("communities.id", ondelete="CASCADE"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    shared_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    community = relationship("Community", back_populates="community_events")
    event = relationship("Event")
    sharer = relationship("User", foreign_keys=[shared_by])
