from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, EmailStr, Field
from app.schemas.organizer import OrganizerProfileOut
from app.schemas.types import WebUrl

# Phone-OTP sign-ups have no name yet; serialize that as "" rather than failing validation
# (a None here used to make /auth/me -- and so every phone login -- return a 500).
NameStr = Annotated[str, BeforeValidator(lambda v: v or "")]

# Must match the theme ids in frontend/src/lib/themes.ts (tests/test_themes.py checks this).
THEME_IDS = ("turnup", "sunset", "lagoon", "palm", "gold", "neon", "glass", "fluffy")
THEME_PREFERENCE_PATTERN = rf"^({'|'.join(THEME_IDS)}):(light|dark|system)$"


class UserSummary(BaseModel):
    id: str
    username: str
    full_name: NameStr
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None
    is_verified: bool
    is_verified_organizer: bool = False
    role: str
    followers_count: int
    events_hosted: int = 0
    avg_rating: float | None = None
    review_count: int = 0
    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    id: str
    username: str
    full_name: NameStr
    display_name: str | None = None
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
    avg_rating: float | None = None
    review_count: int = 0
    category_preferences: str | None
    created_at: datetime
    is_following: bool = False
    plus_badge: bool = False  # Turnup+ member who shows the badge
    organizer_profile: OrganizerProfileOut | None = None
    model_config = {"from_attributes": True}


class UserMe(BaseModel):
    id: str
    email: EmailStr | None = None
    username: str
    full_name: NameStr
    display_name: str | None = None
    bio: str | None
    avatar_url: str | None
    location: str | None
    website: str | None
    is_verified: bool
    email_verified: bool
    two_factor_enabled: bool
    has_password: bool = False
    role: str
    is_active: bool
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    category_preferences: str | None
    city: str | None = None
    price_sensitivity: str | None = None
    event_format_pref: str | None = None
    goes_out_when: str | None = None
    onboarding_completed: bool
    theme_preference: str | None = None
    plus_until: datetime | None = None
    show_plus_badge: bool = True
    wrapped_opt_in: bool = True
    created_at: datetime
    organizer_profile: OrganizerProfileOut | None = None
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    display_name: str | None = Field(None, max_length=80)
    bio: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=120)
    website: WebUrl | None = Field(None, max_length=255)
    avatar_url: WebUrl | None = None
    theme_preference: str | None = Field(None, pattern=THEME_PREFERENCE_PATTERN)
