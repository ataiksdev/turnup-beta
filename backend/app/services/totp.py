import hashlib
import os
import secrets
import pyotp
import qrcode
import qrcode.image.svg
from io import BytesIO
from passlib.context import CryptContext

_backup_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "Turnup") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def get_qr_svg(uri: str) -> str:
    """Returns an SVG string for the provisioning URI QR code."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def verify_totp(secret: str, code: str) -> bool:
    """Accepts a 6-digit code; allows 1-step clock skew."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ── Backup codes ──────────────────────────────────────────────────────────────

def generate_backup_codes(count: int = 10) -> list[str]:
    """Returns plaintext codes in groups of 4 (e.g. 'ABCD-EFGH')."""
    return [
        "-".join([secrets.token_hex(2).upper() for _ in range(2)])
        for _ in range(count)
    ]


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [_backup_ctx.hash(c) for c in codes]


def verify_backup_code(plain: str, hashed_codes: list[str]) -> int | None:
    """Returns the index of the matched code, or None."""
    for i, hashed in enumerate(hashed_codes):
        if _backup_ctx.verify(plain.upper(), hashed):
            return i
    return None
