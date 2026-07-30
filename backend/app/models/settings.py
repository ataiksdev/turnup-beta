"""
Platform-wide, admin-adjustable settings that need to change at runtime without a
redeploy. Deliberately a tiny singleton table rather than an env var -- env vars
require a restart to take effect and aren't editable from the admin UI.
"""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


PLATFORM_SETTINGS_ID = "default"


class PlatformSettings(Base):
    """Singleton row (id is always PLATFORM_SETTINGS_ID) holding platform-wide config."""
    __tablename__ = "platform_settings"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: PLATFORM_SETTINGS_ID)
    # Percentage of each confirmed paid ticket order retained as Turnup's fee (0-100).
    # Deducted from what the organizer receives -- buyers are never charged extra for it.
    ticket_fee_percent: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
