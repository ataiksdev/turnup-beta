"""One-off move of existing local uploads into the bucket (`python -m app.cli
move-uploads-to-s3`), run once after switching STORAGE_BACKEND to s3.

Copies every file in UPLOAD_DIR to S3_BUCKET (skipping ones already there), then rewrites links
in the database from <PUBLIC_BASE_URL>/api/uploads/<name> to <S3_PUBLIC_BASE_URL>/<name>.
Old links keep working either way (/api/uploads/<name> redirects to the bucket), and the local
files are left in place: delete them once you've checked the site.
"""
import asyncio

from sqlalchemy import Enum, String, Text, update

from app.config import settings
from app.database import AsyncSessionLocal, Base
from app.services import storage


async def move_uploads_to_s3() -> dict:
    if not storage.s3_enabled():
        return {"error": "Set STORAGE_BACKEND=s3 and the S3_* settings first."}
    client = storage.s3_client()
    in_bucket = {n for n, _ in await asyncio.to_thread(storage.list_files)}
    copied = 0
    for path in sorted(storage.upload_dir().iterdir()):
        if not storage.NAME.fullmatch(path.name) or path.name in in_bucket:
            continue
        ext = path.name.rsplit(".", 1)[1]
        await asyncio.to_thread(
            client.put_object, Bucket=settings.s3_bucket, Key=path.name, Body=path.read_bytes(),
            ContentType=storage.CONTENT_TYPES[ext], CacheControl="public, max-age=31536000, immutable")
        copied += 1

    old_prefix = storage.api_url("")          # e.g. https://api.example.com/api/uploads/
    new_prefix = storage.public_url("")       # e.g. https://media.example.com/
    rewritten = 0
    async with AsyncSessionLocal() as db:
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                if isinstance(col.type, (String, Text)) and not isinstance(col.type, Enum):
                    from sqlalchemy import func
                    r = await db.execute(update(table).where(col.like(f"%{old_prefix}%")).values(
                        {col.name: func.replace(col, old_prefix, new_prefix)}))
                    rewritten += r.rowcount or 0
        await db.commit()
    return {"copied": copied, "already_in_bucket": len(in_bucket), "rows_rewritten": rewritten}
