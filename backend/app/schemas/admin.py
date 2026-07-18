from datetime import datetime
from pydantic import BaseModel


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
    model_config = {"from_attributes": True}


class AdminEventUpdate(BaseModel):
    is_featured: bool | None = None
    is_trending: bool | None = None
    status: str | None = None


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
