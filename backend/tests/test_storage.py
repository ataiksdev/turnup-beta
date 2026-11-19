"""Object storage, encrypted off-server backups and unused-upload cleanup
(app/services/storage.py, storage_jobs.py, storage_migrate.py)."""
import gzip
import io
import os
import tarfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.models.event import Event
from app.models.user import User
from app.services import storage, storage_jobs
from tests.test_venues import _no_rate_limits, make_user  # noqa: F401


class FakeS3:
    """Just the boto3 calls the app makes, kept in memory."""

    def __init__(self):
        self.buckets: dict[str, dict[str, dict]] = {}

    def _b(self, bucket):
        return self.buckets.setdefault(bucket, {})

    def put_object(self, Bucket, Key, Body, **kw):
        self._b(Bucket)[Key] = {"Body": Body, "LastModified": datetime.now(timezone.utc), **kw}

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
        self.put_object(Bucket, Key, Path(Filename).read_bytes())

    def delete_object(self, Bucket, Key):
        self._b(Bucket).pop(Key, None)

    def list_objects_v2(self, Bucket, ContinuationToken=None):
        items = sorted(self._b(Bucket).items())
        start = int(ContinuationToken or 0)
        page = items[start:start + 2]  # tiny pages, so pagination is exercised
        more = start + 2 < len(items)
        return {"Contents": [{"Key": k, "LastModified": v["LastModified"]} for k, v in page],
                "IsTruncated": more, **({"NextContinuationToken": str(start + 2)} if more else {})}


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "_client", fake)
    monkeypatch.setattr(settings, "s3_access_key_id", "test")
    monkeypatch.setattr(settings, "s3_bucket", "uploads")
    monkeypatch.setattr(settings, "s3_public_base_url", "https://media.example.com")
    return fake


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (30, 20), (10, 120, 200)).save(out, format="PNG")
    return out.getvalue()


# ── Encryption ─────────────────────────────────────────────────────────────────

def test_encrypt_round_trip_and_tamper_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_jobs, "CHUNK", 1000)  # several chunks
    src, enc, out = tmp_path / "in", tmp_path / "enc", tmp_path / "out"
    data = os.urandom(3500)
    src.write_bytes(data)
    storage_jobs.encrypt_file(src, enc, "a long passphrase 123")
    assert data not in enc.read_bytes()
    storage_jobs.decrypt_file(enc, out, "a long passphrase 123")
    assert out.read_bytes() == data
    with pytest.raises(Exception):
        storage_jobs.decrypt_file(enc, out, "the wrong passphrase!")
    blob = enc.read_bytes()
    (tmp_path / "cut").write_bytes(blob[:-40])  # truncated: final chunk missing
    with pytest.raises(Exception):
        storage_jobs.decrypt_file(tmp_path / "cut", out, "a long passphrase 123")
    with pytest.raises(ValueError):
        storage_jobs.encrypt_file(src, enc, "short")


# ── Uploads to the bucket ──────────────────────────────────────────────────────

