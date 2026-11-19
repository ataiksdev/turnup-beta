"""Card chargebacks on venue payments (docs/venues-spec.md 4.12).

Turnup is the merchant on Paystack, so a chargeback lands on Turnup's account. Turnup
contests it with the booking records; one it loses on a venue payment goes on the venue's
ledger (the venue terms make the venue liable for chargebacks on its bookings).
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.venue import Chargeback, Venue, VenueLedgerEntry, VenuePayment
from app.services.venue_access import notify, notify_venue_team
from app.services.venue_money import naira, utcnow

logger = logging.getLogger(__name__)


async def record_dispute_event(db: AsyncSession, event: str, data: dict) -> str:
    """Paystack charge.dispute.create / .remind / .resolve."""
    dispute_id = str(data.get("id") or "")
    tx = data.get("transaction") or {}
    reference = tx.get("reference") if isinstance(tx, dict) else None
    if not dispute_id:
        return "ignored"
    cb = (await db.execute(select(Chargeback).where(Chargeback.paystack_dispute_id == dispute_id))).scalar_one_or_none()
    payment = (await db.execute(select(VenuePayment).where(
        VenuePayment.reference == reference))).scalar_one_or_none() if reference else None
    if not cb:
        amount = data.get("refund_amount") or (tx.get("amount") if isinstance(tx, dict) else 0) or 0
        cb = Chargeback(paystack_dispute_id=dispute_id, reference=reference, amount_kobo=int(amount),
                        payment_id=payment.id if payment else None, venue_id=payment.venue_id if payment else None)
        db.add(cb)
        await db.flush()
        for aid in (await db.execute(select(User.id).where(User.role == "admin"))).scalars().all():
            notify(db, aid, "chargeback_opened", f"Chargeback opened on {reference or 'a payment'}",
                   "Answer it in Paystack with the booking records.", reference_id=cb.id, reference_type="chargeback")
    if event == "charge.dispute.resolve":
        resolution = str(data.get("resolution") or "").lower()
        # Paystack: "merchant-accepted" / "auto-accepted" mean the customer got the money back;
        # "declined" means Turnup won. Anything else is left open for an admin to decide.
        if resolution in ("merchant-accepted", "auto-accepted"):
            await resolve_chargeback(db, cb, "lost")
        elif resolution == "declined":
            await resolve_chargeback(db, cb, "won")
    return "ok"


async def resolve_chargeback(db: AsyncSession, cb: Chargeback, status: str) -> None:
    if cb.status != "open":
        return
    cb.status = status
    cb.resolved_at = utcnow()
    if status == "lost" and cb.venue_id and cb.amount_kobo > 0:
        entry = VenueLedgerEntry(venue_id=cb.venue_id, kind="chargeback", amount_kobo=cb.amount_kobo,
                                 payment_reference=cb.reference,
                                 note="Card chargeback lost on a payment to this venue")
        db.add(entry)
        await db.flush()
        cb.ledger_entry_id = entry.id
        venue = (await db.execute(select(Venue).where(Venue.id == cb.venue_id))).scalar_one()
        await notify_venue_team(db, venue.id, "venue_chargeback",
                                f"A chargeback of {naira(cb.amount_kobo)} was added to your balance",
                                "It's taken from your next payouts, or pay it from the portal.",
                                reference_id=cb.id, reference_type="chargeback")
    await db.flush()
