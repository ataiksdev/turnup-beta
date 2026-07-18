import logging
from app.config import settings

logger = logging.getLogger(__name__)

# ── HTML helpers ──────────────────────────────────────────────────────────────

def _base(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{{font-family:sans-serif;background:#09090B;color:#FAFAFA;margin:0;padding:40px 20px}}
  .card{{max-width:480px;margin:auto;background:#18181B;border-radius:12px;padding:36px}}
  h2{{color:#F97316;margin:0 0 16px}}
  p{{color:#A1A1AA;line-height:1.6;margin:0 0 20px}}
  a.btn{{display:inline-block;background:#F97316;color:#fff;text-decoration:none;
         padding:12px 28px;border-radius:8px;font-weight:600}}
  .footer{{margin-top:24px;font-size:12px;color:#52525B}}
</style></head>
<body><div class="card">
  <h2>Turnup 🎉</h2>
  <h3 style="color:#FAFAFA;margin:0 0 16px">{title}</h3>
  {body}
  <div class="footer">If you didn't request this, you can safely ignore this email.</div>
</div></body></html>"""


def _verify_html(url: str) -> str:
    return _base("Verify your email", f"""
<p>Thanks for joining Turnup! Click below to verify your email address.</p>
<a class="btn" href="{url}">Verify Email</a>
<p style="margin-top:16px">Link expires in 24 hours.</p>""")


def _reset_html(url: str) -> str:
    return _base("Reset your password", f"""
<p>We received a request to reset your Turnup password. Click below to set a new one.</p>
<a class="btn" href="{url}">Reset Password</a>
<p style="margin-top:16px">Link expires in 1 hour.</p>""")


def _magic_html(url: str) -> str:
    return _base("Your magic login link", f"""
<p>Click below to sign in to Turnup instantly — no password needed.</p>
<a class="btn" href="{url}">Sign In</a>
<p style="margin-top:16px">Link expires in 15 minutes and can only be used once.</p>""")


def _ticket_html(
    event_title: str,
    event_date: str,
    event_venue: str,
    event_address: str,
    tier_name: str,
    quantity: int,
    total_price: float,
    ticket_code: str,
    ticket_url: str,
) -> str:
    price_line = "Free" if total_price == 0 else f"₦{total_price:,.0f}"
    return _base(f"Your ticket: {event_title}", f"""
<p>You're going! Here are your ticket details.</p>
<table style="width:100%;border-collapse:collapse;margin-bottom:20px">
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Event</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px">{event_title}</td></tr>
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Date</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px">{event_date}</td></tr>
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Venue</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px">{event_venue}</td></tr>
  {"" if not event_address else f'<tr><td style="padding:6px 0;color:#71717A;font-size:13px">Address</td><td style="padding:6px 0;font-size:13px">{event_address}</td></tr>'}
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Ticket</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px">{tier_name} × {quantity}</td></tr>
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Total</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px">{price_line}</td></tr>
  <tr><td style="padding:6px 0;color:#71717A;font-size:13px">Order ID</td>
      <td style="padding:6px 0;font-family:monospace;font-size:12px;color:#A1A1AA">{ticket_code[:8].upper()}</td></tr>
</table>
<a class="btn" href="{ticket_url}">View Ticket &amp; QR Code</a>
<p style="margin-top:20px;font-size:12px">Show the QR code at the door for entry.</p>""")


# ── Send logic ────────────────────────────────────────────────────────────────

async def _send(to: str, subject: str, html: str) -> None:
    if settings.email_console:
        logger.info("\n" + "="*60)
        logger.info(f"TO: {to}")
        logger.info(f"SUBJECT: {subject}")
        logger.info("BODY (HTML omitted in console mode)")
        # Print plain text version of the link for dev convenience
        import re
        links = re.findall(r'href="([^"]+)"', html)
        for link in links:
            if "token" in link or "verify" in link or "reset" in link or "magic" in link:
                logger.info(f"LINK: {link}")
        logger.info("="*60 + "\n")
        # Also print to stdout so it shows in uvicorn output
        print(f"\n[EMAIL] To: {to} | Subject: {subject}")
        for link in links:
            if any(k in link for k in ("token", "verify", "reset", "magic")):
                print(f"[EMAIL] Link: {link}")
        return

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_tls,
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def send_verification_email(to: str, token: str) -> None:
    url = f"{settings.frontend_url}/verify-email?token={token}"
    await _send(to, "Verify your Turnup email", _verify_html(url))


async def send_password_reset_email(to: str, token: str) -> None:
    url = f"{settings.frontend_url}/reset-password?token={token}"
    await _send(to, "Reset your Turnup password", _reset_html(url))


async def send_magic_link_email(to: str, token: str) -> None:
    url = f"{settings.frontend_url}/auth/magic?token={token}"
    await _send(to, "Your Turnup magic link", _magic_html(url))


async def send_ticket_email(
    to: str,
    order_id: str,
    ticket_code: str,
    event_title: str,
    event_date,
    event_venue: str | None,
    event_address: str | None,
    tier_name: str,
    quantity: int,
    total_price: float,
) -> None:
    if not to:
        return
    from datetime import datetime
    date_str = ""
    if event_date:
        try:
            if isinstance(event_date, str):
                event_date = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
            date_str = event_date.strftime("%a, %b %-d · %-I:%M %p")
        except Exception:
            date_str = str(event_date)

    ticket_url = f"{settings.frontend_url}/tickets/{order_id}"
    html = _ticket_html(
        event_title=event_title or "Event",
        event_date=date_str,
        event_venue=event_venue or "See event page",
        event_address=event_address or "",
        tier_name=tier_name,
        quantity=quantity,
        total_price=total_price,
        ticket_code=ticket_code,
        ticket_url=ticket_url,
    )
    await _send(to, f"Your ticket for {event_title}", html)
