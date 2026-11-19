"""
Platform-wide, admin-adjustable settings that need to change at runtime without a
redeploy. Deliberately a tiny singleton table rather than an env var -- env vars
require a restart to take effect and aren't editable from the admin UI.
"""
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
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

    # Venue marketplace (docs/venues-spec.md section 7). server_default so existing rows
    # pick up the starting values when the columns are added.
    venue_commission_percent: Mapped[float] = mapped_column(Float, default=8.0, server_default="8")
    featured_state_week_kobo: Mapped[int] = mapped_column(BigInteger, default=5_000_000, server_default="5000000")
    featured_area_week_kobo: Mapped[int] = mapped_column(BigInteger, default=1_500_000, server_default="1500000")
    featured_max_per_state: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    featured_max_per_area: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    max_recovery_percent: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    refund_funding_hours: Mapped[int] = mapped_column(Integer, default=72, server_default="72")
    refund_suspend_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    refund_referral_days: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    venue_debt_pause_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    strike_suspend_count: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    dispute_window_hours: Mapped[int] = mapped_column(Integer, default=48, server_default="48")
    free_photo_limit: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    pro_photo_limit: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    free_video_limit: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    pro_video_limit: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    free_team_seats: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    pro_team_seats: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    plus_early_alert_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    subscription_grace_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # JSON: {"flexible": [[full_days, half_days]...]} -- see services/venue_policy.py
    refund_presets: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
