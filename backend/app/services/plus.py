"""Subscriptions: Turnup+ (attendees) and Venue Pro (venues), billed by Paystack Plans
(docs/venues-spec.md 4.8, 4.9).

The current state is cached on users.plus_until / venues.pro_until so every perk check is a
column read. Paystack drives the lifecycle through webhooks; see handle_subscription_event.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.venue import Subscription, SubscriptionPlan, Venue
from app.services.settings import get_platform_settings

logger = logging.getLogger(__name__)

DEFAULT_PLANS = [
    # code, product, name, kobo, interval
    ("turnup_plus_monthly", "turnup_plus", "Turnup+ monthly", 150_000, "monthly"),
    ("turnup_plus_annually", "turnup_plus", "Turnup+ yearly", 1_500_000, "annually"),
    ("venue_pro_monthly", "venue_pro", "Venue Pro monthly", 1_500_000, "monthly"),
    ("venue_pro_annually", "venue_pro", "Venue Pro yearly", 15_000_000, "annually"),
]
LIVE_STATUSES = ("active", "non_renewing", "past_due")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def ensure_plans(db: AsyncSession) -> None:
    existing = set((await db.execute(select(SubscriptionPlan.code))).scalars().all())
    for code, product, name, kobo, interval in DEFAULT_PLANS:
        if code not in existing:
            db.add(SubscriptionPlan(code=code, product=product, name=name, amount_kobo=kobo, interval=interval))
    await db.flush()


def is_plus(user: User | None) -> bool:
    return bool(user and user.plus_until and _utc(user.plus_until) > utcnow())


def is_pro(venue: Venue) -> bool:
    return bool(venue.pro_until and _utc(venue.pro_until) > utcnow())


def period_length(interval: str) -> timedelta:
    return timedelta(days=366 if interval == "annually" else 31)


async def refresh_cached(db: AsyncSession, sub: Subscription) -> None:
    """Recompute plus_until / pro_until from every live subscription of that owner."""
    q = select(Subscription).where(Subscription.product == sub.product, Subscription.status.in_(LIVE_STATUSES))
    q = q.where(Subscription.venue_id == sub.venue_id) if sub.product == "venue_pro" else q.where(
        Subscription.user_id == sub.user_id)
    until = None
    for s in (await db.execute(q)).scalars().all():
        end = _utc(s.grace_until) if s.status == "past_due" and s.grace_until else _utc(s.current_period_end)
        if end and (until is None or end > until):
            until = end
    if sub.product == "venue_pro":
        venue = (await db.execute(select(Venue).where(Venue.id == sub.venue_id))).scalar_one()
        venue.pro_until = until
        venue.is_pro = bool(until and until > utcnow())
    else:
        user = (await db.execute(select(User).where(User.id == sub.user_id))).scalar_one()
        user.plus_until = until
    await db.flush()


async def plan_code_for(db: AsyncSession, plan: SubscriptionPlan) -> str:
    from app.services.paystack import create_plan
    if not plan.paystack_plan_code:
        plan.paystack_plan_code = await create_plan(plan.name, plan.amount_kobo, plan.interval)
        await db.flush()
    return plan.paystack_plan_code


async def start_subscription(db: AsyncSession, *, user: User, plan_code: str,
                             venue: Venue | None = None, callback_url: str | None = None) -> tuple[Subscription, str]:
    from app.services.paystack import PaystackConfigError, initialize_transaction
    from app.services.venue_money import new_reference

    plan = (await db.execute(select(SubscriptionPlan).where(
        SubscriptionPlan.code == plan_code, SubscriptionPlan.is_active == True))).scalar_one_or_none()  # noqa: E712
    if not plan:
        raise HTTPException(404, "That plan isn't available.")
    if (plan.product == "venue_pro") != (venue is not None):
        raise HTTPException(400, "That plan doesn't apply here.")
    q = select(Subscription).where(Subscription.product == plan.product, Subscription.status.in_(["active", "past_due"]))
    q = q.where(Subscription.venue_id == venue.id) if venue else q.where(Subscription.user_id == user.id)
    if (await db.execute(q)).first():
        raise HTTPException(409, "There's already an active subscription.")
    sub = Subscription(plan_code=plan.code, product=plan.product, user_id=user.id,
                       venue_id=venue.id if venue else None, reference=new_reference("sub"))
    db.add(sub)
    await db.flush()
    try:
        init = await initialize_transaction(
            email=user.email or f"{user.username}@users.turnup.app", amount_kobo=plan.amount_kobo,
            reference=sub.reference, metadata={"purpose": plan.product, "subscription_id": sub.id},
            plan=await plan_code_for(db, plan), callback_url=callback_url,
        )
    except PaystackConfigError as e:
        raise HTTPException(503, str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Paystack init failed for subscription %s", sub.reference)
        raise HTTPException(502, "Couldn't start the payment. Please try again.")
    return sub, init["data"]["authorization_url"]


async def activate_first_payment(db: AsyncSession, reference: str, ps_data: dict) -> Subscription | None:
    """charge.success (or verify) for our own sub_ reference: the first period is paid."""
    sub = (await db.execute(select(Subscription).where(Subscription.reference == reference))).scalar_one_or_none()
    if not sub or sub.status != "pending":
        return sub
    plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == sub.plan_code))).scalar_one()
    if not ps_data.get("mock"):
        try:
            if int(ps_data.get("amount")) != plan.amount_kobo:
                logger.warning("Subscription %s paid the wrong amount", reference)
                return sub
        except (TypeError, ValueError):
            return sub
    sub.status = "active"
    sub.current_period_end = utcnow() + period_length(plan.interval)
    customer = ps_data.get("customer") or {}
    if isinstance(customer, dict):
        sub.paystack_customer_code = customer.get("customer_code") or sub.paystack_customer_code
    await refresh_cached(db, sub)
    return sub


async def _find_by_paystack(db: AsyncSession, data: dict) -> Subscription | None:
    code = data.get("subscription_code") or (data.get("subscription") or {}).get("subscription_code")
    if code:
        sub = (await db.execute(select(Subscription).where(
            Subscription.paystack_subscription_code == code))).scalar_one_or_none()
        if sub:
            return sub
    # subscription.create: link it to our newest active subscription for that customer + plan.
    plan_code = (data.get("plan") or {}).get("plan_code")
    customer = data.get("customer") or {}
    plan = (await db.execute(select(SubscriptionPlan).where(
        SubscriptionPlan.paystack_plan_code == plan_code))).scalar_one_or_none() if plan_code else None
    if not plan:
        return None
    q = select(Subscription).where(Subscription.plan_code == plan.code,
                                   Subscription.status.in_(["pending", *LIVE_STATUSES]))
    if customer.get("customer_code"):
        q = q.where(Subscription.paystack_customer_code == customer["customer_code"])
    elif customer.get("email"):
        user_ids = (await db.execute(select(User.id).where(User.email == customer["email"]))).scalars().all()
        q = q.where(Subscription.user_id.in_(user_ids))
    else:
        return None
    return (await db.execute(q.order_by(Subscription.created_at.desc()))).scalars().first()


async def handle_subscription_event(db: AsyncSession, event: str, data: dict) -> str:
    sub = await _find_by_paystack(db, data)
    if not sub:
        return "unknown_subscription"
    ps = await get_platform_settings(db)
    next_date = data.get("next_payment_date") or (data.get("subscription") or {}).get("next_payment_date")
    if event == "subscription.create":
        sub.paystack_subscription_code = data.get("subscription_code")
        sub.paystack_email_token = data.get("email_token")
        if next_date:
            sub.current_period_end = _parse(next_date) or sub.current_period_end
    elif event in ("invoice.update", "charge.success") and data.get("paid", True):
        sub.status = "active" if sub.status != "non_renewing" else sub.status
        sub.grace_until = None
        parsed = _parse(next_date) if next_date else None
        plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == sub.plan_code))).scalar_one()
        sub.current_period_end = parsed or (utcnow() + period_length(plan.interval))
    elif event == "invoice.payment_failed":
        sub.status = "past_due"
        sub.grace_until = utcnow() + timedelta(days=ps.subscription_grace_days)
    elif event == "subscription.not_renew":
        sub.status = "non_renewing"
    elif event == "subscription.disable":
        sub.status = "cancelled"
        sub.cancelled_at = utcnow()
    else:
        return "ignored"
    await refresh_cached(db, sub)
    return "ok"


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


async def cancel_subscription(db: AsyncSession, sub: Subscription) -> Subscription:
    """Stops renewal; perks last until the end of the paid period."""
    from app.services.paystack import disable_subscription
    if sub.status not in ("active", "past_due"):
        raise HTTPException(409, "This subscription isn't active.")
    if sub.paystack_subscription_code and sub.paystack_email_token:
        try:
            await disable_subscription(sub.paystack_subscription_code, sub.paystack_email_token)
        except Exception:
            logger.exception("Paystack disable failed for %s", sub.paystack_subscription_code)
            raise HTTPException(502, "Couldn't reach the payment provider. Please try again.")
    sub.status = "non_renewing"
    sub.cancelled_at = utcnow()
    await refresh_cached(db, sub)
    return sub


async def expire_lapsed(db: AsyncSession) -> int:
    """Mark subscriptions whose paid period (and grace) is over as cancelled."""
    now = utcnow()
    n = 0
    for sub in (await db.execute(select(Subscription).where(Subscription.status.in_(LIVE_STATUSES)))).scalars().all():
        end = _utc(sub.grace_until) if sub.status == "past_due" and sub.grace_until else _utc(sub.current_period_end)
        if end and end < now:
            sub.status = "cancelled"
            await refresh_cached(db, sub)
            n += 1
    # Abandoned checkouts.
    for sub in (await db.execute(select(Subscription).where(
            Subscription.status == "pending", Subscription.created_at < now - timedelta(days=1)))).scalars().all():
        sub.status = "cancelled"
    await db.commit()
    return n
