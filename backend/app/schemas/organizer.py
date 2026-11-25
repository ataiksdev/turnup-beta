from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.schemas.types import WebUrl


# ── Organizer profile ─────────────────────────────────────────────────────────

class OrganizerBecomeRequest(BaseModel):
    organization_name: str | None = Field(None, max_length=200)
    organizer_bio: str | None = Field(None, max_length=1000)
    website: WebUrl | None = Field(None, max_length=255)


class OrganizerProfileOut(BaseModel):
    id: str
    organization_name: str | None
    organizer_bio: str | None
    website: str | None
    is_verified_organizer: bool
    verification_status: str
    verification_note: str | None = None
    verification_requested_at: datetime | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizerProfileUpdate(BaseModel):
    organization_name: str | None = Field(None, max_length=200)
    organizer_bio: str | None = Field(None, max_length=1000)
    website: WebUrl | None = Field(None, max_length=255)


class VerificationRequest(BaseModel):
    note: str | None = Field(None, max_length=1000)


# ── Ticket tiers ──────────────────────────────────────────────────────────────

class TicketTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price: float = Field(ge=0)
    # Turnup takes payments in naira only (Paystack, amounts in kobo), so every price is
    # stored as NGN whatever a client sends (old builds and AI drafts sent "USD").
    currency: str = "NGN"

    @field_validator("currency", mode="before")
    @classmethod
    def _naira_only(cls, v: object) -> str:
        return "NGN"

    quantity: int | None = Field(None, ge=1)
    max_per_order: int = Field(10, ge=1, le=100)
    is_active: bool = True
    sale_start: datetime | None = None
    sale_end: datetime | None = None
    # Turnup+ (docs/venues-spec.md 4.8): members-only tier (guest list), or a members' presale
    members_only: bool = False
    plus_presale_ends_at: datetime | None = None
    presale_then: str = Field("open", pattern=r"^(open|close)$")


class TicketTierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    quantity: int | None = Field(None, ge=1)
    max_per_order: int | None = Field(None, ge=1, le=100)
    is_active: bool | None = None
    sale_start: datetime | None = None
    sale_end: datetime | None = None
    members_only: bool | None = None
    plus_presale_ends_at: datetime | None = None
    presale_then: str | None = Field(None, pattern=r"^(open|close)$")


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
    members_only: bool = False
    plus_presale_ends_at: datetime | None = None
    presale_then: str = "open"
    model_config = {"from_attributes": True}


class CheckoutItem(BaseModel):
    tier_id: str
    quantity: int = Field(1, ge=1, le=20)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1)
    idempotency_key: str | None = Field(None, max_length=64)
    promo_code: str | None = Field(None, max_length=40)
    # question_id -> answer (text, a list for multi-choice, a bool for a checkbox)
    answers: dict[str, str | bool | list[str] | None] | None = None


class PromoCheckRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    items: list[CheckoutItem] = Field(min_length=1)


class PromoCheckOut(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    subtotal: float
    discount: float
    total: float


_CODE_PATTERN = r"^[A-Za-z0-9_-]{3,40}$"


class PromoCodeCreate(BaseModel):
    code: str = Field(pattern=_CODE_PATTERN)
    discount_type: str = Field("percent", pattern=r"^(percent|amount)$")
    discount_value: float = Field(gt=0)
    max_uses: int | None = Field(None, ge=1)
    tier_ids: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True

    @field_validator("discount_value")
    @classmethod
    def _sane(cls, v: float, info) -> float:
        if info.data.get("discount_type", "percent") == "percent" and v > 100:
            raise ValueError("A percentage discount can't be more than 100")
        return v


class PromoCodeUpdate(BaseModel):
    max_uses: int | None = Field(None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class PromoCodeOut(BaseModel):
    id: str
    code: str
    discount_type: str
    discount_value: float
    max_uses: int | None
    times_used: int
    tier_ids: list[str] | None
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    discount_given: float = 0.0   # naira off across paid, unrefunded orders
    created_at: datetime


_KIND_PATTERN = r"^(text|long_text|single_choice|multi_choice|checkbox)$"


class QuestionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    help_text: str | None = Field(None, max_length=300)
    kind: str = Field("text", pattern=_KIND_PATTERN)
    options: list[str] | None = None
    required: bool = False
    position: int | None = None

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out = []
        for o in v:
            o = o.strip()[:100]
            if o and o not in out:
                out.append(o)
        return out[:30]


class QuestionUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=200)
    help_text: str | None = Field(None, max_length=300)
    options: list[str] | None = None
    required: bool | None = None
    position: int | None = None

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v: list[str] | None) -> list[str] | None:
        return QuestionCreate._clean_options(v)


class QuestionOut(BaseModel):
    id: str
    label: str
    help_text: str | None
    kind: str
    options: list[str] | None
    required: bool
    position: int
    model_config = {"from_attributes": True}


class RegistrationRow(BaseModel):
    user_id: str
    name: str
    username: str | None
    email: str | None
    status: str                    # "ticket" or "going"
    answers: dict[str, str]        # question_id -> answer as text
    answered_at: datetime | None


class RegistrationsOut(BaseModel):
    questions: list[QuestionOut]
    rows: list[RegistrationRow]


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
    admitted_count: int = 0
    discount_amount: float | None = None
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
    total_revenue: float  # gross ticket sales, before the platform fee
    platform_fee_total: float
    net_revenue: float  # total_revenue - platform_fee_total -- what you actually get paid
    pending_cohost_invites: int


# ── Reviews ───────────────────────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    ticket_code: str
    # How many people to admit now. Omitted: admit the only person left, or (for a ticket with
    # several people still to come in) return needs_choice so staff pick how many are here.
    admit: int | None = Field(None, ge=1, le=100)


class CheckInResult(BaseModel):
    order_id: str
    ticket_code: str
    attendee_name: str
    tier_name: str
    quantity: int
    checked_in_at: datetime
    fast_lane: bool = False  # Turnup+ member at an event with a fast lane
    admitted_count: int = 0      # people in so far on this ticket
    admitted_now: int = 0        # people admitted by this request
    remaining: int = 0           # still to come in
    needs_choice: bool = False   # nothing admitted yet: ask how many are at the door


class CheckInStats(BaseModel):
    people_in: int
    people_expected: int
    tickets_in: int
    tickets_total: int
    recent: list[dict]


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
