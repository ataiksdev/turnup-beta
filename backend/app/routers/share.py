"""Share links with a ref code (app/services/sharing.py)."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import limiter
from app.models.event import Event
from app.models.sharing import ShareConversion, ShareLink
from app.models.user import User
from app.services.sharing import get_or_create_link, record_open

router = APIRouter(prefix="/api/share", tags=["share"])


class ShareCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=36)
    channel: Literal["whatsapp", "native", "copy_link"]


class ShareOut(BaseModel):
    code: str
    url: str


class ShareOpen(BaseModel):
    code: str = Field(min_length=4, max_length=12, pattern=r"^[A-Za-z0-9]+$")


@router.post("", response_model=ShareOut)
async def create_share_link(body: ShareCreate, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    event = (await db.execute(select(Event).where(Event.id == body.event_id))).scalar_one_or_none()
    if not event or event.status != "published":
        raise HTTPException(404, "Event not found")
    link = await get_or_create_link(db, user.id, event.id, body.channel)
    await db.commit()
    return ShareOut(code=link.code, url=f"{settings.frontend_url.rstrip('/')}/events/{event.slug}?ref={link.code}")


@router.post("/open", status_code=204)
@limiter.limit("60/minute")
async def open_share_link(request: Request, body: ShareOpen, db: AsyncSession = Depends(get_db),
                          user: User | None = Depends(get_optional_user)):
    """The app calls this when an event page is opened with ?ref=. Unknown codes are ignored."""
    anon = (request.headers.get("x-anonymous-id") or "")[:64] or None
    await record_open(db, body.code, user.id if user else None, anon)
    await db.commit()


class SharedEventOut(BaseModel):
    event_id: str
    title: str
    slug: str
    start_date: datetime
    opens: int
    saved: int
    going: int
    bought: int


class MySharesOut(BaseModel):
    people_brought: int      # distinct people who RSVP'd "going" or bought through your links
    opens: int
    events: list[SharedEventOut]


@router.get("/mine", response_model=MySharesOut)
async def my_shares(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    links = (await db.execute(select(ShareLink, Event).join(Event, Event.id == ShareLink.event_id)
                              .where(ShareLink.user_id == user.id))).all()
    convs = (await db.execute(select(ShareConversion.event_id, ShareConversion.kind,
                                     func.count(func.distinct(ShareConversion.user_id)))
                              .where(ShareConversion.sharer_id == user.id)
                              .group_by(ShareConversion.event_id, ShareConversion.kind))).all()
    counts: dict[tuple[str, str], int] = {(eid, kind): n for eid, kind, n in convs}
    people = (await db.execute(select(func.count(func.distinct(ShareConversion.user_id))).where(
        ShareConversion.sharer_id == user.id, ShareConversion.kind.in_(("going", "order"))))).scalar_one()
    per_event: dict[str, SharedEventOut] = {}
    for link, event in links:
        row = per_event.get(event.id)
        if not row:
            row = per_event[event.id] = SharedEventOut(
                event_id=event.id, title=event.title, slug=event.slug, start_date=event.start_date, opens=0,
                saved=counts.get((event.id, "save"), 0), going=counts.get((event.id, "going"), 0),
                bought=counts.get((event.id, "order"), 0))
        row.opens += link.opens
    events = sorted(per_event.values(), key=lambda r: (-(r.going + r.bought), -r.opens))
    return MySharesOut(people_brought=people, opens=sum(r.opens for r in events), events=events[:50])
