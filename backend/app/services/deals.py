"""Turnup+ member deals: claim a code, show it at the door (docs/venues-spec.md 4.8 perk 6)."""
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.user import User
from app.models.venue import Deal, DealRedemption, Venue
from app.services.plus import is_plus

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _live(d: Deal) -> bool:
    now = utcnow()
    return d.is_active and (not d.valid_from or _utc(d.valid_from) <= now) and (not d.valid_to or _utc(d.valid_to) > now)


async def claim(db: AsyncSession, deal_id: str, user: User) -> DealRedemption:
    if not is_plus(user):
        raise HTTPException(402, "Deals are a Turnup+ perk.")
    d = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    if not d or not _live(d):
        raise HTTPException(404, "This deal isn't available.")
    # An unused claimed code is returned again rather than minting another.
    unused = (await db.execute(select(DealRedemption).where(
        DealRedemption.deal_id == d.id, DealRedemption.user_id == user.id,
        DealRedemption.redeemed_at.is_(None)))).scalars().first()
    if unused:
        return unused
    used = (await db.execute(select(func.count()).select_from(DealRedemption).where(
        DealRedemption.deal_id == d.id, DealRedemption.user_id == user.id))).scalar_one()
    if used >= d.max_per_member:
        raise HTTPException(409, "You've used this deal the maximum number of times.")
    r = DealRedemption(deal_id=d.id, user_id=user.id, code=_code())
    db.add(r)
    await db.flush()
    return r


async def redeem_code(db: AsyncSession, code: str, staff: User, *, venue_id: str | None = None,
                      event_id: str | None = None) -> dict:
    r = (await db.execute(select(DealRedemption).where(DealRedemption.code == code.strip().upper()))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Code not found.")
    d = (await db.execute(select(Deal).where(Deal.id == r.deal_id))).scalar_one()
    if (venue_id and d.venue_id != venue_id) or (event_id and d.event_id != event_id):
        raise HTTPException(404, "That code is for a different venue or event.")
    member = (await db.execute(select(User).where(User.id == r.user_id))).scalar_one()
    if r.redeemed_at:
        return {"ok": False, "reason": "already_used", "redeemed_at": r.redeemed_at, "deal": d.title}
    if not _live(d):
        return {"ok": False, "reason": "expired", "deal": d.title}
    if not is_plus(member):
        return {"ok": False, "reason": "membership_lapsed", "deal": d.title}
    r.redeemed_at = utcnow()
    r.redeemed_by_id = staff.id
    await db.flush()
    return {"ok": True, "deal": d.title, "kind": d.kind,
            "member": member.display_name or member.username}


async def my_deals(db: AsyncSession, user: User) -> list[dict]:
    rows = (await db.execute(select(DealRedemption, Deal).join(Deal, Deal.id == DealRedemption.deal_id).where(
        DealRedemption.user_id == user.id).order_by(DealRedemption.claimed_at.desc()))).all()
    out = []
    for r, d in rows:
        where = None
        if d.venue_id:
            v = (await db.execute(select(Venue.name, Venue.slug).where(Venue.id == d.venue_id))).first()
            where = {"type": "venue", "name": v[0], "slug": v[1]} if v else None
        elif d.event_id:
            e = (await db.execute(select(Event.title, Event.id).where(Event.id == d.event_id))).first()
            where = {"type": "event", "name": e[0], "id": e[1]} if e else None
        out.append({"code": r.code, "claimed_at": r.claimed_at, "redeemed_at": r.redeemed_at,
                    "deal": {"id": d.id, "title": d.title, "description": d.description, "kind": d.kind,
                             "valid_to": d.valid_to}, "where": where})
    return out