async def test_uploads_go_to_bucket_and_old_links_redirect(client, db, s3, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    h, _ = await make_user(db)
    r = await client.post("/api/uploads", headers=h, files={"file": ("a.png", png(), "image/png")})
    assert r.status_code == 201
    url = r.json()["url"]
    name = url.rsplit("/", 1)[1]
    assert url == f"https://media.example.com/{name}"
    obj = s3.buckets["uploads"][name]
    assert obj["ContentType"] == "image/webp" and "immutable" in obj["CacheControl"]
    r = await client.get(f"/api/uploads/{name}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == url


async def test_move_local_uploads_to_bucket(db, s3, monkeypatch):
    from app.services import storage_migrate
    name = f"{uuid.uuid4().hex}.webp"
    storage.upload_dir().joinpath(name).write_bytes(b"img")
    _, uid = await make_user(db)
    old = storage.api_url(name)
    user = await db.get(User, uid)
    user.avatar_url = old
    await db.commit()
    monkeypatch.setattr(settings, "storage_backend", "s3")
    # The migration opens its own session; point it at the test database.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    monkeypatch.setattr(storage_migrate, "AsyncSessionLocal", async_sessionmaker(db.bind, expire_on_commit=False))
    out = await storage_migrate.move_uploads_to_s3()
    assert out["copied"] >= 1 and name in s3.buckets["uploads"]
    await db.refresh(user)
    assert user.avatar_url == f"https://media.example.com/{name}"


# ── Unused uploads ─────────────────────────────────────────────────────────────

async def test_prune_deletes_only_old_unreferenced_files(db):
    d = storage.upload_dir()
    used, orphan, fresh = (f"{uuid.uuid4().hex}.webp" for _ in range(3))
    for n in (used, orphan, fresh):
        d.joinpath(n).write_bytes(b"x")
    old = time.time() - 30 * 86400
    for n in (used, orphan):
        os.utime(d / n, (old, old))
    _, host = await make_user(db, "organizer")
    now = datetime.now(timezone.utc)
    db.add(Event(id=str(uuid.uuid4()), slug=f"e-{uuid.uuid4().hex}", title="Uses an upload", description="d" * 30,
                 venue_name="V", address="1 Street", city="Lagos", start_date=now, end_date=now + timedelta(hours=2),
                 host_id=host, cover_image=storage.api_url(used)))
    await db.commit()
    dry = await storage_jobs.prune_orphan_uploads(db, dry_run=True)
    assert dry["would_delete"] == 1 and (d / orphan).exists()
    out = await storage_jobs.prune_orphan_uploads(db)
    assert out["deleted"] == 1
    assert (d / used).exists() and (d / fresh).exists() and not (d / orphan).exists()


# ── Off-server backups ─────────────────────────────────────────────────────────

def test_offsite_backup_encrypts_uploads_and_prunes(tmp_path, s3, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "turnup-2026-11-18.sql.gz").write_bytes(gzip.compress(b"older dump"))
    (backups / "turnup-2026-11-19.sql.gz").write_bytes(gzip.compress(b"CREATE TABLE users;"))
    kyc = Path(settings.kyc_dir)
    kyc.mkdir(parents=True, exist_ok=True)
    (kyc / "doc1.webp").write_bytes(b"cac certificate")
    monkeypatch.setattr(settings, "backup_dir", str(backups))
    monkeypatch.setattr(settings, "backup_s3_bucket", "backups")
    monkeypatch.setattr(settings, "backup_passphrase", "correct horse battery staple")
    s3.put_object("backups", "db/ancient.sql.gz.enc", b"old")
    s3.buckets["backups"]["db/ancient.sql.gz.enc"]["LastModified"] = datetime.now(timezone.utc) - timedelta(days=40)

    out = storage_jobs.run_offsite_backup_sync()
    assert set(out["uploaded"]) >= {"db/turnup-2026-11-19.sql.gz.enc"}
    assert any(k.startswith("kyc/") for k in out["uploaded"])
    assert out["deleted"] == ["db/ancient.sql.gz.enc"]
    # Nothing readable in the bucket; decrypting gives the originals back.
    stored = s3.buckets["backups"]["db/turnup-2026-11-19.sql.gz.enc"]["Body"]
    assert stored.startswith(storage_jobs.MAGIC) and gzip.compress(b"CREATE TABLE users;")[10:20] not in stored
    (tmp_path / "db.enc").write_bytes(stored)
    storage_jobs.decrypt_file(tmp_path / "db.enc", tmp_path / "db.sql.gz", "correct horse battery staple")
    assert gzip.decompress((tmp_path / "db.sql.gz").read_bytes()) == b"CREATE TABLE users;"
    kyc_key = next(k for k in s3.buckets["backups"] if k.startswith("kyc/"))
    (tmp_path / "kyc.enc").write_bytes(s3.buckets["backups"][kyc_key]["Body"])
    storage_jobs.decrypt_file(tmp_path / "kyc.enc", tmp_path / "kyc.tar.gz", "correct horse battery staple")
    with tarfile.open(tmp_path / "kyc.tar.gz") as tar:
        assert tar.extractfile("doc1.webp").read() == b"cac certificate"

    again = storage_jobs.run_offsite_backup_sync()  # same day: nothing new to upload
    assert again["uploaded"] == []


def test_offsite_backup_skipped_until_configured(monkeypatch):
    monkeypatch.setattr(settings, "backup_s3_bucket", "")
    assert "skipped" in storage_jobs.run_offsite_backup_sync()
