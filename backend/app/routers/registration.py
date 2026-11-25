"""Promo codes and registration questions for an event (organizer management + buyer checks).

Checkout and RSVP apply them (routers/events.py); the rules live in services/registration.py."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.event import Event, EventAttendee
from app.models.organizer import (
    EventQuestion, PromoCode, RegistrationAnswer, TicketOrder, TicketTier,
)
from app.models.user import User
from app.routers.events import _require_event_access
from app.schemas.organizer import (
    PromoCheckOut, PromoCheckRequest, PromoCodeCreate, PromoCodeOut, PromoCodeUpdate,
    QuestionCreate, QuestionOut, QuestionUpdate, RegistrationRow, RegistrationsOut,
)
from app.services.registration import (
    QUESTION_KINDS, active_questions, display_answer, find_valid_promo, line_discounts,
    normalise_code,
)

router = APIRouter(prefix="/api/events", tags=["registration"])


# ── Promo codes (organizer) ─────────────────────────────────────────────────────────

async def _promo_out(db: AsyncSession, p: PromoCode) -> PromoCodeOut:
    given = (await db.execute(select(func.coalesce(func.sum(TicketOrder.discount_amount), 0)).where(
        TicketOrder.promo_code_id == p.id, TicketOrder.status == "confirmed",
    ))).scalar() or 0
    return PromoCodeOut(
        id=p.id, code=p.code, discount_type=p.discount_type, discount_value=p.discount_value,
        max_uses=p.max_uses, times_used=p.times_used, tier_ids=p.tier_ids,
        valid_from=p.valid_from, valid_until=p.valid_until, is_active=p.is_active,
        discount_given=round(float(given), 2), created_at=p.created_at,
    )


async def _get_promo(db: AsyncSession, event_id: str, promo_id: str) -> PromoCode:
    p = (await db.execute(select(PromoCode).where(
        PromoCode.id == promo_id, PromoCode.event_id == event_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Promo code not found")
    return p


@router.get("/{event_id}/promo-codes", response_model=list[PromoCodeOut])
async def list_promo_codes(event_id: str, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    await _require_event_access(event_id, user, db)
    rows = (await db.execute(select(PromoCode).where(PromoCode.event_id == event_id)
                             .order_by(PromoCode.created_at.desc()))).scalars().all()
    return [await _promo_out(db, p) for p in rows]


@router.post("/{event_id}/promo-codes", response_model=PromoCodeOut, status_code=201)
async def create_promo_code(event_id: str, payload: PromoCodeCreate,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    await _require_event_access(event_id, user, db)
    code = normalise_code(payload.code)
    if (await db.execute(select(PromoCode.id).where(
            PromoCode.event_id == event_id, PromoCode.code == code))).first():
        raise HTTPException(409, f"This event already has a code called {code}.")
    if payload.tier_ids:
        found = set((await db.execute(select(TicketTier.id).where(
            TicketTier.event_id == event_id, TicketTier.id.in_(payload.tier_ids)))).scalars().all())
        if found != set(payload.tier_ids):
            raise HTTPException(400, "Some of those ticket types aren't on this event.")
    if payload.valid_from and payload.valid_until and payload.valid_until <= payload.valid_from:
        raise HTTPException(400, "The end date must be after the start date.")
    p = PromoCode(id=str(uuid.uuid4()), event_id=event_id, code=code,
                  **payload.model_dump(exclude={"code"}))
    p.tier_ids = payload.tier_ids or None
    db.add(p)
    await db.flush()
    return await _promo_out(db, p)


@router.patch("/{event_id}/promo-codes/{promo_id}", response_model=PromoCodeOut)
async def update_promo_code(event_id: str, promo_id: str, payload: PromoCodeUpdate,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """Only limits and on/off can change: the discount itself is fixed once people may have used it."""
    await _require_event_access(event_id, user, db)
    p = await _get_promo(db, event_id, promo_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.flush()
    return await _promo_out(db, p)


@router.delete("/{event_id}/promo-codes/{promo_id}", status_code=204)
async def delete_promo_code(event_id: str, promo_id: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    await _require_event_access(event_id, user, db)
    p = await _get_promo(db, event_id, promo_id)
    if p.times_used > 0:
        raise HTTPException(409, "This code has been used, so it can't be deleted. Turn it off instead.")
    await db.delete(p)


# ── Promo code check (buyers) ──────────────────────────────────────────────────────

@router.post("/{event_id}/tickets/promo-check", response_model=PromoCheckOut)
@limiter.limit(settings.rate_limit_checkout)  # stops guessing codes
async def check_promo_code(request: Request, event_id: str, payload: PromoCheckRequest,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    promo = await find_valid_promo(db, event_id, payload.code)
    tiers = {t.id: t for t in (await db.execute(select(TicketTier).where(
        TicketTier.event_id == event_id,
        TicketTier.id.in_([i.tier_id for i in payload.items])))).scalars().all()}
    lines = [(tiers[i.tier_id], i.quantity) for i in payload.items if i.tier_id in tiers]
    if not lines:
        raise HTTPException(400, "Choose tickets first.")
    off = line_discounts(promo, lines)
    subtotal = round(sum(t.price * q for t, q in lines), 2)
    discount = round(sum(off), 2)
    if discount <= 0:
        raise HTTPException(400, "That promo code doesn't apply to the tickets you've chosen.")
    return PromoCheckOut(code=promo.code, discount_type=promo.discount_type,
                         discount_value=promo.discount_value, subtotal=subtotal,
                         discount=discount, total=round(subtotal - discount, 2))


# ── Registration questions ────────────────────────────────────────────────────────

@router.get("/{event_id}/questions", response_model=list[QuestionOut])
async def list_questions(event_id: str, db: AsyncSession = Depends(get_db)):
    """Public: the questions someone will be asked when registering."""
    return await active_questions(db, event_id)


@router.post("/{event_id}/questions", response_model=QuestionOut, status_code=201)
async def create_question(event_id: str, payload: QuestionCreate,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    await _require_event_access(event_id, user, db)
    if payload.kind not in QUESTION_KINDS:
        raise HTTPException(400, "Unknown question type")
    if payload.kind.endswith("_choice") and len(payload.options or []) < 2:
        raise HTTPException(400, "Give at least two choices.")
    current = await active_questions(db, event_id)
    if len(current) >= 20:
        raise HTTPException(400, "An event can have up to 20 questions.")
    q = EventQuestion(
        id=str(uuid.uuid4()), event_id=event_id, label=payload.label.strip(),
        help_text=(payload.help_text or "").strip() or None, kind=payload.kind,
        options=payload.options if payload.kind.endswith("_choice") else None,
        required=payload.required,
        position=payload.position if payload.position is not None
        else (max((x.position for x in current), default=-1) + 1),
    )
    db.add(q)
    await db.flush()
    return q


async def _get_question(db: AsyncSession, event_id: str, question_id: str) -> EventQuestion:
    q = (await db.execute(select(EventQuestion).where(
        EventQuestion.id == question_id, EventQuestion.event_id == event_id,
        EventQuestion.is_active == True))).scalar_one_or_none()  # noqa: E712
    if not q:
        raise HTTPException(404, "Question not found")
    return q


@router.patch("/{event_id}/questions/{question_id}", response_model=QuestionOut)
async def update_question(event_id: str, question_id: str, payload: QuestionUpdate,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    await _require_event_access(event_id, user, db)
    q = await _get_question(db, event_id, question_id)
    changes = payload.model_dump(exclude_unset=True)
    if "options" in changes:
        if not q.kind.endswith("_choice"):
            changes.pop("options")
        elif len(changes["options"] or []) < 2:
            raise HTTPException(400, "Give at least two choices.")
    for k, v in changes.items():
        setattr(q, k, v)
    await db.flush()
    return q


@router.delete("/{event_id}/questions/{question_id}", status_code=204)
async def delete_question(event_id: str, question_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Removes the question from the form. Answers already given are kept (the question is
    hidden, not deleted) so the organizer doesn't lose them."""
    await _require_event_access(event_id, user, db)
    q = await _get_question(db, event_id, question_id)
    has_answers = (await db.execute(select(RegistrationAnswer.id).where(
        RegistrationAnswer.question_id == q.id).limit(1))).first()
    if has_answers:
        q.is_active = False
    else:
        await db.delete(q)


