"""Telegram Bot API: reading incoming messages (text, links, poster photos) and replying.

Every request goes to settings.telegram_api_base, never a host taken from a message, so this
adds no SSRF surface.
"""
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.ai_agent import MAX_IMAGE_BYTES

_TIMEOUT = 20
_URL_RE = re.compile(r"https?://\S+")


class TelegramError(Exception):
    pass


@dataclass
class InboundMessage:
    chat_id: str          # where replies go
    user_id: str | None   # the sender's Telegram user id, checked against the allowlist
    sender_name: str | None
    message_id: str
    text: str | None
    image_file_id: str | None
    command: str | None   # "help" (/start, /help) or "whoami"


def parse_update(update: dict) -> InboundMessage | None:
    """The message in a webhook update, or None for anything this bot doesn't handle (edits,
    stickers, group joins...)."""
    msg = update.get("message")
    if not isinstance(msg, dict) or not isinstance(msg.get("chat"), dict):
        return None
    sender = msg.get("from") if isinstance(msg.get("from"), dict) else {}
    text = msg.get("text") or msg.get("caption")

    image = None
    if isinstance(msg.get("photo"), list) and msg["photo"]:
        image = msg["photo"][-1].get("file_id")  # the largest size comes last
    doc = msg.get("document")
    if not image and isinstance(doc, dict) and str(doc.get("mime_type", "")).startswith("image/"):
        image = doc.get("file_id")  # a poster sent "as a file" to keep its quality

    command = None
    if text and not image:
        word = text.strip().split()[0].split("@")[0].lower() if text.strip() else ""
        command = {"/start": "help", "/help": "help", "/whoami": "whoami"}.get(word)
    if not text and not image:
        return None

    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or None
    if sender.get("username"):
        name = f"{name} (@{sender['username']})" if name else f"@{sender['username']}"
    return InboundMessage(
        chat_id=str(msg["chat"]["id"]),
        user_id=str(sender["id"]) if sender.get("id") else None,
        sender_name=name, message_id=str(msg.get("message_id")),
        text=text, image_file_id=image, command=command,
    )


def split_url(text: str | None) -> tuple[str | None, str | None]:
    """(remaining text, first link): a link goes to the AI drafter as a page to read."""
    if not text:
        return None, None
    m = _URL_RE.search(text)
    if not m:
        return text.strip() or None, None
    url = m.group(0).rstrip(").,!?>\"'")
    rest = (text[:m.start()] + text[m.end():]).strip()
    return rest or None, url


def _method(token: str, name: str) -> str:
    return f"{settings.telegram_api_base}/bot{token}/{name}"


async def _call(token: str, name: str, payload: dict | None = None, *, get: bool = False) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = (await client.get(_method(token, name), params=payload) if get
                else await client.post(_method(token, name), json=payload or {}))
    try:
        body = resp.json()
    except ValueError:
        raise TelegramError(f"Telegram answered {resp.status_code}")
    if not body.get("ok"):
        raise TelegramError(body.get("description") or f"Telegram answered {resp.status_code}")
    return body.get("result")


async def download_image(token: str, file_id: str) -> bytes:
    info = await _call(token, "getFile", {"file_id": file_id}, get=True)
    if (info.get("file_size") or 0) > MAX_IMAGE_BYTES:
        raise TelegramError("Image is too large (max 8MB)")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream("GET", f"{settings.telegram_api_base}/file/bot{token}/{info['file_path']}") as resp:
            resp.raise_for_status()
            data = b""
            async for chunk in resp.aiter_bytes():
                data += chunk
                if len(data) > MAX_IMAGE_BYTES:
                    raise TelegramError("Image is too large (max 8MB)")
    return data


async def send_message(token: str, chat_id: str, text: str) -> None:
    await _call(token, "sendMessage", {"chat_id": chat_id, "text": text})


async def send_typing(token: str, chat_id: str) -> None:
    await _call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})


async def get_me(token: str) -> dict:
    return await _call(token, "getMe", get=True)


async def set_webhook(token: str, url: str, secret: str) -> None:
    await _call(token, "setWebhook", {
        "url": url, "secret_token": secret,
        "allowed_updates": ["message"], "drop_pending_updates": True,
    })


async def delete_webhook(token: str) -> None:
    await _call(token, "deleteWebhook")
