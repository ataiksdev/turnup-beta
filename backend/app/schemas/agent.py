from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Admin ────────────────────────────────────────────────────────────────────

class AgentConnectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    host_username: str | None = None
    daily_limit: int | None = Field(None, ge=1, le=1000)
    callback_url: str | None = Field(None, max_length=500)


class AgentConnectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    is_active: bool | None = None
    host_username: str | None = None  # "" clears it (the scout bot hosts)
    daily_limit: int | None = Field(None, ge=1, le=1000)
    callback_url: str | None = Field(None, max_length=500)  # "" removes it


class AgentConnectionOut(BaseModel):
    id: str
    name: str
    is_active: bool
    api_key_prefix: str
    host_username: str | None
    daily_limit: int
    used_today: int
    events_created: int
    callback_url: str | None
    last_used_at: datetime | None
    created_at: datetime


class AgentConnectionCreated(AgentConnectionOut):
    # Shown once, at creation and rotation.
    api_key: str | None = None
    callback_secret: str | None = None


class AgentSubmissionOut(BaseModel):
    id: str
    connection_id: str
    connection_name: str
    status: str
    submitted_by: str | None
    input_text: str | None
    error_note: str | None
    event_id: str | None
    event_title: str | None
    event_review_status: str | None
    created_at: datetime


# ── Agent API (/api/integrations/v1) ─────────────────────────────────────────

class AgentEventIn(BaseModel):
    """An event your bot already extracted. Goes to the admin approval queue."""
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=10000)
    start_date: datetime
    end_date: datetime | None = None
    venue_name: str = Field("", max_length=200)
    address: str = Field("", max_length=300)
    city: str = Field("", max_length=100)
    country: str = Field("Nigeria", max_length=100)
    event_type: Literal["physical", "virtual", "hybrid"] = "physical"
    is_free: bool = True
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    currency: str = Field("NGN", min_length=3, max_length=3)
    category: str | None = Field(None, max_length=50, description="A name from GET /v1/categories")
    tags: list[str] | str | None = None
    cover_image: str | None = Field(None, max_length=500, description="Public http(s) image URL, e.g. the poster")
    ticket_url: str | None = Field(None, max_length=500)
    external_id: str | None = Field(None, max_length=200, description="Your id for this; resending it is a no-op")
    submitted_by: str | None = Field(None, max_length=200, description="Who gave your bot the event; echoed in callbacks")

    @field_validator("start_date", "end_date")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("include a timezone offset, e.g. 2026-12-05T19:00:00+01:00")
        return v


class AgentSubmissionStatus(BaseModel):
    submission_id: str
    status: str  # created | skipped_duplicate | skipped_no_event | failed | over_limit
    repeated: bool = False
    external_id: str | None = None
    submitted_by: str | None = None
    event_id: str | None = None
    event_title: str | None = None
    start_date: datetime | None = None
    venue_name: str | None = None
    review_status: str | None = None  # pending | approved | rejected, for an event this created
    review_note: str | None = None
    event_url: str | None = None  # once approved
    message: str  # plain-language outcome your bot can pass on
    created_at: datetime


class AgentMe(BaseModel):
    name: str
    daily_limit: int
    used_today: int
