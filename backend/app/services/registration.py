"""Promo codes and custom registration questions.

Promo codes: a code takes a percentage off each eligible ticket, or a fixed naira amount off the
whole order. Discounts are worked out in kobo and stored per order line, so the existing
payment check (sum of total_price == amount paid) and refunds keep working unchanged. A
checkout that uses a code holds one "use" (PromoRedemption) for as long as its tickets are
reserved; an unpaid cart that expires gives the use back.

Registration questions: asked when someone buys tickets or RSVPs "going". Answers are kept
per person per question (answering again replaces the old answer)."""
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organizer import (
    EventQuestion, PromoCode, PromoRedemption, RegistrationAnswer, TicketTier,
)

QUESTION_KINDS = ("text", "long_text", "single_choice", "multi_choice", "checkbox")
MAX_ANSWER_LENGTH = 2000


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalise_code(code: str) -> str:
    return code.strip().upper()


# ── Promo codes ───────────────────────────────────────────────────────────────────

async def find_valid_promo(db: AsyncSession, event_id: str, code: str) -> PromoCode:
    """The usable code, or a 400 that tells the buyer why not."""
    promo = (await db.execute(select(PromoCode).where(
        PromoCode.event_id == event_id, PromoCode.code == normalise_code(code),
    ))).scalar_one_or_none()
    if not promo or not promo.is_active:
        raise HTTPException(400, "That promo code isn't valid for this event.")
    now = datetime.now(timezone.utc)
    if promo.valid_from and now < _as_utc(promo.valid_from):
        raise HTTPException(400, "That promo code isn't active yet.")
    if promo.valid_until and now > _as_utc(promo.valid_until):
        raise HTTPException(400, "That promo code has expired.")
    if promo.max_uses is not None and promo.times_used >= promo.max_uses:
        raise HTTPException(400, "That promo code has been fully used.")
    return promo


def line_discounts(promo: PromoCode, lines: list[tuple[TicketTier, int]]) -> list[float]:
    """Naira off each (tier, quantity) line, in the same order. Never more than a line costs."""
    eligible = [
        (not promo.tier_ids or tier.id in promo.tier_ids) and tier.price > 0
        for tier, _ in lines
    ]
    line_kobo = [int(round(tier.price * qty * 100)) for tier, qty in lines]
    off = [0] * len(lines)
    if promo.discount_type == "percent":
        pct = min(max(promo.discount_value, 0), 100)
        for i, ok in enumerate(eligible):
            if ok:
                off[i] = min(line_kobo[i], int(round(line_kobo[i] * pct / 100)))
    else:
        remaining = int(round(max(promo.discount_value, 0) * 100))
        for i, ok in enumerate(eligible):
            if ok and remaining > 0:
                off[i] = min(line_kobo[i], remaining)
                remaining -= off[i]
    return [k / 100 for k in off]


async def take_use(db: AsyncSession, promo: PromoCode, user_id: str, reference: str,
                   discount_total: float) -> None:
    """Claim one use atomically (two buyers can't both take the last one)."""
    claimed = await db.execute(
        update(PromoCode).where(
            PromoCode.id == promo.id,
            or_(PromoCode.max_uses.is_(None), PromoCode.times_used < PromoCode.max_uses),
        ).values(times_used=PromoCode.times_used + 1)
    )
    if claimed.rowcount == 0:
        raise HTTPException(409, "That promo code has just been fully used.")
    db.add(PromoRedemption(
        id=str(uuid.uuid4()), promo_code_id=promo.id, event_id=promo.event_id, user_id=user_id,
        payment_reference=reference, discount_amount=discount_total,
    ))


async def release_use(db: AsyncSession, reference: str | None) -> None:
    """An unpaid cart expired: give its use back (once, however many lines the cart had)."""
    if not reference:
        return
    red = (await db.execute(select(PromoRedemption).where(
        PromoRedemption.payment_reference == reference))).scalar_one_or_none()
    if not red:
        return
    released = await db.execute(
        update(PromoRedemption).where(PromoRedemption.id == red.id, PromoRedemption.status == "active")
        .values(status="released")
    )
    if released.rowcount:
        await db.execute(update(PromoCode).where(PromoCode.id == red.promo_code_id, PromoCode.times_used > 0)
                         .values(times_used=PromoCode.times_used - 1))


