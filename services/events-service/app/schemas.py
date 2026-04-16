from datetime import datetime
from pydantic import BaseModel, Field


class HostSummary(BaseModel):
    id: str
    username: str
    full_name: str
    avatar_url: str | None
    is_verified: bool
    followers_count: int = 0
    model_config = {"from_attributes": True}


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
    timezone: str = "America/New_York"
    is_free: bool = True
    price_min: float | None = None
    price_max: float | None = None
    ticket_url: str | None = None
    capacity: int | None = None
    category_id: str | None = None
    tags: str | None = None


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
    ticket_url: str | None = None
    capacity: int | None = None
    status: str | None = None
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
    status: str
    is_featured: bool
    is_trending: bool
    tags: str | None
    category: CategoryOut | None
    host: HostSummary
    created_at: datetime
    is_saved: bool = False
    attendance_status: str | None = None
    model_config = {"from_attributes": True}


class EventDetail(EventOut):
    description: str
    gallery: str | None
    latitude: float | None
    longitude: float | None
    timezone: str
    ticket_url: str | None
    capacity: int | None


class AttendRequest(BaseModel):
    status: str = Field(pattern=r"^(going|interested)$")
