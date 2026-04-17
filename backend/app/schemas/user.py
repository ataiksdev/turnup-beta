from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.schemas.organizer import OrganizerProfileOut


class UserSummary(BaseModel):
    id: str
    username: str
    full_name: str
    avatar_url: str | None
    is_verified: bool
    role: str
    followers_count: int
    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    id: str
    username: str
    full_name: str
    bio: str | None
    avatar_url: str | None
    location: str | None
    website: str | None
    is_verified: bool
    role: str
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    category_preferences: str | None
    created_at: datetime
    is_following: bool = False
    organizer_profile: OrganizerProfileOut | None = None
    model_config = {"from_attributes": True}


class UserMe(BaseModel):
    id: str
    email: EmailStr
    username: str
    full_name: str
    bio: str | None
    avatar_url: str | None
    location: str | None
    website: str | None
    is_verified: bool
    email_verified: bool
    two_factor_enabled: bool
    role: str
    is_active: bool
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    category_preferences: str | None
    onboarding_completed: bool
    created_at: datetime
    organizer_profile: OrganizerProfileOut | None = None
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    bio: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=120)
    website: str | None = Field(None, max_length=255)
    avatar_url: str | None = None
