"""Activity tracking and recommendation features (docs/recommendations-spec.md).

- `activity_log`: append-only log of what people do in the app (client events sent to
  POST /api/track, plus server events written where purchases, RSVPs and check-ins happen).
- `user_features` / `event_features`: per-user and per-event numbers computed from it by the
  worker (app/services/rec_features.py) and read by the ranker (app/services/recommender.py).

Plain Postgres tables on purpose: the ingest and lookup functions are small, so Kafka (for the
log) or Redis (for the features) can replace them later without touching the ranker.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# SQLite only auto-increments an INTEGER PRIMARY KEY.
BigId = BigInteger().with_variant(Integer, "sqlite")


class Activity(Base):
    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_activity_name_time", "name", "occurred_at"),
        Index("ix_activity_event_name_time", "event_id", "name", "occurred_at"),
        Index("ix_activity_user_time", "user_id", "occurred_at"),
        Index("ix_activity_anon_time", "anonymous_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    # The app's own id for the event, so a batch re-sent after a dropped connection isn't
    # counted twice. Null for server events.
    client_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(10), default="client")  # client | server
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Who. No foreign keys: inserts stay cheap, and rows are removed explicitly when an
    # account is deleted (services/activity.py forget_user).
    user_id: Mapped[str | None] = mapped_column(String(36))
    anonymous_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(10))       # web | android | ios
    app_version: Mapped[str | None] = mapped_column(String(20))

    # What it was about.
    event_id: Mapped[str | None] = mapped_column(String(36))       # the Turnup event, if any
    surface: Mapped[str | None] = mapped_column(String(30))        # for_you, search, trending...
    position: Mapped[int | None] = mapped_column(Integer)
    rec_request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Where. Coordinates only with location permission AND profiling consent.
    geo_city: Mapped[str | None] = mapped_column(String(100))
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lon: Mapped[float | None] = mapped_column(Float)
    referrer: Mapped[str | None] = mapped_column(String(300))
    utm_campaign: Mapped[str | None] = mapped_column(String(100))

    props: Mapped[dict | None] = mapped_column(JSON)


class UserFeatures(Base):
    __tablename__ = "user_features"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Taste
    category_affinity: Mapped[dict | None] = mapped_column(JSON)   # {category_id: 0..1}
    tag_affinity: Mapped[dict | None] = mapped_column(JSON)        # {tag: 0..1}, top 30
    # Timing
    avg_lead_time_hours: Mapped[float | None] = mapped_column(Float)
    spontaneity_ratio: Mapped[float | None] = mapped_column(Float)  # share decided < 48h before
    weekend_share: Mapped[float | None] = mapped_column(Float)
    # Money
    median_ticket_spend: Mapped[float | None] = mapped_column(Float)
    max_ticket_spend: Mapped[float | None] = mapped_column(Float)
    free_event_share: Mapped[float | None] = mapped_column(Float)
    vip_share: Mapped[float | None] = mapped_column(Float)          # bought above the cheapest tier
    checkout_abandon_rate: Mapped[float | None] = mapped_column(Float)
    # Place (from the events they engage with, not from tracking them)
    home_lat: Mapped[float | None] = mapped_column(Float)
    home_lon: Mapped[float | None] = mapped_column(Float)
    preferred_radius_km: Mapped[float | None] = mapped_column(Float)
    # People
    social_affinity_ids: Mapped[list | None] = mapped_column(JSON)  # followed + repeat organizers
    share_rate: Mapped[float | None] = mapped_column(Float)
    # Lifecycle
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle: Mapped[str | None] = mapped_column(String(20))       # new | active | cooling | dormant
    conversion_propensity: Mapped[float | None] = mapped_column(Float)  # 0..1
    views_30d: Mapped[int] = mapped_column(Integer, default=0)
    saves_30d: Mapped[int] = mapped_column(Integer, default=0)
    orders_total: Mapped[int] = mapped_column(Integer, default=0)

    # Only with users.profiling_consent (null otherwise).
    peak_hours: Mapped[list | None] = mapped_column(JSON)           # top local hours active
    co_attendee_ids: Mapped[list | None] = mapped_column(JSON)      # consenting users they go out with
    tastemaker_score: Mapped[float | None] = mapped_column(Float)
    segments: Mapped[list | None] = mapped_column(JSON)             # audience labels for partners


class EventFeatures(Base):
    __tablename__ = "event_features"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    impressions_7d: Mapped[int] = mapped_column(Integer, default=0)
    clicks_7d: Mapped[int] = mapped_column(Integer, default=0)
    views_7d: Mapped[int] = mapped_column(Integer, default=0)
    saves_7d: Mapped[int] = mapped_column(Integer, default=0)
    orders_7d: Mapped[int] = mapped_column(Integer, default=0)
    ctr_7d: Mapped[float] = mapped_column(Float, default=0.0)           # smoothed
    save_rate_7d: Mapped[float] = mapped_column(Float, default=0.0)     # smoothed, per view
    view_to_order_rate_7d: Mapped[float] = mapped_column(Float, default=0.0)

    velocity_1h: Mapped[int] = mapped_column(Integer, default=0)        # orders + saves + going
    velocity_24h: Mapped[int] = mapped_column(Integer, default=0)
    interest_surge: Mapped[float] = mapped_column(Float, default=0.0)   # last 24h vs daily avg of prior 7d
    sell_through_pct: Mapped[float | None] = mapped_column(Float)
    remaining_tickets: Mapped[int | None] = mapped_column(Integer)      # null = unlimited / no tiers

    organizer_quality: Mapped[float] = mapped_column(Float, default=0.5)        # 0..1
    attendance_reliability: Mapped[float | None] = mapped_column(Float)         # checked in / sold
    demand_score: Mapped[float] = mapped_column(Float, default=0.0)             # 0..1, Wilson-smoothed

