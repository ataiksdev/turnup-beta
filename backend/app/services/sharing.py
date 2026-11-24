"""Share links with a ref code, and credit for the people they bring in.

1. A signed-in person shares an event: get_or_create_link() gives them a code per event and
   channel, and the app shares /events/<slug>?ref=<code>.
2. Someone opens it: record_open() writes a `share_link_opened` server event under their
   device id (and account, if signed in). If they sign up or log in later, the usual
   account linking (services/activity.link_anonymous) attaches it to their account.
3. Within ATTRIBUTION_DAYS they save the event, RSVP "going" or buy a ticket: credit()
   finds their latest open for that event and records a ShareConversion for the sharer.
   Nobody is credited for themselves.

The conversions feed users' tastemaker_score (rec_features._tastemaker_scores) and the
"people you brought" count (GET /api/share/mine).
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.sharing import ShareConversion, ShareLink
from app.services.activity import record

ATTRIBUTION_DAYS = 7
CHANNELS = ("whatsapp", "native", "copy_link")
KINDS = ("save", "going", "order")
_ALPHABET = string.ascii_letters + string.digits


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def get_or_create_link(db: AsyncSession, user_id: str, event_id: str, channel: str) -> ShareLink:
    q = select(ShareLink).where(ShareLink.user_id == user_id, ShareLink.event_id == event_id,
                                ShareLink.channel == channel)
    link = (await db.execute(q)).scalar_one_or_none()
    if link:
        return link
    for _ in range(5):
        link = ShareLink(user_id=user_id, event_id=event_id, channel=channel, code=_new_code())
        try:
            async with db.begin_nested():
                db.add(link)
            return link
        except IntegrityError:  # code collision, or the same link made at the same moment
            existing = (await db.execute(q)).scalar_one_or_none()
            if existing:
                return existing
    raise RuntimeError("Couldn't make a share code")


async def record_open(db: AsyncSession, code: str, user_id: str | None, anonymous_id: str | None) -> ShareLink | None:
    link = (await db.execute(select(ShareLink).where(ShareLink.code == code))).scalar_one_or_none()
    if not link or (user_id and user_id == link.user_id) or not (user_id or anonymous_id):
        return link
    who = [Activity.user_id == user_id] if user_id else []
    if anonymous_id:
        who.append(Activity.anonymous_id == anonymous_id)
    seen = (await db.execute(select(Activity.id).where(
        Activity.name == "share_link_opened", Activity.event_id == link.event_id, or_(*who),
        Activity.props["code"].as_string() == code).limit(1))).first()
    if not seen:
        link.opens += 1
    record(db, "share_link_opened", user_id=user_id, anonymous_id=anonymous_id, event_id=link.event_id,
           props={"code": code, "channel": link.channel, "sharer_id": link.user_id})
    return link


async def credit(db: AsyncSession, user_id: str, event_id: str, kind: str, now: datetime | None = None) -> bool:
    """Called where saves, "going" RSVPs and confirmed orders happen. True if a sharer was credited."""
    now = now or datetime.now(timezone.utc)
    opened = (await db.execute(
        select(Activity.props).where(
            Activity.name == "share_link_opened", Activity.user_id == user_id, Activity.event_id == event_id,
            Activity.occurred_at >= now - timedelta(days=ATTRIBUTION_DAYS), Activity.occurred_at <= now)
        .order_by(Activity.occurred_at.desc()).limit(1)
    )).scalar_one_or_none()
    code = (opened or {}).get("code")
    if not code:
        return False
    link = (await db.execute(select(ShareLink).where(ShareLink.code == code))).scalar_one_or_none()
    if not link or link.user_id == user_id:
        return False
    exists = (await db.execute(select(ShareConversion.id).where(
        ShareConversion.share_link_id == link.id, ShareConversion.user_id == user_id,
        ShareConversion.kind == kind))).first()
    if exists:
        return False
    try:
        async with db.begin_nested():
            db.add(ShareConversion(share_link_id=link.id, sharer_id=link.user_id, user_id=user_id,
                                   event_id=event_id, kind=kind))
    except IntegrityError:
        return False
    return True


async def people_brought(db: AsyncSession, sharer_ids, since: datetime,
                         until: datetime | None = None) -> dict[str, int]:
    """Distinct people each sharer brought to an event ("going" or a ticket) in [since, until)."""
    until = until or datetime.now(timezone.utc)
    rows = (await db.execute(
        select(ShareConversion.sharer_id, func.count(func.distinct(ShareConversion.user_id)))
        .where(ShareConversion.sharer_id.in_(sharer_ids), ShareConversion.kind.in_(("going", "order")),
               ShareConversion.created_at >= since, ShareConversion.created_at < until)
        .group_by(ShareConversion.sharer_id))).all()
    return dict(rows)
