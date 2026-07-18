from datetime import datetime
from pydantic import BaseModel, Field


ALLOWED_PLATFORMS = {"whatsapp", "instagram", "discord", "telegram", "twitter", "facebook", "tiktok", "youtube", "website"}


class SocialLinks(BaseModel):
    whatsapp: str | None = None
    instagram: str | None = None
    discord: str | None = None
    telegram: str | None = None
    twitter: str | None = None
    facebook: str | None = None
    tiktok: str | None = None
    youtube: str | None = None
    website: str | None = None


class CategoryMini(BaseModel):
    id: str
    name: str
    slug: str
    icon: str
    color: str
    model_config = {"from_attributes": True}


class CreatorMini(BaseModel):
    id: str
    username: str
    full_name: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_verified: bool
    role: str
    model_config = {"from_attributes": True}


class CommunityMemberOut(BaseModel):
    user_id: str
    username: str
    full_name: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_verified: bool
    role: str          # member | moderator | admin
    joined_at: datetime
    model_config = {"from_attributes": True}


class CommunityOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    cover_image: str | None
    icon: str | None
    city: str | None
    is_private: bool
    social_links: dict = {}
    member_count: int
    event_count: int
    creator: CreatorMini
    category: CategoryMini | None
    created_at: datetime
    # viewer context (injected at route layer)
    is_member: bool = False
    member_role: str | None = None   # "member" | "moderator" | "admin"
    is_verified_community: bool = False  # True when creator is organizer
    invite_token: str | None = None  # only shown to admins of private communities
    model_config = {"from_attributes": True}


class CommunityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    description: str | None = Field(None, max_length=2000)
    cover_image: str | None = None
    icon: str | None = Field(None, max_length=10)
    category_id: str | None = None
    city: str | None = Field(None, max_length=100)
    is_private: bool = False
    social_links: SocialLinks = SocialLinks()


class CommunityUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=100)
    description: str | None = Field(None, max_length=2000)
    cover_image: str | None = None
    icon: str | None = Field(None, max_length=10)
    category_id: str | None = None
    city: str | None = Field(None, max_length=100)
    is_private: bool | None = None
    social_links: SocialLinks | None = None


class ShareEventRequest(BaseModel):
    event_id: str
