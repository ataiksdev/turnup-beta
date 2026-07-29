from datetime import datetime
from pydantic import BaseModel, Field


class AdminUserOut(BaseModel):
    id: str
    username: str
    full_name: str | None
    display_name: str | None
    email: str | None
    role: str
    is_active: bool
    is_verified: bool
    email_verified: bool
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    created_at: datetime
    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class AdminEventOut(BaseModel):
    id: str
    title: str
    slug: str
    status: str
    is_featured: bool
    is_trending: bool
    event_type: str
    city: str
    country: str
    start_date: datetime
    attendees_count: int
    views_count: int
    host_username: str
    host_id: str
    created_at: datetime
    review_status: str
    review_note: str | None = None
    created_via: str
    reviewed_by_username: str | None = None
    reviewed_at: datetime | None = None
    model_config = {"from_attributes": True}


class AdminEventUpdate(BaseModel):
    is_featured: bool | None = None
    is_trending: bool | None = None
    status: str | None = None


class AdminEventReject(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class AIEventDraft(BaseModel):
    title: str = ""
    description: str = ""
    venue_name: str = ""
    address: str = ""
    city: str = ""
    country: str = ""
    start_date: str = ""
    end_date: str = ""
    is_free: bool = True
    price_min: float | None = None
    price_max: float | None = None
    currency: str = ""
    event_type: str = "physical"
    category_guess: str = ""
    tags: str = ""
    confidence_notes: str = ""


class AdminCategoryCreate(BaseModel):
    name: str
    slug: str
    icon: str = "🎉"
    color: str = "#F97316"
    description: str | None = None


class AdminCategoryUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    icon: str | None = None
    color: str | None = None
    description: str | None = None


class AdminCategoryOut(BaseModel):
    id: str
    name: str
    slug: str
    icon: str
    color: str
    description: str | None
    model_config = {"from_attributes": True}


class AdminOrderOut(BaseModel):
    id: str
    event_id: str
    event_title: str
    tier_name: str
    buyer_username: str
    buyer_email: str | None
    quantity: int
    unit_price: float
    total_price: float
    currency: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ScoutSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: str = Field(min_length=8, max_length=500)


class ScoutSourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    is_active: bool | None = None


class ScoutSourceOut(BaseModel):
    id: str
    name: str
    url: str
    is_active: bool
    last_polled_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ScoutedItemOut(BaseModel):
    id: str
    source_id: str
    source_name: str
    url: str
    status: str
    event_id: str | None
    event_title: str | None
    error_note: str | None
    created_at: datetime


class ScoutRunResult(BaseModel):
    sources_polled: int
    items_seen: int
    events_created: int
    skipped_duplicate: int
    skipped_no_event: int
    failed: int


class PlatformStats(BaseModel):
    total_users: int
    total_organizers: int
    total_events: int
    published_events: int
    total_orders: int
    confirmed_revenue: float
    total_attendees: int
    new_users_this_week: int
    new_events_this_week: int
