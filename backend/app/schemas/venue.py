from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.types import WebUrl

VenueType = Literal["hall", "lounge", "hotel_studio", "outdoor"]
Preset = Literal["flexible", "moderate", "strict"]
Role = Literal["owner", "manager", "viewer"]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AreaOut(_Out):
    id: str
    state: str
    name: str
    slug: str
    kind: str
    latitude: float | None = None
    longitude: float | None = None


class AreaIn(BaseModel):
    state: str
    name: str = Field(min_length=2, max_length=80)
    kind: Literal["city", "district"] = "district"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    is_active: bool | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


# ── Venue ───────────────────────────────────────────────────────────────────────

class VenueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    type: VenueType
    description: str | None = Field(default=None, max_length=5000)
    state: str
    area_id: str | None = None
    area_other: str | None = Field(default=None, max_length=80)
    address: str = Field(min_length=5, max_length=300)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _area(self):
        if not self.area_id and not (self.area_other or "").strip():
            raise ValueError("Pick an area, or choose Other and type it.")
        return self


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    type: VenueType | None = None
    description: str | None = Field(default=None, max_length=5000)
    state: str | None = None
    area_id: str | None = None
    area_other: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, min_length=5, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    cover_image: WebUrl | None = None
    amenities: list[str] | None = Field(default=None, max_length=40)
    rules: str | None = Field(default=None, max_length=5000)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    price_display: Literal["from", "range", "on_request"] | None = None
    refund_preset: Preset | None = None
    deposit_type: Literal["percent", "fixed"] | None = None
    deposit_value: int | None = Field(default=None, ge=0)
    balance_due_days: int | None = Field(default=None, ge=0, le=90)
    legal_name: str | None = Field(default=None, max_length=200)
    cac_number: str | None = Field(default=None, max_length=40)
    registered_address: str | None = Field(default=None, max_length=300)

    @field_validator("amenities")
    @classmethod
    def _amenities(cls, v):
        if v is None:
            return v
        return [a.strip()[:40] for a in v if a and a.strip()]

    @model_validator(mode="after")
    def _deposit(self):
        if self.deposit_type == "percent" and self.deposit_value is not None and not 1 <= self.deposit_value <= 100:
            raise ValueError("A percentage deposit must be between 1 and 100.")
        return self


class SpaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=3000)
    capacity_seated: int | None = Field(default=None, ge=0, le=100_000)
    capacity_standing: int | None = Field(default=None, ge=0, le=100_000)
    setting: Literal["indoor", "outdoor", "both"] = "indoor"
    price_from_kobo: int | None = Field(default=None, ge=0)
    price_to_kobo: int | None = Field(default=None, ge=0)
    price_unit: Literal["per_day", "per_hour", "per_event"] = "per_day"
    min_hours: int | None = Field(default=None, ge=0, le=72)
    is_active: bool = True
    sort_order: int = 0


class SpaceOut(_Out):
    id: str
    name: str
    description: str | None
    capacity_seated: int | None
    capacity_standing: int | None
    setting: str
    price_from_kobo: int | None
    price_to_kobo: int | None
    price_unit: str
    min_hours: int | None
    is_active: bool
    sort_order: int


class MediaOut(_Out):
    id: str
    kind: str
    url: str
    poster_url: str | None
    duration_s: int | None
    caption: str | None
    space_id: str | None
    sort_order: int
    hidden: bool = False


class MediaAdd(BaseModel):
    kind: Literal["photo", "video"]
    url: WebUrl
    poster_url: WebUrl | None = None
    duration_s: int | None = None
    caption: str | None = Field(default=None, max_length=200)
    space_id: str | None = None


class MediaOrder(BaseModel):
    ids: list[str]


class BankIn(BaseModel):
    bank_code: str = Field(min_length=2, max_length=20)
    account_number: str = Field(pattern=r"^\d{10}$")


class InviteIn(BaseModel):
    email: str = Field(max_length=255)
    role: Literal["manager", "viewer"]


class MemberRoleIn(BaseModel):
    role: Role


class BlockIn(BaseModel):
    space_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _order(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start.")
        return self


# ── Enquiries, quotes, bookings ─────────────────────────────────────────────────

class EnquiryCreate(BaseModel):
    space_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    guest_count: int = Field(ge=1, le=100_000)
    event_type: str | None = Field(default=None, max_length=80)
    budget_kobo: int | None = Field(default=None, ge=0)
    message: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _order(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start.")
        return self


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class QuoteIn(BaseModel):
    space_id: str
    starts_at: datetime
    ends_at: datetime
    total_kobo: int = Field(gt=0)
    deposit_kobo: int | None = Field(default=None, gt=0)
    balance_due_days: int | None = Field(default=None, ge=0, le=90)
    inclusions: str | None = Field(default=None, max_length=3000)
    valid_days: int = Field(default=7, ge=1, le=60)

    @model_validator(mode="after")
    def _check(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start.")
        if self.deposit_kobo is not None and self.deposit_kobo > self.total_kobo:
            raise ValueError("The deposit can't be more than the total.")
        return self


class PayIn(BaseModel):
    amount_kobo: int | None = Field(default=None, gt=0)
    callback_url: WebUrl | None = None


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    preview: bool = False


class DisputeIn(BaseModel):
    reason: Literal["not_as_listed", "venue_no_show", "organizer_no_show", "damage", "other"]
    description: str = Field(min_length=10, max_length=5000)
    evidence: list[WebUrl] = Field(default_factory=list, max_length=12)


class DisputeDecision(BaseModel):
    resolution: Literal["no_refund", "partial", "full"]
    refund_kobo: int | None = Field(default=None, ge=0)
    note: str = Field(min_length=3, max_length=3000)


class ReportIn(BaseModel):
    message_id: str | None = None
    details: str | None = Field(default=None, max_length=2000)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=3000)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


# ── Turnup+ and featured ────────────────────────────────────────────────────────

class DealIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    kind: Literal["free_entry", "discount", "free_item", "reserved", "other"] = "other"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_per_member: int = Field(default=1, ge=1, le=100)
    is_active: bool = True


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class FeaturedIn(BaseModel):
    scope: Literal["state", "area"]
    weeks: list[str] = Field(min_length=1, max_length=12)  # Monday dates, YYYY-MM-DD
    callback_url: WebUrl | None = None


class SubscribeIn(BaseModel):
    plan_code: str
    callback_url: WebUrl | None = None


# ── Agents ──────────────────────────────────────────────────────────────────────

class AgentIn(BaseModel):
    user_id: str
    states: list[str] = Field(min_length=1)
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool = True


class AssignIn(BaseModel):
    agent_id: str


class ScheduleIn(BaseModel):
    scheduled_for: datetime


class CheckInIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    note: str | None = Field(default=None, max_length=1000)


class VisitReportIn(BaseModel):
    checklist: dict[str, bool]
    notes: str = Field(min_length=3, max_length=5000)
    outcome: Literal["passed", "failed"]


class DocumentDecision(BaseModel):
    status: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=1000)


class VerificationDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class StrikeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class LedgerAdjustIn(BaseModel):
    amount_kobo: int
    note: str = Field(min_length=3, max_length=1000)


class SuspendIn(BaseModel):
    suspend: bool
    note: str | None = Field(default=None, max_length=1000)


class ChargebackDecision(BaseModel):
    status: Literal["won", "lost"]
