from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal


class SeriesCreate(BaseModel):
    # Series metadata
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    recurrence_rule: Literal["weekly", "bi-weekly", "monthly", "bi-monthly"]
    occurrences: int = Field(ge=2, le=52)

    # First event fields (reused for all occurrences)
    event_title: str = Field(min_length=5, max_length=200)
    event_description: str = Field(min_length=20, max_length=2000)
    cover_image: str | None = None
    event_type: Literal["physical", "virtual", "hybrid"] = "physical"
    meeting_url: str | None = None
    venue_name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    country: str = "NG"
    timezone: str = "Africa/Lagos"
    capacity: int | None = None
    waitlist_enabled: bool = False
    is_free: bool = True
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "NGN"
    tags: str | None = None
    category_id: str | None = None
    start_date: datetime   # first occurrence start
    end_date: datetime     # first occurrence end (duration applied to all)
    status: Literal["draft", "published"] = "published"


class SeriesEventOut(BaseModel):
    id: str
    title: str
    slug: str
    start_date: datetime
    end_date: datetime
    status: str
    attendees_count: int
    model_config = {"from_attributes": True}


class SeriesOut(BaseModel):
    id: str
    title: str
    description: str | None
    recurrence_rule: str
    organizer_id: str
    total_occurrences: int
    next_occurrence_date: datetime | None
    created_at: datetime
    events: list[SeriesEventOut]
    model_config = {"from_attributes": True}
