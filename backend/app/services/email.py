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
