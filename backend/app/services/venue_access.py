"""Who may do what with a venue (docs/venues-spec.md section 2).

Venue roles live in venue_members, agents in agents, so one person can be an attendee, a
venue manager and an agent at once without touching users.role.
"""
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import Notification
from app.models.user import User
from app.models.venue import Agent, AgentVisit, Venue, VenueMember

ROLE_RANK = {"viewer": 1, "manager": 2, "owner": 3}


async def get_membership(db: AsyncSession, venue_id: str, user_id: str) -> VenueMember | None:
    return (await db.execute(select(VenueMember).where(
        VenueMember.venue_id == venue_id, VenueMember.user_id == user_id))).scalar_one_or_none()


async def require_venue_role(db: AsyncSession, venue_id: str, user: User, minimum: str) -> tuple[Venue, VenueMember]:
    venue = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()
    if not venue or venue.status == "closed":
        raise HTTPException(404, "Venue not found")
    member = await get_membership(db, venue_id, user.id)
    if not member:
        raise HTTPException(403, "You're not on this venue's team.")
    if ROLE_RANK[member.role] < ROLE_RANK[minimum]:
        needed = {"manager": "a Manager or the Owner", "owner": "the Owner"}.get(minimum, minimum)
        raise HTTPException(403, f"Only {needed} can do that.")
    return venue, member


async def venue_team_ids(db: AsyncSession, venue_id: str, minimum: str = "manager") -> list[str]:
    rows = (await db.execute(select(VenueMember.user_id, VenueMember.role).where(
        VenueMember.venue_id == venue_id))).all()
    return [uid for uid, role in rows if ROLE_RANK[role] >= ROLE_RANK[minimum]]


async def get_agent(db: AsyncSession, user: User) -> Agent | None:
    return (await db.execute(select(Agent).where(
        Agent.user_id == user.id, Agent.is_active == True))).scalar_one_or_none()  # noqa: E712


def agent_states(agent: Agent) -> list[str]:
    try:
        return list(json.loads(agent.states or "[]"))
    except ValueError:
        return []


async def agent_assigned_to(db: AsyncSession, venue_id: str, user_id: str) -> bool:
    visit = (await db.execute(select(AgentVisit.id).where(
        AgentVisit.venue_id == venue_id, AgentVisit.agent_id == user_id,
        AgentVisit.status.in_(["assigned", "scheduled", "passed", "failed"]),
    ))).first()
    return visit is not None


async def can_view_kyc(db: AsyncSession, venue_id: str, user: User) -> bool:
    """Admins, and the agent assigned to the venue. Not the venue's own team: they uploaded
    the files and can replace them, but the stored copies are for verification only."""
    if user.role == "admin":
        return True
    agent = await get_agent(db, user)
    return bool(agent and await agent_assigned_to(db, venue_id, user.id))


def notify(db: AsyncSession, user_id: str, type_: str, title: str, body: str | None = None,
           reference_id: str | None = None, reference_type: str | None = None) -> None:
    db.add(Notification(id=str(uuid.uuid4()), user_id=user_id, type=type_, title=title[:200],
                        body=body, reference_id=reference_id, reference_type=reference_type))


async def notify_venue_team(db: AsyncSession, venue_id: str, type_: str, title: str,
                            body: str | None = None, reference_id: str | None = None,
                            reference_type: str | None = None, minimum: str = "manager") -> None:
    for uid in await venue_team_ids(db, venue_id, minimum):
        notify(db, uid, type_, title, body, reference_id, reference_type)