async def retake_use(db: AsyncSession, reference: str | None) -> None:
    """An expired cart turned out to be paid after all: count its use again. The buyer has
    already paid the discounted price, so this is allowed even past max_uses."""
    if not reference:
        return
    red = (await db.execute(select(PromoRedemption).where(
        PromoRedemption.payment_reference == reference))).scalar_one_or_none()
    if not red:
        return
    taken = await db.execute(
        update(PromoRedemption).where(PromoRedemption.id == red.id, PromoRedemption.status == "released")
        .values(status="active")
    )
    if taken.rowcount:
        await db.execute(update(PromoCode).where(PromoCode.id == red.promo_code_id)
                         .values(times_used=PromoCode.times_used + 1))


# ── Registration questions ─────────────────────────────────────────────────────────

@dataclass
class CleanAnswer:
    question_id: str
    text: str


def _clean_one(q: EventQuestion, raw) -> str | None:
    """The stored text for one answer, None if left blank, or a 422 if it's not a valid answer."""
    if raw is None:
        return None
    if q.kind == "checkbox":
        if isinstance(raw, str):
            raw = raw.strip().lower() in ("true", "yes", "1", "on")
        return "yes" if raw else None
    if q.kind == "multi_choice":
        values = raw if isinstance(raw, list) else [raw]
        values = [str(v).strip() for v in values if str(v).strip()]
        bad = [v for v in values if v not in (q.options or [])]
        if bad:
            raise HTTPException(422, f"'{bad[0]}' isn't one of the choices for \"{q.label}\".")
        return json.dumps(values) if values else None
    if isinstance(raw, (list, dict)):
        raise HTTPException(422, f"Answer \"{q.label}\" with text.")
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > MAX_ANSWER_LENGTH:
        raise HTTPException(422, f"The answer to \"{q.label}\" is too long.")
    if q.kind == "single_choice" and text not in (q.options or []):
        raise HTTPException(422, f"'{text}' isn't one of the choices for \"{q.label}\".")
    return text


async def active_questions(db: AsyncSession, event_id: str) -> list[EventQuestion]:
    return list((await db.execute(select(EventQuestion).where(
        EventQuestion.event_id == event_id, EventQuestion.is_active == True,  # noqa: E712
    ).order_by(EventQuestion.position, EventQuestion.created_at))).scalars().all())


async def check_answers(db: AsyncSession, event_id: str, user_id: str,
                        answers: dict | None) -> list[CleanAnswer]:
    """Validate answers before anything is reserved. A required question counts as answered if
    this person answered it before (e.g. buying more tickets later). Raises 422 on a problem."""
    questions = await active_questions(db, event_id)
    if not questions:
        return []
    answers = answers or {}
    already = set((await db.execute(select(RegistrationAnswer.question_id).where(
        RegistrationAnswer.event_id == event_id, RegistrationAnswer.user_id == user_id,
    ))).scalars().all())
    clean: list[CleanAnswer] = []
    for q in questions:
        text = _clean_one(q, answers.get(q.id))
        if text is None:
            if q.required and q.id not in already:
                raise HTTPException(422, f"Please answer: {q.label}")
            continue
        clean.append(CleanAnswer(q.id, text))
    return clean


async def save_answers(db: AsyncSession, event_id: str, user_id: str, clean: list[CleanAnswer]) -> None:
    if not clean:
        return
    existing = {a.question_id: a for a in (await db.execute(select(RegistrationAnswer).where(
        RegistrationAnswer.event_id == event_id, RegistrationAnswer.user_id == user_id,
    ))).scalars().all()}
    for c in clean:
        if c.question_id in existing:
            existing[c.question_id].answer = c.text
        else:
            db.add(RegistrationAnswer(id=str(uuid.uuid4()), event_id=event_id,
                                      question_id=c.question_id, user_id=user_id, answer=c.text))


def display_answer(q: EventQuestion | None, text: str) -> str:
    """Stored text -> what an organizer reads (multi-choice lists joined)."""
    if q and q.kind == "multi_choice":
        try:
            return ", ".join(json.loads(text))
        except (ValueError, TypeError):
            return text
    return text
