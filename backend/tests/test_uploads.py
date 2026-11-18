"""Image uploads: only real images are accepted, and what's stored is a clean re-encode."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app.config import settings
from app.middleware.rate_limit import limiter
from app.models.auth_tokens import UserSession
from app.models.user import User
from app.services.auth import create_access_token


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "public_base_url", "https://turnup.example")
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


async def _auth(db) -> dict:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=uid, username=f"up_{uuid.uuid4().hex[:8]}", full_name="Up"))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}


def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (3000, 1500), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                      # Make
    exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0)}     # GPSInfo: somewhere in Lagos
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


async def _upload(client, headers, data: bytes, name="photo.jpg", ctype="image/jpeg"):
    return await client.post("/api/uploads", headers=headers, files={"file": (name, data, ctype)})


@pytest.mark.asyncio
async def test_upload_reencodes_resizes_and_strips_metadata(client, db):
    headers = await _auth(db)
    original = _jpeg_with_gps()
    assert Image.open(io.BytesIO(original)).getexif()  # sanity: the input has EXIF

    r = await _upload(client, headers, original)
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith("https://turnup.example/api/uploads/") and url.endswith(".webp")

    served = await client.get(url.replace("https://turnup.example", ""))
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.headers["x-content-type-options"] == "nosniff"
    img = Image.open(io.BytesIO(served.content))
    assert img.format == "WEBP"
    assert max(img.size) == 2000                      # scaled down from 3000
    assert not img.getexif()                          # GPS/camera metadata gone


@pytest.mark.asyncio
@pytest.mark.parametrize("name,data,ctype", [
    ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
    ("fake.png", b"<html><script>alert(1)</script></html>", "image/png"),
    ("doc.pdf", b"%PDF-1.4 not an image", "application/pdf"),
])
async def test_non_images_are_rejected(client, db, name, data, ctype):
    headers = await _auth(db)
    r = await _upload(client, headers, data, name, ctype)
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_needs_login_and_size_limit(client, db):
    assert (await _upload(client, {}, _jpeg_with_gps())).status_code == 401
    headers = await _auth(db)
    too_big = b"\xff\xd8" + b"0" * (8 * 1024 * 1024 + 10)
    assert (await _upload(client, headers, too_big)).status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["../../etc/passwd", "..%2F..%2Fapp.db", "abc.webp", "a" * 32 + ".png"])
async def test_only_generated_names_are_served(client, name):
    r = await client.get(f"/api/uploads/{name}")
    assert r.status_code == 404
