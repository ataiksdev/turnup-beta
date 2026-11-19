"""Appearance preference: saved on the account (so it follows the user across devices),
validated, and kept in step with the themes the frontend actually ships."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.auth_tokens import UserSession
from app.models.user import User
from app.schemas.user import THEME_IDS
from app.services.auth import create_access_token

THEMES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "themes.ts"


async def _auth(db) -> dict:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=uid, username=f"th_{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@example.com",
                full_name="Theme Tester"))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}


@pytest.mark.asyncio
async def test_theme_preference_round_trips(client, db):
    headers = await _auth(db)
    assert (await client.get("/api/auth/me", headers=headers)).json()["theme_preference"] is None
    r = await client.patch("/api/auth/me", json={"theme_preference": "glass:system"}, headers=headers)
    assert r.status_code == 200, r.text
    assert (await client.get("/api/auth/me", headers=headers)).json()["theme_preference"] == "glass:system"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["glass", "rainbow:dark", "fluffy:sepia", "fluffy:dark;x", ""])
async def test_invalid_theme_preference_rejected(client, db, bad):
    headers = await _auth(db)
    r = await client.patch("/api/auth/me", json={"theme_preference": bad}, headers=headers)
    assert r.status_code == 422


def test_backend_theme_ids_match_frontend():
    if not THEMES_TS.exists():
        pytest.skip("frontend not checked out")
    src = THEMES_TS.read_text()
    block = src[src.index("export const THEMES = {"):src.index("} as const satisfies")]
    frontend_ids = re.findall(r'^  "([a-z]+)": \{', block, flags=re.M)
    assert frontend_ids, "couldn't find theme ids in themes.ts"
    assert tuple(frontend_ids) == THEME_IDS, (
        "Theme ids differ between frontend/src/lib/themes.ts and backend/app/schemas/user.py THEME_IDS")
