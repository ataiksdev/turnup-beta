"""Request bodies for POST /api/track (see app/services/activity.py)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

_ID = r"^[A-Za-z0-9_-]{8,64}$"


class TrackGeo(BaseModel):
    city: str | None = Field(None, max_length=100)
    # Kept only for signed-in users who opted in to profiling (app/services/activity.py).
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class TrackEvent(BaseModel):
    id: str | None = Field(None, pattern=_ID)          # the app's id, for de-duplicating retries
    name: str = Field(..., max_length=40)
    ts: datetime | None = None
    event_id: str | None = Field(None, max_length=36)
    surface: str | None = Field(None, max_length=30)
    position: int | None = Field(None, ge=0, le=1000)
    rec_request_id: str | None = Field(None, max_length=36)
    is_promoted: bool = False
    props: dict | None = None


class TrackBatch(BaseModel):
    anonymous_id: str = Field(..., pattern=_ID)
    session_id: str | None = Field(None, pattern=_ID)
    platform: Literal["web", "android", "ios"] = "web"
    app_version: str | None = Field(None, max_length=20)
    referrer: str | None = Field(None, max_length=300)
    utm_campaign: str | None = Field(None, max_length=100)
    geo: TrackGeo | None = None
    events: list[TrackEvent] = Field(..., max_length=50)


class IdentifyRequest(BaseModel):
    anonymous_id: str = Field(..., pattern=_ID)
