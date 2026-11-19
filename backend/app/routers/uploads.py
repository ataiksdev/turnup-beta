"""Image uploads (event covers, avatars).

Every upload is decoded and re-encoded by Pillow before it's stored. That (1) proves the file
really is an image of an allowed type, whatever its extension or Content-Type claim,
(2) removes metadata such as EXIF GPS coordinates that phone photos carry, and (3) drops any
non-image payload hidden in the file (polyglots, SVG scripts: SVG isn't accepted at all).

Files are stored on local disk (UPLOAD_DIR) with random names and served from
/api/uploads/<name>. On a multi-server deployment, point UPLOAD_DIR at shared storage or
swap _store() for an object store (S3, Cloudinary...).
"""
import io
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.services import storage

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

MAX_BYTES = 8 * 1024 * 1024        # what we'll read from the client
MAX_PIXELS = 40_000_000            # refuse decompression bombs before decoding them fully
MAX_SIDE = 2000                    # stored images are scaled down to fit this box
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
_NAME = re.compile(r"^[0-9a-f]{32}\.(webp|jpg|mp4|webm)$")
_MEDIA_TYPES = {"webp": "image/webp", "jpg": "image/jpeg", "mp4": "video/mp4", "webm": "video/webm"}


def _upload_dir() -> Path:
    return storage.upload_dir()

# Stored files go through app/services/storage.py: local disk, or an S3-compatible bucket.
# URLs are absolute, so they also work inside the Android app (whose own origin is
# http://localhost) and in emails/link previews.


def _reencode(raw: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED_FORMATS:
                raise HTTPException(415, "Upload a JPEG, PNG, WebP or GIF image.")
            if probe.width * probe.height > MAX_PIXELS:
                raise HTTPException(413, "That image's dimensions are too large.")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)  # keep phone photos upright once EXIF is gone
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=82, method=4)  # no exif/metadata is written
            return out.getvalue(), "webp"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "That file isn't a readable image.")


@router.post("", status_code=201)
@limiter.limit(settings.rate_limit_upload)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    raw = await file.read(MAX_BYTES + 1)  # bounded read: never buffer more than the limit
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, f"Images can be up to {MAX_BYTES // (1024 * 1024)} MB.")
    if not raw:
        raise HTTPException(400, "The file is empty.")
    data, ext = _reencode(raw)
    return {"url": await storage.save(f"{uuid.uuid4().hex}.{ext}", data)}


@router.post("/video", status_code=201)
@limiter.limit("10/hour")
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Venue videos (docs/venues-spec.md 4.9). Checked by content, limited in size and length,
    and re-encoded to MP4 with ffmpeg (which also strips metadata and makes a poster image).
    Without ffmpeg the original MP4/WebM is stored as is."""
    from app.services.kyc_store import detect_video
    from app.services.video import process_video
    limit = settings.venue_video_max_mb * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, f"Videos can be up to {settings.venue_video_max_mb} MB.")
    kind = detect_video(raw)
    if not kind:
        raise HTTPException(415, "Upload an MP4, MOV or WebM video.")
    name = uuid.uuid4().hex
    video, ext, poster, duration = await process_video(raw, kind[1], settings.venue_video_max_seconds)
    url = await storage.save(f"{name}.{ext}", video)
    poster_url = None
    if poster:
        pdata, pext = _reencode(poster)
        poster_url = await storage.save(f"{uuid.uuid4().hex}.{pext}", pdata)
    return {"url": url, "poster_url": poster_url, "duration_s": duration}


@router.get("/{name}")
async def get_upload(name: str):
    if not _NAME.match(name):  # random names only: no paths, no traversal
        raise HTTPException(404, "Not found")
    path = _upload_dir() / name
    if storage.s3_enabled() and not path.is_file():
        # Files live in the bucket; links made before the move to object storage still work.
        return RedirectResponse(storage.public_url(name), status_code=301,
                                headers={"Cache-Control": "public, max-age=86400"})
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(
        path, media_type=_MEDIA_TYPES[name.rsplit(".", 1)[1]],
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",  # names never change
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
