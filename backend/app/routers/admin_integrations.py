"""Admin: agent connections (the Telegram bot, API keys for outside programs) and their log."""
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
from app.services import telegram
from app.services.url_safety import UnsafeURLError, validate_public_url

router = APIRouter(prefix="/api/admin/integrations", tags=["admin: integrations"])


async def _out(db: AsyncSession, conn: AgentConnection, cls=AgentConnectionOut, **extra):
    created = (await db.execute(select(func.count(AgentSubmission.id)).where(
        AgentSubmission.connection_id == conn.id, AgentSubmission.status == "created"))).scalar_one()
    host = await db.get(User, conn.host_user_id) if conn.host_user_id else None
    secrets = intake.connection_secrets(conn)
    is_tg = conn.kind == "telegram"
    return cls(
        id=conn.id, name=conn.name, kind=conn.kind, is_active=conn.is_active,
        api_key_prefix=conn.api_key_prefix, host_username=host.username if host else None,
        daily_limit=conn.daily_limit, used_today=await intake.used_today(db, conn),
        events_created=created, callback_url=conn.callback_url,
        telegram_bot_username=conn.telegram_bot_username if is_tg else None,
        telegram_connected=is_tg and bool(conn.telegram_bot_username and secrets.get("webhook_secret")),
        has_bot_token=is_tg and bool(secrets.get("bot_token")),
        allowed_senders=conn.allowed_senders if is_tg else None,
        webhook_url=intake.telegram_webhook_url(conn) if is_tg else None,
        last_used_at=conn.last_used_at, created_at=conn.created_at,
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


def _clean_allowlist(raw: str | None) -> str | None:
    ids = sorted(intake.parse_allowed_senders(raw))
    bad = [i for i in ids if not i.isdigit()]
    if bad:
        raise HTTPException(422, f"Use numeric Telegram user ids (message the bot /whoami to get yours), not: {', '.join(bad)}")
    return ", ".join(ids) or None


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
    """A new connection. For an API connection the key and callback secret are only ever shown
    here (and on rotation). A Telegram connection then needs Connect (below)."""
    conn = AgentConnection(
        name=body.name.strip(), kind=body.kind, is_active=True,
        host_user_id=await _resolve_host(db, body.host_username),
        daily_limit=body.daily_limit or settings.agent_default_daily_limit,
        created_by_id=admin.id,
    )
    extra = {}
    if body.kind == "api":
        api_key, conn.api_key_hash, conn.api_key_prefix = intake.new_api_key()
        callback_secret = intake.new_callback_secret()
        conn.callback_url = await _check_callback(body.callback_url)
        intake.set_secrets(conn, callback_secret=callback_secret)
        extra = {"api_key": api_key, "callback_secret": callback_secret}
    else:
        token = (body.telegram_bot_token or "").strip()
        if not token:
            raise HTTPException(422, "Paste the bot token @BotFather gave you")
        conn.allowed_senders = _clean_allowlist(body.allowed_senders)
        intake.set_secrets(conn, bot_token=token)
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return await _out(db, conn, AgentConnectionCreated, **extra)


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
    if conn.kind == "api" and "callback_url" in data:
        conn.callback_url = await _check_callback(data["callback_url"])
    if conn.kind == "telegram":
        if "allowed_senders" in data:
            conn.allowed_senders = _clean_allowlist(data["allowed_senders"])
        if (data.get("telegram_bot_token") or "").strip():
            # A different bot: it has to be connected again.
            intake.set_secrets(conn, bot_token=data["telegram_bot_token"].strip(), webhook_secret=None)
            conn.telegram_bot_username = None
    await db.flush()
    return await _out(db, conn)


@router.post("/{connection_id}/rotate-key", response_model=AgentConnectionCreated)
async def rotate_key(connection_id: str, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """API connections: a new API key and callback secret. The old key stops working at once."""
    conn = await _get(db, connection_id)
    if conn.kind != "api":
        raise HTTPException(400, "Telegram connections have no API key. Use Connect to renew the webhook secret.")
    api_key, conn.api_key_hash, conn.api_key_prefix = intake.new_api_key()
    callback_secret = intake.new_callback_secret()
    intake.set_secrets(conn, callback_secret=callback_secret)
    await db.flush()
    return await _out(db, conn, AgentConnectionCreated, api_key=api_key, callback_secret=callback_secret)


@router.post("/{connection_id}/telegram/connect", response_model=AgentConnectionOut)
async def connect_telegram(connection_id: str, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """Check the bot token and point the bot at Turnup's webhook (with a new secret)."""
    conn = await _get(db, connection_id)
    if conn.kind != "telegram":
        raise HTTPException(400, "Not a Telegram connection")
    token = intake.connection_secrets(conn).get("bot_token")
    if not token:
        raise HTTPException(400, "Add the bot token from @BotFather first")
    url = intake.telegram_webhook_url(conn)
    if not url.startswith("https://"):
        raise HTTPException(400, f"Telegram only sends to public https:// addresses, and this server's is {url}. "
                                 "Set PUBLIC_BASE_URL to Turnup's public address.")
    secret = intake.new_webhook_secret()
    try:
        me = await telegram.get_me(token)
        await telegram.set_webhook(token, url, secret)
    except telegram.TelegramError as e:
        raise HTTPException(422, f"Telegram said: {e}")
    except Exception as e:
        raise HTTPException(502, f"Couldn't reach Telegram: {e}")
    intake.set_secrets(conn, webhook_secret=secret)
    conn.telegram_bot_username = me.get("username")
    await db.flush()
    return await _out(db, conn)


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(connection_id: str, _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """Deletes the connection and its log (an API key stops working; a Telegram bot is
    disconnected). Events it created stay."""
    conn = await _get(db, connection_id)
    token = intake.connection_secrets(conn).get("bot_token") if conn.kind == "telegram" else None
    if token:
        try:
            await telegram.delete_webhook(token)
        except Exception:
            pass  # deleting the secret below makes Turnup refuse its calls anyway
    await db.delete(conn)


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
            id=s.id, connection_id=c.id, connection_name=c.name, kind=c.kind, status=s.status,
            submitted_by=s.submitted_by, input_text=s.input_text, error_note=s.error_note,
            event_id=ev.id if ev else None, event_title=ev.title if ev else None,
            event_review_status=ev.review_status if ev else None, created_at=s.created_at,
        )
        for s, c, ev in rows
    ]
