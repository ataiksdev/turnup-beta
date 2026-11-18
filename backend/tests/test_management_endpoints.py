"""Endpoints behind the new organizer/community management screens."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.auth_tokens import UserSession
from app.models.event import Event
from app.models.organizer import OrganizerProfile, TicketTier
from app.models.user import User
from app.services.auth import create_access_token


def _u() -> str:
    return uuid.uuid4().hex[:10]


async def _user(db, role="attendee") -> tuple[dict, str]:
    uid, jti = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=uid, username=f"{role}_{_u()}", email=f"{_u()}@example.com", full_name="X", role=role))
    db.add(UserSession(user_id=uid, jti=jti, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(uid, jti)[0]}"}, uid


@pytest.mark.asyncio
async def test_paused_tiers_visible_to_host_only(client, db):
    host_h, host = await _user(db, "organizer")
    other_h, _ = await _user(db)
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(Event(id=eid, slug=f"e-{eid}", title="Tiered", description="d" * 30, venue_name="V",
                 address="1 Street", city="Lagos", country="NG", start_date=now + timedelta(days=3),
                 end_date=now + timedelta(days=3, hours=2), host_id=host, status="published"))
    db.add(TicketTier(id=str(uuid.uuid4()), event_id=eid, name="On sale", price=10.0))
    db.add(TicketTier(id=str(uuid.uuid4()), event_id=eid, name="Paused", price=20.0, is_active=False))
    await db.commit()

    public = (await client.get(f"/api/events/{eid}/tickets")).json()
    assert [t["name"] for t in public] == ["On sale"]
    host_view = (await client.get(f"/api/events/{eid}/tickets?include_inactive=true", headers=host_h)).json()
    assert {t["name"] for t in host_view} == {"On sale", "Paused"}
    assert (await client.get(f"/api/events/{eid}/tickets?include_inactive=true", headers=other_h)).status_code == 403


@pytest.mark.asyncio
async def test_organizer_without_profile_row_can_create_one(client, db):
    headers, uid = await _user(db, "organizer")  # e.g. promoted by an admin: no profile row
    r = await client.patch("/api/organizer/profile", json={"organization_name": "Hype House"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["organization_name"] == "Hype House"
    db.expire_all()
    assert (await db.execute(select(OrganizerProfile).where(OrganizerProfile.user_id == uid))).scalar_one()
