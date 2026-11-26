"""Admin: agent connections (API keys for outside bots and agents) and their submission log."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_admin
from app.models.agent import AgentConnection, AgentSubmission
from app.models.event import Event
from app.models.user import User
from app.schemas.agent import (
    AgentConnectionCreate, AgentConnectionCreated, AgentConnectionOut, AgentConnectionUpdate,
    AgentSubmissionOut,
)
from app.services import agent_intake as intake
from app.services.url_safety import UnsafeURLError, validate_public_url

router = APIRouter(prefix="/api/admin/integrations", tags=["admin: integrations"])


async def _out(db: AsyncSession, conn: AgentConnection, cls=AgentConnectionOut, **extra):
    created = (await db.execute(select(func.count(AgentSubmission.id)).where(
        AgentSubmission.connection_id == conn.id, AgentSubmission.status == "created"))).scalar_one()
    host = await db.get(User, conn.host_user_id) if conn.host_user_id else None
    return cls(
        id=conn.id, name=conn.name, is_active=conn.is_active, api_key_prefix=conn.api_key_prefix,
        host_username=host.username if host else None, daily_limit=conn.daily_limit,
        used_today=await intake.used_today(db, conn), events_created=created,
        callback_url=conn.callback_url, last_used_at=conn.last_used_at, created_at=conn.created_at,
        **extra,
    )


async def _resolve_host(db: AsyncSession, username: str | None) -> str | None:
    name = (username or "").strip().lstrip("@")
    if not name:
        return None
    user = (await db.execute(select(User).where(
        User.username == name, User.is_deleted == False))).scalar_one_or_none()
    if not user:
        raise HTTPException(422, f"No user named @{name}")
    return user.id


async def _check_callback(url: str | None) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if not settings.debug and not url.startswith("https://"):
        raise HTTPException(422, "The callback URL must start with https://")
    try:
        await validate_public_url(url)
    except UnsafeURLError as e:
        raise HTTPException(422, f"Callback URL not allowed: {e}")
    return url


async def _get(db: AsyncSession, connection_id: str) -> AgentConnection:
    conn = await db.get(AgentConnection, connection_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    return conn


@router.get("", response_model=list[AgentConnectionOut])
async def list_connections(_: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    conns = (await db.execute(select(AgentConnection).order_by(AgentConnection.created_at.desc()))).scalars().all()
    return [await _out(db, c) for c in conns]


@router.post("", response_model=AgentConnectionCreated, status_code=201)
async def create_connection(
    body: AgentConnectionCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """A new connection. The API key and callback signing secret are only ever shown here
    (and on rotation): give them to whoever runs the bot."""
    api_key, key_hash, prefix = intake.new_api_key()
    callback_secret = intake.new_callback_secret()
    conn = AgentConnection(
        name=body.name.strip(), is_active=True, api_key_hash=key_hash, api_key_prefix=prefix,
        callback_url=await _check_callback(body.callback_url),
        callback_secret_encrypted=intake.encrypt(callback_secret),
        host_user_id=await _resolve_host(db, body.host_username),
        daily_limit=body.daily_limit or settings.agent_default_daily_limit,
        created_by_id=admin.id,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return await _out(db, conn, AgentConnectionCreated, api_key=api_key, callback_secret=callback_secret)


@router.patch("/{connection_id}", response_model=AgentConnectionOut)
async def update_connection(
    connection_id: str,
    body: AgentConnectionUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    conn = await _get(db, connection_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        conn.name = data["name"].strip()
    if data.get("is_active") is not None:
        conn.is_active = data["is_active"]
    if "host_username" in data:
        conn.host_user_id = await _resolve_host(db, data["host_username"])
    if data.get("daily_limit") is not None:
        conn.daily_limit = data["daily_limit"]
    if "callback_url" in data:
        conn.callback_url = await _check_callback(data["callback_url"])
    await db.flush()
    return await _out(db, conn)


@router.post("/{connection_id}/rotate-key", response_model=AgentConnectionCreated)
async def rotate_key(connection_id: str, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """A new API key and callback secret. The old key stops working at once."""
    conn = await _get(db, connection_id)
    api_key, conn.api_key_hash, conn.api_key_prefix = intake.new_api_key()
    callback_secret = intake.new_callback_secret()
    conn.callback_secret_encrypted = intake.encrypt(callback_secret)
    await db.flush()
    return await _out(db, conn, AgentConnectionCreated, api_key=api_key, callback_secret=callback_secret)


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(connection_id: str, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """Deletes the connection (its key stops working) and its log. Events it created stay."""
    await db.delete(await _get(db, connection_id))


@router.get("/submissions", response_model=list[AgentSubmissionOut])
async def list_submissions(
    connection_id: str | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AgentSubmission, AgentConnection, Event)
        .join(AgentConnection, AgentConnection.id == AgentSubmission.connection_id)
        .outerjoin(Event, Event.id == AgentSubmission.event_id)
    )
    if connection_id:
        stmt = stmt.where(AgentSubmission.connection_id == connection_id)
    if status:
        stmt = stmt.where(AgentSubmission.status == status)
    rows = (await db.execute(stmt.order_by(AgentSubmission.created_at.desc()).offset(skip).limit(limit))).all()
    return [
        AgentSubmissionOut(
            id=s.id, connection_id=c.id, connection_name=c.name, status=s.status,
            submitted_by=s.submitted_by, input_text=s.input_text, error_note=s.error_note,
            event_id=ev.id if ev else None, event_title=ev.title if ev else None,
            event_review_status=ev.review_status if ev else None, created_at=s.created_at,
        )
        for s, c, ev in rows
    ]
