"""Where public uploads live: local disk or an S3-compatible bucket.

STORAGE_BACKEND=local (default): files in UPLOAD_DIR, served by GET /api/uploads/<name>.
STORAGE_BACKEND=s3: files in S3_BUCKET, linked at S3_PUBLIC_BASE_URL/<name> (the bucket's
public address, e.g. a Cloudflare R2 custom domain or r2.dev URL, or a Supabase Storage public
bucket URL). /api/uploads/<name> then redirects there, so links made before the switch work.

Names are always "<32 hex>.<ext>" and never change, so files can be cached forever.
"""
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

NAME = re.compile(r"[0-9a-f]{32}\.(?:webp|jpg|mp4|webm)")
CONTENT_TYPES = {"webp": "image/webp", "jpg": "image/jpeg", "mp4": "video/mp4", "webm": "video/webm"}

_client = None


def s3_enabled() -> bool:
    return settings.storage_backend == "s3"


def s3_client():
    """boto3 client for the configured S3-compatible service (shared by backups)."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None, region_name=settings.s3_region or "auto",
            aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}, signature_version="s3v4"),
        )
    return _client


def upload_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def api_url(name: str) -> str:
    base = (settings.public_base_url or settings.frontend_url).rstrip("/")
    return f"{base}/api/uploads/{name}"


def public_url(name: str) -> str:
    if s3_enabled():
        return f"{settings.s3_public_base_url.rstrip('/')}/{name}"
    return api_url(name)


async def save(name: str, data: bytes) -> str:
    """Store a public file; returns its public URL."""
    if s3_enabled():
        ext = name.rsplit(".", 1)[1]
        await asyncio.to_thread(
            s3_client().put_object, Bucket=settings.s3_bucket, Key=name, Body=data,
            ContentType=CONTENT_TYPES[ext], CacheControl="public, max-age=31536000, immutable")
    else:
        (upload_dir() / name).write_bytes(data)
    return public_url(name)


def list_files() -> list[tuple[str, datetime]]:
    """(name, last modified) of every stored public file."""
    out: list[tuple[str, datetime]] = []
    if s3_enabled():
        client, token = s3_client(), None
        while True:
            kw = {"Bucket": settings.s3_bucket}
            if token:
                kw["ContinuationToken"] = token
            page = client.list_objects_v2(**kw)
            for obj in page.get("Contents", []):
                if NAME.fullmatch(obj["Key"]):
                    out.append((obj["Key"], obj["LastModified"]))
            if not page.get("IsTruncated"):
                return out
            token = page.get("NextContinuationToken")
    for p in upload_dir().iterdir():
        if p.is_file() and NAME.fullmatch(p.name):
            out.append((p.name, datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)))
    return out


def delete(name: str) -> None:
    if s3_enabled():
        s3_client().delete_object(Bucket=settings.s3_bucket, Key=name)
    else:
        (upload_dir() / name).unlink(missing_ok=True)
