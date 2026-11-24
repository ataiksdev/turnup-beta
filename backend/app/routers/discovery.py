"""What people tell the feed directly: hidden events and organizers, and search alerts."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.discovery import HiddenItem, SearchAlert
from app.models.event import Event
from app.models.user import User
from app.services.search import tokens
from app.services.search_alerts import MAX_ACTIVE_PER_USER, new_alert

router = APIRouter(prefix="/api", tags=["discovery"])


# ── Hidden events and organizers ────────────────────────────────────────────────

class HideRequest(BaseModel):
    kind: Literal["event", "organizer"]
    target_id: str = Field(min_length=1, max_length=36)


class HiddenOut(BaseModel):
    kind: str
    target_id: str
    created_at: datetime
    label: str          # event title, or organizer name
    detail: str | None  # event date and city, or @username
    link: str | None    # event slug, or username


async def _describe(db: AsyncSession, items: list[HiddenItem]) -> list[HiddenOut]:
    event_ids = [i.target_id for i in items if i.kind == "event"]
    user_ids = [i.target_id for i in items if i.kind == "organizer"]
    events = {e.id: e for e in (await db.execute(select(Event).where(Event.id.in_(event_ids)))).scalars()} if event_ids else {}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()} if user_ids else {}
    out = []
    for i in items:
        if i.kind == "event":
            e = events.get(i.target_id)
            out.append(HiddenOut(kind=i.kind, target_id=i.target_id, created_at=i.created_at,
                                 label=e.title if e else "An event that's been removed",
                                 detail=f"{e.start_date:%d %b %Y} · {e.city}" if e else None,
                                 link=e.slug if e else None))
        else:
            u = users.get(i.target_id)
            name = (u.display_name or u.full_name or u.username) if u else "An account that's been removed"
            out.append(HiddenOut(kind=i.kind, target_id=i.target_id, created_at=i.created_at, label=name,
                                 detail=f"@{u.username}" if u else None, link=u.username if u else None))
    return out


@router.get("/hidden", response_model=list[HiddenOut])
async def list_hidden(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    items = (await db.execute(select(HiddenItem).where(HiddenItem.user_id == user.id)
                              .order_by(HiddenItem.created_at.desc()))).scalars().all()
    return await _describe(db, list(items))


@router.post("/hidden", response_model=HiddenOut, status_code=201)
async def hide(body: HideRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.kind == "event":
        exists = (await db.execute(select(Event.id).where(Event.id == body.target_id))).scalar_one_or_none()
        if not exists:
            raise HTTPException(404, "Event not found")
    else:
        if body.target_id == user.id:
            raise HTTPException(400, "You can't hide yourself")
        exists = (await db.execute(select(User.id).where(User.id == body.target_id))).scalar_one_or_none()
        if not exists:
            raise HTTPException(404, "Organizer not found")
    item = (await db.execute(select(HiddenItem).where(
        HiddenItem.user_id == user.id, HiddenItem.kind == body.kind,
        HiddenItem.target_id == body.target_id))).scalar_one_or_none()
    if not item:
        item = HiddenItem(user_id=user.id, kind=body.kind, target_id=body.target_id)
        db.add(item)
        await db.commit()
        await db.refresh(item)
    return (await _describe(db, [item]))[0]


@router.delete("/hidden/{kind}/{target_id}", status_code=204)
async def unhide(kind: Literal["event", "organizer"], target_id: str,
                 db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.execute(delete(HiddenItem).where(
        HiddenItem.user_id == user.id, HiddenItem.kind == kind, HiddenItem.target_id == target_id))
    await db.commit()


# ── Search alerts ("Notify me") ─────────────────────────────────────────────────

class SearchAlertCreate(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)

    @field_validator("q", "city", "category")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class SearchAlertOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    query: str
    city: str | None
    category: str | None
    created_at: datetime
    expires_at: datetime
    notified_count: int


@router.get("/search-alerts", response_model=list[SearchAlertOut])
async def list_search_alerts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return (await db.execute(select(SearchAlert).where(
        SearchAlert.user_id == user.id, SearchAlert.is_active == True)  # noqa: E712
        .order_by(SearchAlert.created_at.desc()))).scalars().all()


@router.post("/search-alerts", response_model=SearchAlertOut, status_code=201)
async def create_search_alert(body: SearchAlertCreate, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    if not body.q or not tokens(body.q):
        raise HTTPException(422, "Enter some words to search for")
    active = SearchAlert.user_id == user.id, SearchAlert.is_active == True  # noqa: E712
    same = (await db.execute(select(SearchAlert).where(
        *active, func.lower(SearchAlert.query) == body.q.lower(),
        func.coalesce(func.lower(SearchAlert.city), "") == (body.city or "").lower(),
        func.coalesce(SearchAlert.category, "") == (body.category or "")))).scalars().first()
    if same:
        return same
    count = (await db.execute(select(func.count()).select_from(SearchAlert).where(*active))).scalar_one()
    if count >= MAX_ACTIVE_PER_USER:
        raise HTTPException(409, f"You can have up to {MAX_ACTIVE_PER_USER} search alerts. Remove one in Settings first.")
    alert = new_alert(user.id, body.q, body.city, body.category)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/search-alerts/{alert_id}", status_code=204)
async def delete_search_alert(alert_id: str, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    await db.execute(delete(SearchAlert).where(SearchAlert.id == alert_id, SearchAlert.user_id == user.id))
    await db.commit()