@router.get("/{event_id}/registrations", response_model=RegistrationsOut)
async def list_registrations(event_id: str, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """Everyone registered (a confirmed ticket, or RSVP'd going) with their answers.
    Answers from people who started a checkout but never paid aren't shown."""
    await _require_event_access(event_id, user, db)
    questions = list((await db.execute(select(EventQuestion).where(
        EventQuestion.event_id == event_id).order_by(
        EventQuestion.is_active.desc(), EventQuestion.position, EventQuestion.created_at))).scalars().all())
    ticket_holders = set((await db.execute(select(TicketOrder.user_id).where(
        TicketOrder.event_id == event_id, TicketOrder.status == "confirmed"))).scalars().all())
    going = set((await db.execute(select(EventAttendee.user_id).where(
        EventAttendee.event_id == event_id, EventAttendee.status == "going"))).scalars().all())
    registered = ticket_holders | going
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    registered.discard(event.host_id)

    answers = (await db.execute(select(RegistrationAnswer).where(
        RegistrationAnswer.event_id == event_id))).scalars().all()
    q_by_id = {q.id: q for q in questions}
    by_user: dict[str, dict] = {}
    latest: dict[str, object] = {}
    for a in answers:
        if a.user_id not in registered:
            continue
        by_user.setdefault(a.user_id, {})[a.question_id] = display_answer(q_by_id.get(a.question_id), a.answer)
        if a.user_id not in latest or a.updated_at > latest[a.user_id]:
            latest[a.user_id] = a.updated_at

    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(registered)))).scalars().all()} \
        if registered else {}
    rows = [
        RegistrationRow(
            user_id=uid, name=u.display_name or u.full_name or u.username or "",
            username=u.username, email=u.email,
            status="ticket" if uid in ticket_holders else "going",
            answers=by_user.get(uid, {}), answered_at=latest.get(uid),
        )
        for uid, u in users.items()
    ]
    rows.sort(key=lambda r: (r.answered_at is None, r.name.lower()))
    return RegistrationsOut(
        questions=[QuestionOut.model_validate(q) for q in questions if q.is_active or any(
            q.id in r.answers for r in rows)],
        rows=rows,
    )
