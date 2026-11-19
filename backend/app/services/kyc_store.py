"""Private storage for venue verification files (docs/venues-spec.md 8.2).

Files live under KYC_DIR with random names and are never served by the public uploads route.
They're read through short-lived signed links (`signed_url`) that the API only hands out after
an access check, and every view is written to kyc_access_log by the caller.
"""
import hashlib
import hmac
import io
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES_DEFAULT = 100 * 1024 * 1024
LINK_TTL_SECONDS = 300

_VIDEO_SIGNATURES = (
    (4, b"ftyp", "video/mp4", "mp4"),        # MP4 / MOV (ISO base media)
    (0, b"\x1aE\xdf\xa3", "video/webm", "webm"),
)


def _dir() -> Path:
    path = Path(settings.kyc_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _image(raw: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Upload a JPEG, PNG or WebP image, or a PDF.")
            if probe.width * probe.height > 40_000_000:
                raise HTTPException(413, "That image's dimensions are too large.")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((2400, 2400))  # documents need to stay legible
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=88)
            return out.getvalue(), "image/webp", "webp"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "That file isn't a readable image.")


def detect_video(raw: bytes) -> tuple[str, str] | None:
    for offset, magic, ctype, ext in _VIDEO_SIGNATURES:
        if raw[offset:offset + len(magic)] == magic:
            return ctype, ext
    return None


def prepare(raw: bytes, *, allow_pdf: bool = True, allow_video: bool = False) -> tuple[bytes, str, str]:
    """Validate by content (never by extension) and return (bytes, content_type, ext)."""
    if not raw:
        raise HTTPException(400, "The file is empty.")
    if allow_video:
        video = detect_video(raw)
        if video:
            limit = settings.venue_video_max_mb * 1024 * 1024
            if len(raw) > limit:
                raise HTTPException(413, f"Videos can be up to {settings.venue_video_max_mb} MB.")
            return raw, video[0], video[1]
    if len(raw) > MAX_DOC_BYTES:
        raise HTTPException(413, "Documents can be up to 10 MB.")
    if raw.startswith(b"%PDF-"):
        if not allow_pdf:
            raise HTTPException(415, "Upload an image.")
        if b"/JavaScript" in raw or b"/JS" in raw or b"/Launch" in raw:
            raise HTTPException(415, "That PDF contains scripts. Export it again without them.")
        return raw, "application/pdf", "pdf"
    return _image(raw)


def save(data: bytes, ext: str) -> str:
    key = f"{uuid.uuid4().hex}.{ext}"
    (_dir() / key).write_bytes(data)
    return key


def read_path(key: str) -> Path:
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(404, "Not found")
    path = _dir() / key
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return path


def delete(key: str) -> None:
    try:
        read_path(key).unlink()
    except HTTPException:
        pass


def _sig(key: str, exp: int, user_id: str) -> str:
    msg = f"{key}|{exp}|{user_id}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()


def signed_url(key: str, user_id: str) -> str:
    exp = int(time.time()) + LINK_TTL_SECONDS
    return f"/api/kyc/files/{key}?u={user_id}&exp={exp}&sig={_sig(key, exp, user_id)}"


def check_signature(key: str, user_id: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    return hmac.compare_digest(_sig(key, exp, user_id), sig or "")


def identity_hash(value: str) -> str:
    """Hash for blocked-identity checks (CAC numbers, bank accounts): normalised + keyed."""
    norm = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    return hmac.new(settings.secret_key.encode(), norm.encode(), hashlib.sha256).hexdigest()
