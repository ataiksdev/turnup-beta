from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.user import UserSummary


class CategoryOut(BaseModel):
    id: str
    name: str
    slug: str
    icon: str
    color: str
    model_config = {"from_attributes": True}


class EventCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20)
    cover_image: str | None = None
    venue_name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=5, max_length=300)
    city: str = Field(min_length=2, max_length=100)
    country: str = "US"
    latitude: float | None = None
    longitude: float | None = None
    start_date: datetime
    end_date: datetime
    timezone: str = "Africa/Lagos"
    is_free: bool = True
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "NGN"
    capacity: int | None = None
    waitlist_enabled: bool = False
    category_id: str | None = None
    tags: str | None = None
    event_type: str = Field("physical", pattern=r"^(physical|virtual|hybrid)$")
    meeting_url: str | None = None
    status: str = Field("published", pattern=r"^(draft|published)$")
    template_id: str | None = None  # optional: create from template
    created_via: str = Field("manual", pattern=r"^(manual|ai_agent)$")


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    cover_image: str | None = None
    venue_name: str | None = None
    address: str | None = None
    city: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_free: bool | None = None
    price_min: float | None = None
    price_max: float | None = None
    capacity: int | None = None
    waitlist_enabled: bool | None = None
    event_type: str | None = Field(None, pattern=r"^(physical|virtual|hybrid)$")
    meeting_url: str | None = None
    status: str | None = Field(None, pattern=r"^(draft|published|cancelled|completed)$")
    tags: str | None = None


class EventOut(BaseModel):
    id: str
    title: str
    slug: str
    cover_image: str | None
    venue_name: str
    address: str
    city: str
    country: str
    start_date: datetime
    end_date: datetime
    is_free: bool
    price_min: float | None
    price_max: float | None
    currency: str
    attendees_count: int
    interested_count: int
    saves_count: int
    waitlist_count: int
    views_count: int
    waitlist_enabled: bool
    status: str
    is_featured: bool
    is_trending: bool
    tags: str | None
    host: UserSummary
    category: CategoryOut | None
    created_at: datetime
    event_type: str = "physical"
    is_saved: bool = False
    attendance_status: str | None = None
    is_waitlisted: bool = False
    review_status: str = "approved"
    review_note: str | None = None
    created_via: str = "manual"
    model_config = {"from_attributes": True}


class EventDetail(EventOut):
    description: str
    gallery: str | None
    latitude: float | None
    longitude: float | None
    timezone: str
    meeting_url: str | None
    capacity: int | None
    template_id: str | None
    avg_rating: float | None = None
    review_count: int = 0


class AttendRequest(BaseModel):
    status: str = Field(pattern=r"^(going|interested)$")
