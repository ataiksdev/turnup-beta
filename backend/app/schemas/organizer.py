from datetime import datetime
from pydantic import BaseModel, Field


# ── Organizer profile ─────────────────────────────────────────────────────────

class OrganizerBecomeRequest(BaseModel):
    organization_name: str | None = Field(None, max_length=200)
    organizer_bio: str | None = Field(None, max_length=1000)
    website: str | None = Field(None, max_length=255)


class OrganizerProfileOut(BaseModel):
    id: str
    organization_name: str | None
    organizer_bio: str | None
    website: str | None
    is_verified_organizer: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizerProfileUpdate(BaseModel):
    organization_name: str | None = Field(None, max_length=200)
    organizer_bio: str | None = Field(None, max_length=1000)
    website: str | None = Field(None, max_length=255)


# ── Ticket tiers ──────────────────────────────────────────────────────────────

class TicketTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price: float = Field(ge=0)
    currency: str = "NGN"
    quantity: int | None = Field(None, ge=1)
    max_per_order: int = Field(10, ge=1, le=100)
    is_active: bool = True
    sale_start: datetime | None = None
    sale_end: datetime | None = None


class TicketTierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    quantity: int | None = Field(None, ge=1)
    max_per_order: int | None = Field(None, ge=1, le=100)
    is_active: bool | None = None
    sale_start: datetime | None = None
    sale_end: datetime | None = None


class TicketTierOut(BaseModel):
    id: str
    event_id: str
    name: str
    description: str | None
    price: float
    currency: str
    quantity: int | None
    quantity_sold: int
    available: int | None  # computed: quantity - quantity_sold (None if unlimited)
    max_per_order: int
    is_active: bool
    sale_start: datetime | None
    sale_end: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class CheckoutItem(BaseModel):
    tier_id: str
    quantity: int = Field(1, ge=1, le=20)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1)
    idempotency_key: str | None = Field(None, max_length=64)


class CheckoutInitOut(BaseModel):
    order_ids: list[str]
    payment_reference: str
    paystack_public_key: str = ""
    amount_kobo: int = 0
    email: str
    is_free: bool = False


class TicketOrderOut(BaseModel):
    id: str
    event_id: str
    tier_id: str
    tier_name: str
    quantity: int
    unit_price: float
    total_price: float
    status: str
    payment_reference: str | None = None
    ticket_code: str | None = None
    checked_in_at: datetime | None = None
    # enriched fields returned by my-tickets endpoint
    event_title: str | None = None
    event_slug: str | None = None
    event_cover: str | None = None
    event_date: datetime | None = None
    event_city: str | None = None
    event_address: str | None = None
    event_venue: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class VerifyPaymentRequest(BaseModel):
    reference: str


# ── Event templates ───────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    template_data: dict  # EventCreate-compatible fields (no title/dates)


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    template_data: dict | None = None


class TemplateOut(BaseModel):
    id: str
    organizer_id: str
    name: str
    description: str | None
    template_data: dict
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Co-hosts ──────────────────────────────────────────────────────────────────

class CoHostInviteRequest(BaseModel):
    username: str  # invite by username


class CoHostRespondRequest(BaseModel):
    event_id: str
    accept: bool


class CoHostOut(BaseModel):
    id: str
    user_id: str
    username: str
    full_name: str
    avatar_url: str | None
    status: str
    invited_at: datetime
    responded_at: datetime | None
    model_config = {"from_attributes": True}


# ── Waitlist ──────────────────────────────────────────────────────────────────

class WaitlistEntryOut(BaseModel):
    id: str
    user_id: str
    username: str
    full_name: str
    avatar_url: str | None
    position: int
    status: str
    created_at: datetime
    notified_at: datetime | None
    model_config = {"from_attributes": True}


class WaitlistNotifyRequest(BaseModel):
    count: int = Field(1, ge=1, le=50)


class WaitlistStatusOut(BaseModel):
    position: int
    status: str
    total_ahead: int


# ── Analytics ─────────────────────────────────────────────────────────────────

class DailyViewOut(BaseModel):
    date: str
    views: int


class AnalyticsOut(BaseModel):
    event_id: str
    total_views: int
    unique_views: int
    rsvp_going: int
    rsvp_interested: int
    saves_count: int
    waitlist_count: int
    ticket_orders_count: int
    estimated_revenue: float
    daily_views: list[DailyViewOut]


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardOut(BaseModel):
    total_events: int
    published_events: int
    draft_events: int
    total_attendees: int
    total_revenue: float
    pending_cohost_invites: int


# ── Reviews ───────────────────────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    ticket_code: str


class CheckInResult(BaseModel):
    order_id: str
    ticket_code: str
    attendee_name: str
    tier_name: str
    quantity: int
    checked_in_at: datetime


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(None, max_length=2000)


class ReviewOut(BaseModel):
    id: str
    event_id: str
    user_id: str
    username: str
    full_name: str
    avatar_url: str | None
    rating: int
    body: str | None
    created_at: datetime
    model_config = {"from_attributes": True}
