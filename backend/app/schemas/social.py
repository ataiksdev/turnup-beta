from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.user import UserSummary


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: str | None = None


class CommentPublic(BaseModel):
    id: str
    content: str
    user: UserSummary
    event_id: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FollowPublic(BaseModel):
    follower_id: str
    following_id: str
    created_at: datetime
    is_following: bool = True

    model_config = {"from_attributes": True}


class NotificationPublic(BaseModel):
    id: str
    type: str
    title: str
    body: str | None
    reference_id: str | None
    reference_type: str | None
    actor: UserSummary | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
