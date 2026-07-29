import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.event import Category, Event
from app.models.scout import ScoutedItem, ScoutSource
from app.models.user import User
from app.routers.events import _slugify
from app.schemas.admin import AIEventDraft
from app.services.ai_agent import AIAgentError, draft_event

_FEED_FETCH_TIMEOUT = 15
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass
class ScoutRunSummary:
    sources_polled: int = 0
    items_seen: int = 0
    events_created: int = 0
    skipped_duplicate: int = 0
    skipped_no_event: int = 0
    failed: int = 0


def _parse_feed_links(xml_text: str) -> list[str]:
    """Extract entry links from an RSS or Atom feed. Best-effort, tolerant of malformed feeds."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    links: list[str] = []

    # RSS 2.0: <rss><channel><item><link>text</link>
    for item in root.findall(".//item"):
        link_el = item.find("link")
        if link_el is not None and link_el.text:
            links.append(link_el.text.strip())

    # Atom: <feed><entry><link href="...">
    for entry in root.findall(f".//{_ATOM_NS}entry"):
        link_el = entry.find(f"{_ATOM_NS}link")
        if link_el is not None and link_el.get("href"):
            links.append(link_el.get("href").strip())

    seen: set[str] = set()
    out = []
    for link in links:
        if link and link not in seen:
            seen.add(link)
            out.append(link)
    return out


async def _fetch_feed_links(url: str) -> list[str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=_FEED_FETCH_TIMEOUT) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TurnupScoutBot/1.0)"})
        resp.raise_for_status()
    return _parse_feed_links(resp.text)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _find_duplicate_event(db: AsyncSession, draft: AIEventDraft, start: datetime) -> Event | None:
    stmt = select(Event).where(
        or_(
            func.lower(Event.title) == draft.title.strip().lower(),
            and_(
                Event.venue_name == draft.venue_name,
                func.date(Event.start_date) == start.date().isoformat(),
            ),
        )
    )
    return (await db.execute(stmt)).scalars().first()


async def _process_item(
    db: AsyncSession,
    source: ScoutSource,
    url: str,
    bot: User,
    category_names: list[str],
    categories_by_name: dict[str, str],
) -> str:
    """Draft one candidate URL and create a pending Event if it looks like a real event.
    Returns the resulting ScoutedItem status."""
    try:
        raw = await draft_event(
            text=None, url=url, image_bytes=None, image_media_type=None,
            category_names=category_names,
        )
    except AIAgentError as e:
        db.add(ScoutedItem(id=str(uuid.uuid4()), source_id=source.id, url=url, status="failed", error_note=str(e)))
        return "failed"

    draft = AIEventDraft(**raw)
    start = _parse_iso(draft.start_date)
    if not draft.title.strip() or not draft.description.strip() or not start:
        db.add(ScoutedItem(id=str(uuid.uuid4()), source_id=source.id, url=url, status="skipped_no_event"))
        return "skipped_no_event"

    dup = await _find_duplicate_event(db, draft, start)
    if dup:
        db.add(ScoutedItem(id=str(uuid.uuid4()), source_id=source.id, url=url, status="skipped_duplicate", event_id=dup.id))
        return "skipped_duplicate"

    end = _parse_iso(draft.end_date) or (start + timedelta(hours=3))
    category_id = categories_by_name.get(draft.category_guess.strip().lower())

    eid = str(uuid.uuid4())
    event = Event(
        id=eid,
        slug=_slugify(draft.title, eid),
        title=draft.title.strip(),
        description=draft.description.strip(),
        venue_name=draft.venue_name.strip() or "Venue TBA",
        address=draft.address.strip() or "Address TBA",
        city=draft.city.strip() or "Unknown",
        country=draft.country.strip() or "Nigeria",
        start_date=start,
        end_date=end,
        is_free=draft.is_free,
        price_min=draft.price_min,
        price_max=draft.price_max,
        currency=draft.currency or "NGN",
        event_type=draft.event_type,
        category_id=category_id,
        tags=draft.tags or None,
        status="draft",
        review_status="pending",
        created_via="ai_agent",
        host_id=bot.id,
    )
    db.add(event)
    await db.flush()
    db.add(ScoutedItem(id=str(uuid.uuid4()), source_id=source.id, url=url, status="created", event_id=eid))
    return "created"


async def run_daily_scout(db: AsyncSession) -> ScoutRunSummary:
    summary = ScoutRunSummary()

    bot = (await db.execute(
        select(User).where(User.username == settings.scout_bot_username)
    )).scalar_one_or_none()
    if not bot:
        raise RuntimeError(f"Scout bot account '{settings.scout_bot_username}' not found — run init_db first.")

    categories = (await db.execute(select(Category))).scalars().all()
    category_names = [c.name for c in categories]
    categories_by_name = {c.name.lower(): c.id for c in categories}

    already_seen: set[str] = set((await db.execute(select(ScoutedItem.url))).scalars().all())

    sources = (await db.execute(select(ScoutSource).where(ScoutSource.is_active == True))).scalars().all()

    budget = settings.scout_max_items_per_run
    for source in sources:
        summary.sources_polled += 1
        try:
            links = await _fetch_feed_links(source.url)
        except Exception as e:
            source.last_polled_at = datetime.now(timezone.utc)
            source.last_run_status = f"fetch failed: {e}"
            continue

        new_links = [link for link in links if link not in already_seen]
        processed = 0
        for url in new_links:
            if budget <= 0:
                break
            already_seen.add(url)
            summary.items_seen += 1
            processed += 1
            status = await _process_item(db, source, url, bot, category_names, categories_by_name)
            budget -= 1
            if status == "created":
                summary.events_created += 1
            elif status == "skipped_duplicate":
                summary.skipped_duplicate += 1
            elif status == "skipped_no_event":
                summary.skipped_no_event += 1
            else:
                summary.failed += 1

        source.last_polled_at = datetime.now(timezone.utc)
        source.last_run_status = f"ok: {processed} new item(s) processed"
        await db.flush()

        if budget <= 0:
            break

    await db.commit()
    return summary
