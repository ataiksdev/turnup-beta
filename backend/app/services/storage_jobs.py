"""Storage housekeeping, run by the worker:

- prune_orphan_uploads (weekly): deletes public uploads nothing in the database points to any
  more (replaced covers, deleted venue photos...), once they're older than
  ORPHAN_UPLOAD_GRACE_DAYS so a file uploaded into a form that isn't saved yet is never lost.
- offsite_backup (nightly): encrypts the newest database dump and an archive of the KYC files
  with BACKUP_PASSPHRASE and copies both to BACKUP_S3_BUCKET; deletes copies older than
  OFFSITE_KEEP_DAYS. Decrypt with `python -m app.cli decrypt-backup <in> <out>`.

Encrypted file format (streamed, so large archives never sit in memory):
  b"TUPBAK1" | 16-byte salt | repeated [4-byte big-endian length | 12-byte nonce | AES-256-GCM
  ciphertext+tag] | final chunk of length 0. The key is scrypt(passphrase, salt). Each chunk's
  nonce is random and its index is authenticated, so chunks can't be reordered or dropped.
"""
import asyncio
import logging
import os
import struct
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Enum, String, Text, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Base
from app.services import storage

logger = logging.getLogger(__name__)

MAGIC = b"TUPBAK1"
CHUNK = 1024 * 1024


# ── Unused uploads ─────────────────────────────────────────────────────────────

async def referenced_names(db: AsyncSession) -> set[str]:
    """Every upload name mentioned anywhere in the database (any text column)."""
    names: set[str] = set()
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if not isinstance(col.type, (String, Text)) or isinstance(col.type, Enum):
                continue
            q = select(col).where(or_(*[col.like(f"%.{ext}%") for ext in storage.CONTENT_TYPES]))
            for (value,) in (await db.execute(q)).all():
                names.update(storage.NAME.findall(value or ""))
    return names


async def prune_orphan_uploads(db: AsyncSession, dry_run: bool = False) -> dict:
    keep = await referenced_names(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.orphan_upload_grace_days)
    files = await asyncio.to_thread(storage.list_files)
    orphans = [n for n, modified in files if n not in keep and modified < cutoff]
    if not dry_run:
        for n in orphans:
            await asyncio.to_thread(storage.delete, n)
    out = {"files": len(files), "referenced": len(keep), "deleted" if not dry_run else "would_delete": len(orphans)}
    logger.info("Unused uploads: %s", out)
    return out


# ── Encryption ─────────────────────────────────────────────────────────────────

def _key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def encrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(passphrase) < 16:
        raise ValueError("BACKUP_PASSPHRASE must be at least 16 characters")
    salt = os.urandom(16)
    aead = AESGCM(_key(passphrase, salt))
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC + salt)
        index = 0
        while True:
            block = fin.read(CHUNK)
            nonce = os.urandom(12)
            # The chunk index and a "last" flag are authenticated: truncation is detected.
            aad = struct.pack(">Q?", index, not block)
            ct = aead.encrypt(nonce, block, aad)
            fout.write(struct.pack(">I", len(ct)) + nonce + ct)
            if not block:
                break
            index += 1


def decrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        if fin.read(len(MAGIC)) != MAGIC:
            raise ValueError("Not a Turnup backup file")
        aead = AESGCM(_key(passphrase, fin.read(16)))
        index = 0
        while True:
            header = fin.read(16)
            if len(header) < 16:
                raise ValueError("The backup file is truncated")
            (length,), nonce = struct.unpack(">I", header[:4]), header[4:]
            ct = fin.read(length)
            # An empty final chunk encrypts to just its 16-byte tag.
            last = length == 16
            block = aead.decrypt(nonce, ct, struct.pack(">Q?", index, last))
            if last:
                return
            fout.write(block)
            index += 1


# ── Off-server backups ─────────────────────────────────────────────────────────

def _offsite_ready() -> bool:
    return bool(settings.backup_s3_bucket and settings.backup_passphrase and settings.s3_access_key_id)


def _upload_backup(path: Path, key: str) -> None:
    storage.s3_client().upload_file(str(path), settings.backup_s3_bucket, key,
                                    ExtraArgs={"ContentType": "application/octet-stream"})


def _existing_keys() -> list[tuple[str, datetime]]:
    client, token, out = storage.s3_client(), None, []
    while True:
        kw = {"Bucket": settings.backup_s3_bucket}
        if token:
            kw["ContinuationToken"] = token
        page = client.list_objects_v2(**kw)
        out += [(o["Key"], o["LastModified"]) for o in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return out
        token = page.get("NextContinuationToken")


def run_offsite_backup_sync(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not _offsite_ready():
        return {"skipped": "BACKUP_S3_BUCKET, BACKUP_PASSPHRASE and S3 credentials are not all set"}
    day = now.strftime("%Y-%m-%d")
    existing = dict(_existing_keys())
    out: dict = {"uploaded": []}
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Newest database dump made by the backup service.
        dumps = sorted(Path(settings.backup_dir).glob("turnup-*.sql.gz")) if Path(settings.backup_dir).is_dir() else []
        if dumps:
            key = f"db/{dumps[-1].name}.enc"
            if key not in existing:
                enc = Path(tmp) / "db.enc"
                encrypt_file(dumps[-1], enc, settings.backup_passphrase)
                _upload_backup(enc, key)
                out["uploaded"].append(key)
        else:
            out["db"] = "no dump found in BACKUP_DIR"
        # 2. KYC files (only those still within retention exist on disk).
        kyc = Path(settings.kyc_dir)
        key = f"kyc/kyc-{day}.tar.gz.enc"
        if kyc.is_dir() and key not in existing:
            archive = Path(tmp) / "kyc.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for f in sorted(kyc.iterdir()):
                    if f.is_file():
                        tar.add(f, arcname=f.name)
            enc = Path(tmp) / "kyc.enc"
            encrypt_file(archive, enc, settings.backup_passphrase)
            _upload_backup(enc, key)
            out["uploaded"].append(key)
    # 3. Retention.
    cutoff = now - timedelta(days=settings.offsite_keep_days)
    old = [k for k, modified in existing.items() if modified < cutoff and k.endswith(".enc")]
    for k in old:
        storage.s3_client().delete_object(Bucket=settings.backup_s3_bucket, Key=k)
    out["deleted"] = old
    logger.info("Off-server backup: %s", out)
    return out


async def offsite_backup(db: AsyncSession | None = None) -> dict:
    return await asyncio.to_thread(run_offsite_backup_sync)
