"""Activity from the app (docs/recommendations-spec.md)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.activity import IdentifyRequest, TrackBatch
from app.services.activity import ingest, link_anonymous

router = APIRouter(prefix="/api/track", tags=["tracking"])


@router.post("", status_code=202)
@limiter.limit(settings.rate_limit_track)
async def track(
    request: Request,
    batch: TrackBatch,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """A batch of up to 50 events from the app, signed in or not."""
    return {"accepted": await ingest(db, batch, user)}


@router.post("/identify", status_code=202)
@limiter.limit(settings.rate_limit_track)
async def identify(
    request: Request,
    payload: IdentifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Called by the app right after signing in or up: this device's earlier signed-out
    browsing becomes part of the account."""
    return {"linked": await link_anonymous(db, user, payload.anonymous_id)}
