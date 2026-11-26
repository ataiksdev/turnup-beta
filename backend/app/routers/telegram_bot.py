"""The Telegram bot's webhook. Telegram POSTs each message the bot receives here; Turnup answers
at once and drafts the event in the background (reading a poster takes several seconds).
Setup: Admin → Bot Connections, docs/agent-connections.md.
"""
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.database import get_db
from app.models.agent import AgentConnection
from app.services import agent_intake as intake
from app.services import telegram

logger = logging.getLogger("turnup.agents")
router = APIRouter(prefix="/api/integrations/telegram", tags=["telegram bot"], include_in_schema=False)


def session_factory():
    """The session background processing uses once the webhook has answered (tests replace it)."""
    return database.AsyncSessionLocal()


async def _reply(token: str, chat_id: str, text: str) -> None:
    try:
        await telegram.send_message(token, chat_id, text)
    except Exception as e:
        logger.warning("Telegram reply failed: %s", e)


async def process_message(connection_id: str, msg: telegram.InboundMessage) -> None:
    async with session_factory() as db:
        conn = await db.get(AgentConnection, connection_id)
        if not conn or not conn.is_active or conn.kind != "telegram":
            return
        token = intake.connection_secrets(conn).get("bot_token")
        if not token:
            return

        if msg.command == "whoami":
            # Answered for anyone: it's how the admin finds the id to put on the allowlist.
            await _reply(token, msg.chat_id, f"Your Telegram id is {msg.user_id}")
            return
        allowed = intake.sender_allowed(conn, msg.user_id)
        if msg.command == "help":
            await _reply(token, msg.chat_id, intake.TELEGRAM_HELP if allowed else intake.TELEGRAM_NOT_OPEN)
            return
        if not allowed:
            intake.record_refusal(db, conn, intake.Submission(
                submitted_by=msg.sender_name or msg.user_id, reply_chat_id=msg.chat_id, text=msg.text))
            await db.commit()
            await _reply(token, msg.chat_id, intake.TELEGRAM_NOT_OPEN)
            return

        try:
            await telegram.send_typing(token, msg.chat_id)
        except Exception:
            pass
        text, url = telegram.split_url(msg.text)
        image = None
        if msg.image_file_id:
            try:
                image = await telegram.download_image(token, msg.image_file_id)
            except Exception as e:
                logger.warning("Couldn't download a Telegram image: %s", e)
                if not (text or url):
                    await _reply(token, msg.chat_id, "I couldn't open that image. Please send it again.")
                    return

        try:
            result = await intake.submit(db, conn, intake.Submission(
                submitted_by=msg.sender_name or msg.user_id, reply_chat_id=msg.chat_id,
                external_id=f"tg:{msg.chat_id}:{msg.message_id}",
                text=text, url=url, image_bytes=image, image_media_type="image/jpeg" if image else None,
            ))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Telegram submission failed")
            await _reply(token, msg.chat_id, "Something went wrong reading that. Please try again in a little while.")
            return
        if not result.repeated:  # a Telegram retry of a message already answered
            await _reply(token, msg.chat_id, intake.chat_reply(result))


@router.post("/{connection_id}")
async def telegram_webhook(
    connection_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    conn = await db.get(AgentConnection, connection_id)
    if not conn or conn.kind != "telegram":
        raise HTTPException(404, "Not found")
    expected = intake.connection_secrets(conn).get("webhook_secret")
    if not expected or not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            expected, x_telegram_bot_api_secret_token):
        raise HTTPException(401, "Bad secret token")
    if not conn.is_active:
        return {"ok": True}  # 200 so Telegram doesn't keep retrying
    try:
        update = json.loads(await request.body())
    except ValueError:
        return {"ok": True}
    msg = telegram.parse_update(update) if isinstance(update, dict) else None
    if msg:
        background_tasks.add_task(process_message, conn.id, msg)
    return {"ok": True}
