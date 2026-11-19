"""Venue marketplace (docs/venues-spec.md).

Money is stored in kobo (integers) throughout, unlike the older ticket tables.
Status-like columns are plain strings (validated in schemas/services), not database enums,
so adding a state never needs an enum migration.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


def _pk():
    return mapped_column(String(36), primary_key=True, default=_id)


def _created():
    return mapped_column(DateTime(timezone=True), default=utcnow)


# ── Places ──────────────────────────────────────────────────────────────────────

class Area(Base):
    """A city or district inside a state (FCT counts as a state here). Admin-managed."""
    __tablename__ = "areas"
    __table_args__ = (UniqueConstraint("state", "slug"),)

    id: Mapped[str] = _pk()
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(90), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="district")  # city | district
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


# ── Venues ──────────────────────────────────────────────────────────────────────

class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[str] = _pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # hall | lounge | hotel_studio | outdoor
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    area_id: Mapped[str | None] = mapped_column(ForeignKey("areas.id"), index=True)
    area_other: Mapped[str | None] = mapped_column(String(80))  # typed when the area isn't listed
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    amenities: Mapped[str | None] = mapped_column(Text)  # JSON list of strings
    rules: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(30))     # revealed only after booking
    email: Mapped[str | None] = mapped_column(String(255))    # revealed only after booking

    price_display: Mapped[str] = mapped_column(String(20), default="from")  # from | range | on_request
    refund_preset: Mapped[str] = mapped_column(String(20), default="moderate")  # flexible | moderate | strict
    deposit_type: Mapped[str] = mapped_column(String(10), default="percent")  # percent | fixed
    deposit_value: Mapped[int] = mapped_column(BigInteger, default=30)  # percent, or kobo when fixed
    balance_due_days: Mapped[int] = mapped_column(Integer, default=7)

    # draft | in_review | live | paused | suspended | closed
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    pause_reason: Mapped[str | None] = mapped_column(String(40))  # unpaid_refund | debt | admin
    # none | documents_submitted | documents_approved | visit_passed | rejected
    verification_status: Mapped[str] = mapped_column(String(30), default="none")
    verification_note: Mapped[str | None] = mapped_column(Text)
    deposits_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Legal identity as verified (disclosed only in a claim pack, spec 4.12)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    cac_number: Mapped[str | None] = mapped_column(String(40))
    registered_address: Mapped[str | None] = mapped_column(String(300))

    paystack_subaccount_code: Mapped[str | None] = mapped_column(String(60))
    bank_code: Mapped[str | None] = mapped_column(String(20))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account_last4: Mapped[str | None] = mapped_column(String(4))
    bank_account_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_hash: Mapped[str | None] = mapped_column(String(64))
    bank_name_match: Mapped[bool | None] = mapped_column(Boolean)

    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_organizers: Mapped[float | None] = mapped_column(Float)
    reviews_organizers_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_guests: Mapped[float | None] = mapped_column(Float)
    reviews_guests_count: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    went_live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VenueSpace(Base):
    __tablename__ = "venue_spaces"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    capacity_seated: Mapped[int | None] = mapped_column(Integer)
    capacity_standing: Mapped[int | None] = mapped_column(Integer)
    setting: Mapped[str] = mapped_column(String(10), default="indoor")  # indoor | outdoor | both
    price_from_kobo: Mapped[int | None] = mapped_column(BigInteger)
    price_to_kobo: Mapped[int | None] = mapped_column(BigInteger)
    price_unit: Mapped[str] = mapped_column(String(10), default="per_day")  # per_day | per_hour | per_event
    min_hours: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class VenueMedia(Base):
    __tablename__ = "venue_media"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # photo | video
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    poster_url: Mapped[str | None] = mapped_column(String(500))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class VenueMember(Base):
    __tablename__ = "venue_members"
    __table_args__ = (UniqueConstraint("venue_id", "user_id"),)

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # owner | manager | viewer
    invited_by_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()


class VenueInvite(Base):
    __tablename__ = "venue_invites"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class VenueBlock(Base):
    """A manual calendar block. space_id NULL blocks the whole venue."""
    __tablename__ = "venue_blocks"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = _created()


# ── Verification ────────────────────────────────────────────────────────────────

class VenueDocument(Base):
    __tablename__ = "venue_documents"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # cac | owner_id | site_photo | site_video | other
    storage_key: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    reviewed_by_id: Mapped[str | None] = mapped_column(String(36))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class KycAccessLog(Base):
    __tablename__ = "kyc_access_log"

    id: Mapped[str] = _pk()
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    venue_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # view | download | disclose
    ip: Mapped[str | None] = mapped_column(String(45))
    at: Mapped[datetime] = _created()


class Agent(Base):
    __tablename__ = "agents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    states: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of state names
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = _created()


class AgentVisit(Base):
    __tablename__ = "agent_visits"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # assigned | scheduled | passed | failed | cancelled
    status: Mapped[str] = mapped_column(String(15), default="assigned", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkin_latitude: Mapped[float | None] = mapped_column(Float)
    checkin_longitude: Mapped[float | None] = mapped_column(Float)
    distance_from_venue_m: Mapped[int | None] = mapped_column(Integer)
    distance_note: Mapped[str | None] = mapped_column(Text)
    checklist: Mapped[str | None] = mapped_column(Text)  # JSON {item: bool}
    notes: Mapped[str | None] = mapped_column(Text)
    photo_keys: Mapped[str | None] = mapped_column(Text)  # JSON list of private-store keys
    assigned_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


# ── Enquiries and bookings ──────────────────────────────────────────────────────

class VenueEnquiry(Base):
    __tablename__ = "venue_enquiries"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="SET NULL"))
    organizer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(80))
    budget_kobo: Mapped[int | None] = mapped_column(BigInteger)
    # open | quoted | booked | declined | expired | closed
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    organizer_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class EnquiryMessage(Base):
    __tablename__ = "enquiry_messages"

    id: Mapped[str] = _pk()
    enquiry_id: Mapped[str] = mapped_column(ForeignKey("venue_enquiries.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[str | None] = mapped_column(String(36))
    sender_side: Mapped[str] = mapped_column(String(10), nullable=False)  # organizer | venue | system
    body: Mapped[str] = mapped_column(Text, nullable=False)
    quote_id: Mapped[str | None] = mapped_column(String(36))
    flagged_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class VenueQuote(Base):
    __tablename__ = "venue_quotes"

    id: Mapped[str] = _pk()
    enquiry_id: Mapped[str] = mapped_column(ForeignKey("venue_enquiries.id", ondelete="CASCADE"), nullable=False, index=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("venue_spaces.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deposit_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_due_days: Mapped[int] = mapped_column(Integer, nullable=False)
    refund_preset: Mapped[str] = mapped_column(String(20), nullable=False)
    inclusions: Mapped[str | None] = mapped_column(Text)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # sent | accepted | superseded | declined | expired
    status: Mapped[str] = mapped_column(String(12), default="sent")
    created_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = _created()


class VenueBooking(Base):
    __tablename__ = "venue_bookings"
    __table_args__ = (Index("ix_venue_bookings_space_time", "space_id", "starts_at", "ends_at"),)

    id: Mapped[str] = _pk()
    quote_id: Mapped[str] = mapped_column(ForeignKey("venue_quotes.id"), nullable=False, unique=True)
    enquiry_id: Mapped[str] = mapped_column(ForeignKey("venue_enquiries.id"), nullable=False, index=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), nullable=False, index=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("venue_spaces.id"), nullable=False)
    organizer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deposit_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    commission_percent: Mapped[float] = mapped_column(Float, nullable=False)
    commission_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_preset: Mapped[str] = mapped_column(String(20), nullable=False)
    # pending_payment | confirmed | fully_paid | cancelled_by_organizer | cancelled_by_venue |
    # cancelled_unpaid_balance | expired | completed | disputed
    status: Mapped[str] = mapped_column(String(30), default="pending_payment", index=True)
    refunded_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[str | None] = mapped_column(String(40))  # e.g. "7,3,1"
    created_at: Mapped[datetime] = _created()


class VenuePayment(Base):
    """Every payment linked to a venue: booking deposit/balance parts, refund funding from the
    venue, debt payments, featured placement. Reference prefixes route the Paystack webhook."""
    __tablename__ = "venue_payments"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), nullable=False, index=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("venue_bookings.id"), index=True)
    refund_request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    payer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # deposit | balance | refund_funding | debt_payment | featured
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commission_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    recovery_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    venue_share_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    reference: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    # pending | success | failed | expired
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    channel: Mapped[str | None] = mapped_column(String(30))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class RefundRequest(Base):
    __tablename__ = "refund_requests"

    id: Mapped[str] = _pk()
    booking_id: Mapped[str] = mapped_column(ForeignKey("venue_bookings.id"), nullable=False, index=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id"), nullable=False, index=True)
    organizer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    dispute_id: Mapped[str | None] = mapped_column(String(36))
    # organizer_cancelled | venue_cancelled | dispute | unpaid_balance
    reason: Mapped[str] = mapped_column(String(25), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funded_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # awaiting_venue | funded | refunded | overdue | suspended | referred | settled_directly
    status: Mapped[str] = mapped_column(String(20), default="awaiting_venue", index=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_by_organizer: Mapped[bool] = mapped_column(Boolean, default=False)
    settled_by_venue: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class RefundPayout(Base):
    """A Paystack refund sent to the organizer against one of their booking payments."""
    __tablename__ = "refund_payouts"

    id: Mapped[str] = _pk()
    refund_request_id: Mapped[str] = mapped_column(ForeignKey("refund_requests.id"), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("venue_payments.id"), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="sent")  # sent | failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class VenueStrike(Base):
    __tablename__ = "venue_strikes"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(40), nullable=False)  # venue_cancelled | off_platform | unpaid_refund | admin
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()


class VenueLedgerEntry(Base):
    """The venue balance. Positive amounts = the venue owes Turnup (or an organizer, for
    refund_owed); negative = paid back."""
    __tablename__ = "venue_ledger"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    # commission_owed | refund_owed | chargeback | recovered | paid_directly | adjustment
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(36))
    refund_request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()


class VenueDispute(Base):
    __tablename__ = "venue_disputes"

    id: Mapped[str] = _pk()
    booking_id: Mapped[str] = mapped_column(ForeignKey("venue_bookings.id"), nullable=False, index=True)
    opened_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # organizer | venue
    # not_as_listed | venue_no_show | organizer_no_show | damage | other
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)  # JSON list of image URLs
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open | resolved
    resolution: Mapped[str | None] = mapped_column(String(10))  # no_refund | partial | full
    refund_kobo: Mapped[int | None] = mapped_column(BigInteger)
    decided_by_id: Mapped[str | None] = mapped_column(String(36))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OffPlatformReport(Base):
    __tablename__ = "off_platform_reports"

    id: Mapped[str] = _pk()
    enquiry_id: Mapped[str] = mapped_column(ForeignKey("venue_enquiries.id", ondelete="CASCADE"), nullable=False, index=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    reporter_id: Mapped[str] = mapped_column(String(36), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | upheld | dismissed
    decided_by_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()


class BlockedIdentity(Base):
    __tablename__ = "blocked_identities"

    id: Mapped[str] = _pk()
    kind: Mapped[str] = mapped_column(String(15), nullable=False)  # cac | bank_account | user
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    refund_request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created()
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chargeback(Base):
    __tablename__ = "chargebacks"

    id: Mapped[str] = _pk()
    payment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    venue_id: Mapped[str | None] = mapped_column(String(36), index=True)
    paystack_dispute_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(60))
    amount_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | won | lost
    ledger_entry_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ── Social ──────────────────────────────────────────────────────────────────────

class VenueFollow(Base):
    __tablename__ = "venue_follows"
    __table_args__ = (UniqueConstraint("user_id", "venue_id"),)

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = _created()


class VenueReview(Base):
    __tablename__ = "venue_reviews"
    __table_args__ = (
        UniqueConstraint("author_id", "booking_id"),
        UniqueConstraint("author_id", "event_id"),
    )

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # organizer | guest
    booking_id: Mapped[str | None] = mapped_column(String(36))
    event_id: Mapped[str | None] = mapped_column(String(36))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    venue_reply: Mapped[str | None] = mapped_column(Text)
    venue_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


# ── Turnup+ deals, subscriptions, featured placement ────────────────────────────

class Deal(Base):
    """A Turnup+ member deal, owned by a venue or by an event."""
    __tablename__ = "deals"

    id: Mapped[str] = _pk()
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # free_entry | discount | free_item | reserved | other
    kind: Mapped[str] = mapped_column(String(15), default="other")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_per_member: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = _created()


class DealRedemption(Base):
    __tablename__ = "deal_redemptions"

    id: Mapped[str] = _pk()
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    claimed_at: Mapped[datetime] = _created()
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_by_id: Mapped[str | None] = mapped_column(String(36))


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)  # e.g. turnup_plus_monthly
    product: Mapped[str] = mapped_column(String(20), nullable=False)  # turnup_plus | venue_pro
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)  # monthly | annually
    paystack_plan_code: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = _pk()
    plan_code: Mapped[str] = mapped_column(ForeignKey("subscription_plans.code"), nullable=False)
    product: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    # pending | active | non_renewing | past_due | cancelled
    status: Mapped[str] = mapped_column(String(15), default="pending", index=True)
    reference: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    paystack_subscription_code: Mapped[str | None] = mapped_column(String(60), index=True)
    paystack_email_token: Mapped[str | None] = mapped_column(String(60))
    paystack_customer_code: Mapped[str | None] = mapped_column(String(60))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class FeaturedSlot(Base):
    __tablename__ = "featured_slots"
    __table_args__ = (Index("ix_featured_slots_place_week", "scope", "state", "area_id", "week_start"),)

    id: Mapped[str] = _pk()
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # state | area
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    area_id: Mapped[str | None] = mapped_column(String(36))
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # pending | active | ended | refunded | expired
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    created_at: Mapped[datetime] = _created()


class TicketTransfer(Base):
    __tablename__ = "ticket_transfers"

    id: Mapped[str] = _pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("ticket_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    old_ticket_code: Mapped[str | None] = mapped_column(String(36))
    new_ticket_code: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = _created()


class WrappedReport(Base):
    __tablename__ = "wrapped_reports"
    __table_args__ = (UniqueConstraint("user_id", "year"),)

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    image_url: Mapped[str | None] = mapped_column(String(500))
    generated_at: Mapped[datetime] = _created()


class ScheduledAlert(Base):
    """A follower alert held back for non-members (Turnup+ early alerts)."""
    __tablename__ = "scheduled_alerts"

    id: Mapped[str] = _pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(String(36))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
