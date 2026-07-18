import calendar
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_organizer
from app.models.event import Event, EventSeries
from app.schemas.series import SeriesCreate, SeriesOut

router = APIRouter(prefix="/api/series", tags=["series"])

# ── Horizon ──────────────────────────────────────────────────────────────────

_HORIZON_DAYS = 92  # rolling 3-month window


def _next_occurrence(dt: datetime, rule: str) -> datetime:
    if rule == "weekly":
        return dt + timedelta(weeks=1)
    elif rule == "bi-weekly":
        return dt + timedelta(weeks=2)
    elif rule in ("monthly", "bi-monthly"):
        months = 1 if rule == "monthly" else 2
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)
    raise ValueError(f"Unknown rule: {rule}")


def _slugify(text: str, uid: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-") + f"-{uid[:8]}"


def _ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime (handles naive datetimes from SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── Load helper ──────────────────────────────────────────────────────────────

async def _load_series(series_id: str, db: AsyncSession) -> EventSeries | None:
    stmt = (
        select(EventSeries)
        .options(selectinload(EventSeries.events))
        .where(EventSeries.id == series_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ── Event factory ────────────────────────────────────────────────────────────

def _make_event(
    *,
    series_id: str,
    host_id: str,
    title: str,
    description: str,
    cover_image: str | None,
    event_type: str,
    meeting_url: str | None,
    venue_name: str,
    address: str,
    city: str,
    country: str,
    tz: str,
    capacity: int | None,
    waitlist_enabled: bool,
    is_free: bool,
    price_min: float | None,
    price_max: float | None,
    currency: str,
    tags: str | None,
    category_id: str | None,
    start_date: datetime,
    end_date: datetime,
    status: str,
) -> Event:
    eid = str(uuid.uuid4())
    return Event(
        id=eid,
        title=title,
        slug=_slugify(title, eid),
        description=description,
        cover_image=cover_image,
        event_type=event_type,
        meeting_url=meeting_url,
        venue_name=venue_name,
        address=address,
        city=city,
        country=country,
        timezone=tz,
        capacity=capacity,
        waitlist_enabled=waitlist_enabled,
        is_free=is_free,
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        tags=tags,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        host_id=host_id,
        series_id=series_id,
    )


# ── Auto-advance ─────────────────────────────────────────────────────────────

async def _auto_advance(series: EventSeries, db: AsyncSession) -> bool:
    """
    Materialize events whose start_date has entered the rolling 3-month window.
    Returns True if any new events were created.
    """
    if series.next_occurrence_date is None:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=_HORIZON_DAYS)

    next_dt = _ensure_utc(series.next_occurrence_date)
    if next_dt > cutoff:
        return False

    # Need at least one existing event as a field template
    if not series.events:
        return False

    tmpl = series.events[0]  # all events share the same template fields
    duration = tmpl.end_date - tmpl.start_date

    created_count = len(series.events)
    total = series.total_occurrences
    current = next_dt
    new_events: list[Event] = []

    while created_count < total and _ensure_utc(current) <= cutoff:
        evt = _make_event(
            series_id=series.id,
            host_id=series.organizer_id,
            title=tmpl.title,
            description=tmpl.description,
            cover_image=tmpl.cover_image,
            event_type=tmpl.event_type,
            meeting_url=tmpl.meeting_url,
            venue_name=tmpl.venue_name,
            address=tmpl.address,
            city=tmpl.city,
            country=tmpl.country,
            tz=tmpl.timezone,
            capacity=tmpl.capacity,
            waitlist_enabled=tmpl.waitlist_enabled,
            is_free=tmpl.is_free,
            price_min=tmpl.price_min,
            price_max=tmpl.price_max,
            currency=tmpl.currency,
            tags=tmpl.tags,
            category_id=tmpl.category_id,
            start_date=current,
            end_date=current + duration,
            status=tmpl.status,
        )
        db.add(evt)
        new_events.append(evt)
        created_count += 1
        current = _next_occurrence(current, series.recurrence_rule)

    # Update series metadata
    if created_count >= total:
        series.next_occurrence_date = None
    else:
        series.next_occurrence_date = current

    if new_events:
        await db.flush()
        # Expire the series so the identity-map cache for `events` is cleared;
        # the next selectinload call will re-query the DB and see the new rows.
        db.expire(series)
        return True
    return False


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=SeriesOut, status_code=201)
async def create_series(
    payload: SeriesCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_organizer),
):
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=_HORIZON_DAYS)

    series_id = str(uuid.uuid4())

    # Compute all N start dates in memory
    all_dates: list[datetime] = []
    current = payload.start_date
    for _ in range(payload.occurrences):
        all_dates.append(current)
        current = _next_occurrence(current, payload.recurrence_rule)

    # Only materialise events within the horizon
    dates_to_create = [d for d in all_dates if _ensure_utc(d) <= cutoff]
    first_uncreated = next(
        (d for d in all_dates if _ensure_utc(d) > cutoff), None
    )

    duration = payload.end_date - payload.start_date

    series = EventSeries(
        id=series_id,
        title=payload.title,
        description=payload.description,
        recurrence_rule=payload.recurrence_rule,
        organizer_id=user.id,
        total_occurrences=payload.occurrences,
        next_occurrence_date=first_uncreated,
    )
    db.add(series)

    for start in dates_to_create:
        evt = _make_event(
            series_id=series_id,
            host_id=user.id,
            title=payload.event_title,
            description=payload.event_description,
            cover_image=payload.cover_image,
            event_type=payload.event_type,
            meeting_url=payload.meeting_url,
            venue_name=payload.venue_name,
            address=payload.address,
            city=payload.city,
            country=payload.country,
            tz=payload.timezone,
            capacity=payload.capacity,
            waitlist_enabled=payload.waitlist_enabled,
            is_free=payload.is_free,
            price_min=payload.price_min,
            price_max=payload.price_max,
            currency=payload.currency,
            tags=payload.tags,
            category_id=payload.category_id,
            start_date=start,
            end_date=start + duration,
            status=payload.status,
        )
        db.add(evt)

    await db.flush()
    return await _load_series(series_id, db)


@router.get("/{series_id}", response_model=SeriesOut)
async def get_series(
    series_id: str,
    db: AsyncSession = Depends(get_db),
):
    series = await _load_series(series_id, db)
    if not series:
        raise HTTPException(404, "Series not found")

    advanced = await _auto_advance(series, db)
    if advanced:
        # Reload to include newly created events
        series = await _load_series(series_id, db)

    return series


@router.delete("/{series_id}", status_code=204)
async def delete_series(
    series_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_organizer),
):
    series = (
        await db.execute(select(EventSeries).where(EventSeries.id == series_id))
    ).scalar_one_or_none()
    if not series:
        raise HTTPException(404, "Series not found")
    if series.organizer_id != user.id:
        raise HTTPException(403, "Not authorized")

    # Nullify series_id on events (don't cascade-delete the events)
    await db.execute(
        update(Event).where(Event.series_id == series_id).values(series_id=None)
    )
    await db.delete(series)
