"""Claim pack (docs/venues-spec.md 4.12): the records an organizer needs to pursue an unpaid
refund directly, once Turnup's enforcement period has ended. Built on demand, never stored."""
from datetime import datetime

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.venue import (
    EnquiryMessage, RefundRequest, Venue, VenueBooking, VenueDispute, VenueLedgerEntry, VenueMember,
    VenuePayment, VenueQuote, VenueSpace,
)
from app.services.venue_policy import PRESET_LABELS


def _ngn(kobo: int | None) -> str:
    return f"NGN {((kobo or 0) / 100):,.2f}"


def _d(dt: datetime | None) -> str:
    return dt.strftime("%d %b %Y %H:%M UTC") if dt else "-"


def _latin(text: str | None) -> str:
    """The built-in PDF fonts are Latin-1 only."""
    return (text or "").replace("₦", "NGN ").replace("’", "'").replace("“", '"').replace(
        "”", '"').replace("–", "-").replace("—", "-").encode("latin-1", "replace").decode("latin-1")


class _Pdf(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120)
        self.cell(0, 6, "Turnup - claim pack (confidential)", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


def _h(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _latin(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)


def _p(pdf: FPDF, text: str) -> None:
    pdf.multi_cell(0, 5, _latin(text), new_x="LMARGIN", new_y="NEXT")


def _row(pdf: FPDF, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(55, 6, _latin(label))
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _latin(value), new_x="LMARGIN", new_y="NEXT")


async def build_claim_pack(db: AsyncSession, rr: RefundRequest) -> bytes:
    booking = (await db.execute(select(VenueBooking).where(VenueBooking.id == rr.booking_id))).scalar_one()
    venue = (await db.execute(select(Venue).where(Venue.id == rr.venue_id))).scalar_one()
    organizer = (await db.execute(select(User).where(User.id == rr.organizer_id))).scalar_one()
    space = (await db.execute(select(VenueSpace).where(VenueSpace.id == booking.space_id))).scalar_one()
    quote = (await db.execute(select(VenueQuote).where(VenueQuote.id == booking.quote_id))).scalar_one()
    owner = (await db.execute(select(User).join(VenueMember, VenueMember.user_id == User.id).where(
        VenueMember.venue_id == venue.id, VenueMember.role == "owner"))).scalars().first()
    payments = (await db.execute(select(VenuePayment).where(
        VenuePayment.booking_id == booking.id, VenuePayment.status == "success").order_by(VenuePayment.paid_at))).scalars().all()
    funding = (await db.execute(select(VenuePayment).where(
        VenuePayment.refund_request_id == rr.id, VenuePayment.status == "success"))).scalars().all()
    ledger = (await db.execute(select(VenueLedgerEntry).where(
        VenueLedgerEntry.refund_request_id == rr.id).order_by(VenueLedgerEntry.created_at))).scalars().all()
    disputes = (await db.execute(select(VenueDispute).where(VenueDispute.booking_id == booking.id))).scalars().all()
    messages = (await db.execute(select(EnquiryMessage).where(
        EnquiryMessage.enquiry_id == booking.enquiry_id).order_by(EnquiryMessage.created_at))).scalars().all()

    pdf = _Pdf()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Unpaid venue refund: claim pack", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    _p(pdf, f"Generated {_d(datetime.utcnow())} for {organizer.full_name or organizer.username}. "
            "Turnup's enforcement period for this refund has ended. The refund is a debt the venue owes "
            "you under the booking terms you both accepted. This pack contains the records and the venue's "
            "verified legal details so you can pursue it directly.")

    _h(pdf, "1. Amount claimed")
    _row(pdf, "Refund owed", _ngn(rr.amount_kobo))
    _row(pdf, "Received so far", _ngn(rr.refunded_kobo))
    _row(pdf, "Outstanding", _ngn(rr.amount_kobo - rr.refunded_kobo))
    _row(pdf, "Reason", rr.reason.replace("_", " "))
    _row(pdf, "Requested", _d(rr.created_at))
    _row(pdf, "Venue deadline", _d(rr.due_at))
    _row(pdf, "Listing paused", _d(rr.paused_at))
    _row(pdf, "Listing suspended", _d(rr.suspended_at))
    _row(pdf, "Referred to you", _d(rr.referred_at))

    _h(pdf, "2. The venue (as verified by Turnup)")
    _row(pdf, "Registered business name", venue.legal_name or "-")
    _row(pdf, "CAC number", venue.cac_number or "-")
    _row(pdf, "Registered address", venue.registered_address or "-")
    _row(pdf, "Listed as", f"{venue.name}, {venue.address}, {venue.state}")
    _row(pdf, "Owner on Turnup", (owner.full_name or owner.username) if owner else "-")
    _row(pdf, "Payout account name", venue.bank_account_name or "-")

    _h(pdf, "3. The booking")
    _row(pdf, "Booking reference", booking.id)
    _row(pdf, "Space", space.name)
    _row(pdf, "Dates", f"{_d(booking.starts_at)} to {_d(booking.ends_at)}")
    _row(pdf, "Total price", _ngn(booking.total_kobo))
    _row(pdf, "Deposit", _ngn(booking.deposit_kobo))
    _row(pdf, "Refund policy", PRESET_LABELS.get(booking.refund_preset, booking.refund_preset))
    _row(pdf, "Quote accepted", _d(quote.created_at))
    _row(pdf, "Status", booking.status.replace("_", " "))
    _row(pdf, "Cancelled", f"{_d(booking.cancelled_at)} - {booking.cancel_reason or ''}")

    _h(pdf, "4. Payments made through Turnup")
    for p in payments:
        _row(pdf, f"{p.kind.title()} {_d(p.paid_at)}", f"{_ngn(p.amount_kobo)} (Paystack ref {p.reference}); "
                  f"refunded {_ngn(p.refunded_kobo)}")
    if funding:
        for p in funding:
            _row(pdf, f"Venue funding {_d(p.paid_at)}", f"{_ngn(p.amount_kobo)} (ref {p.reference})")
    for e in ledger:
        _row(pdf, f"Ledger {_d(e.created_at)}", f"{e.kind.replace('_', ' ')}: {_ngn(e.amount_kobo)} {e.note or ''}")

    if disputes:
        _h(pdf, "5. Disputes")
        for d in disputes:
            _row(pdf, f"Opened {_d(d.created_at)}", f"by {d.side}: {d.reason.replace('_', ' ')}. {d.description}")
            if d.resolution:
                _row(pdf, f"Decided {_d(d.resolved_at)}", f"{d.resolution}, {_ngn(d.refund_kobo)}. {d.decision_note or ''}")

    _h(pdf, "6. Message history")
    for m in messages:
        _p(pdf, f"[{_d(m.created_at)}] {m.sender_side}: {m.body}")

    _h(pdf, "7. Your options")
    _p(pdf, "- Send the venue a formal demand letter quoting this pack.\n"
            "- File in a small claims court where available (several states, including Lagos and the FCT, "
            "run small claims courts for claims within their monetary limit).\n"
            "- For a personal (consumer) booking, complain to the Federal Competition and Consumer "
            "Protection Commission (FCCPC).\n"
            "Turnup answers court orders and lawful requests with its records. Turnup is not a party to the "
            "booking contract and does not take part in the claim.")
    return bytes(pdf.output())
