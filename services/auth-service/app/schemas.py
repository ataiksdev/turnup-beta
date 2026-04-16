from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


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
    is_active: bool
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    category_preferences: str | None
    onboarding_completed: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    bio: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=120)
    website: str | None = Field(None, max_length=255)
    avatar_url: str | None = None


class OnboardingRequest(BaseModel):
    """Sent after registration to capture category preferences."""
    category_preferences: list[str] = Field(min_length=1, max_length=8,
                                             description="List of category slugs")


class OnboardingResponse(BaseModel):
    onboarding_completed: bool
    category_preferences: str | None


class UserInternal(BaseModel):
    """Returned to other services via internal endpoint."""
    id: str
    username: str
    full_name: str
    avatar_url: str | None
    is_verified: bool
    is_active: bool
    followers_count: int
    following_count: int
    events_hosted: int
    events_attended: int
    category_preferences: str | None
    onboarding_completed: bool
    model_config = {"from_attributes": True}
