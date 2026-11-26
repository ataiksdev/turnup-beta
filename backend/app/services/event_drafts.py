"""Turning a drafted event (from the AI drafter, or fields an outside agent sent) into an Event
waiting in the admin approval queue. Shared by the daily scout agent and agent connections
(app/services/agent_intake.py), so both validate, dedupe and create pending events the same way.
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.routers.events import _slugify
from app.schemas.admin import AIEventDraft
from app.schemas.types import safe_web_url_or_none


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def find_duplicate_event(db: AsyncSession, draft: AIEventDraft, start: datetime) -> Event | None:
    # Same venue on the same calendar day, as a datetime range rather than DATE(col) = 'text':
    # that comparison only works on SQLite (Postgres has no date = varchar operator).
    day_start = datetime.combine(start.date(), datetime.min.time(), tzinfo=start.tzinfo)
    day_end = day_start + timedelta(days=1)
    stmt = select(Event).where(
        or_(
            func.lower(Event.title) == draft.title.strip().lower(),
            and_(
                Event.venue_name == draft.venue_name,
                Event.start_date >= day_start,
                Event.start_date < day_end,
            ),
        )
    )
    return (await db.execute(stmt)).scalars().first()


async def create_pending_event(
    db: AsyncSession,
    draft: AIEventDraft,
    *,
    host_id: str,
    created_via: str,
    categories_by_name: dict[str, str],
    ticket_url: str | None = None,
) -> tuple[str, Event | None]:
    """Validate and dedupe a draft, then create it as a draft Event pending admin review.

    Returns (status, event): "created" with the new event, "skipped_duplicate" with the event
    it duplicates, or "skipped_no_event" with None when the draft lacks a title, description
    or start date."""
    start = parse_iso(draft.start_date)
    if not draft.title.strip() or not draft.description.strip() or not start:
        return "skipped_no_event", None

    dup = await find_duplicate_event(db, draft, start)
    if dup:
        return "skipped_duplicate", dup

    end = parse_iso(draft.end_date) or (start + timedelta(hours=3))
    if end <= start:
        end = start + timedelta(hours=3)
    category_id = categories_by_name.get(draft.category_guess.strip().lower())

    eid = str(uuid.uuid4())
    event = Event(
        id=eid,
        slug=_slugify(draft.title, eid),
        title=draft.title.strip()[:200],
        description=draft.description.strip(),
        cover_image=safe_web_url_or_none(draft.cover_image),
        venue_name=(draft.venue_name.strip() or "Venue TBA")[:200],
        address=(draft.address.strip() or "Address TBA")[:300],
        city=(draft.city.strip() or "Unknown")[:100],
        country=(draft.country.strip() or "Nigeria")[:100],
        start_date=start,
        end_date=end,
        is_free=draft.is_free,
        price_min=draft.price_min,
        price_max=draft.price_max,
        currency=(draft.currency or "NGN")[:3],
        event_type=draft.event_type if draft.event_type in ("physical", "virtual", "hybrid") else "physical",
        category_id=category_id,
        tags=draft.tags or None,
        ticket_url=safe_web_url_or_none(ticket_url),
        status="draft",
        review_status="pending",
        created_via=created_via,
        host_id=host_id,
    )
    db.add(event)
    await db.flush()
    return "created", event
