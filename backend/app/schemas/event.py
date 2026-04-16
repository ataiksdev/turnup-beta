from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.user import UserSummary


class CategoryPublic(BaseModel):
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
    country: str = Field(default="US", max_length=100)
    latitude: float | None = None
    longitude: float | None = None
    start_date: datetime
    end_date: datetime
    timezone: str = "America/New_York"
    is_free: bool = True
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "USD"
    ticket_url: str | None = None
    capacity: int | None = None
    category_id: str | None = None
    tags: str | None = None  # comma-separated


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=5, max_length=200)
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
    ticket_url: str | None = None
    capacity: int | None = None
    status: str | None = None
    tags: str | None = None


class EventPublic(BaseModel):
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
    status: str
    is_featured: bool
    is_trending: bool
    tags: str | None
    host: UserSummary
    category: CategoryPublic | None
    created_at: datetime
    # Per-user state (set dynamically)
    is_saved: bool = False
    attendance_status: str | None = None  # "going" | "interested" | None

    model_config = {"from_attributes": True}


class EventDetail(EventPublic):
    description: str
    gallery: str | None
    latitude: float | None
    longitude: float | None
    timezone: str
    ticket_url: str | None
    capacity: int | None
    address: str


class EventAttendeeCreate(BaseModel):
    status: str = Field(pattern=r"^(going|interested)$")


class EventSaveToggle(BaseModel):
    saved: bool
