"""A Telegram bot that sends events to Turnup.

People send it a poster, a link, or the event details as text. It forwards them to Turnup's
agent API, which reads the event with AI and puts it in the admin approval queue, then tells
the person when it's approved or rejected.

Uses long polling (getUpdates), so it needs no public URL: run it anywhere with internet.
Setup: README.md next to this file. Needs Python 3.10+ and httpx (pip install httpx).
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

import httpx

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TURNUP_KEY = os.environ["TURNUP_API_KEY"]
TURNUP_API = os.environ.get("TURNUP_API_URL", "https://turnup.ng/api/integrations/v1").rstrip("/")
TELEGRAM_API = os.environ.get("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
# Submissions waiting for review, so the bot can tell people the outcome even after a restart.
STATE_FILE = Path(os.environ.get("STATE_FILE", "pending.json"))
REVIEW_CHECK_SECONDS = int(os.environ.get("REVIEW_CHECK_SECONDS", "60"))

HELP = (
    "Send me an event and I'll add it to Turnup:\n"
    "• a photo of the poster or flyer (add any extra details as the caption)\n"
    "• a link to the event's page\n"
    "• or the details as text: name, date, time, venue, price\n\n"
    "The Turnup team reviews every event before it goes live, and I'll message you here when "
    "yours is approved."
)
URL_RE = re.compile(r"https?://\S+")

log = logging.getLogger("turnup-telegram-bot")
tg = httpx.AsyncClient(base_url=f"{TELEGRAM_API}/bot{TELEGRAM_TOKEN}", timeout=60)
turnup = httpx.AsyncClient(base_url=TURNUP_API, timeout=90,
                           headers={"Authorization": f"Bearer {TURNUP_KEY}"})


# ── Pending reviews (a small JSON file) ──────────────────────────────────────

def load_pending() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_pending(pending: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(pending))
    tmp.replace(STATE_FILE)


pending: dict = load_pending()  # submission_id -> {"chat_id": ..., "title": ...}


# ── Telegram ─────────────────────────────────────────────────────────────────

async def send(chat_id: int | str, text: str) -> None:
    try:
        await tg.post("/sendMessage", json={"chat_id": chat_id, "text": text})
    except httpx.HTTPError as e:
        log.warning("sendMessage failed: %s", e)


async def download_file(file_id: str) -> bytes:
    info = (await tg.get("/getFile", params={"file_id": file_id})).json()
    path = info["result"]["file_path"]
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{TELEGRAM_API}/file/bot{TELEGRAM_TOKEN}/{path}")
    resp.raise_for_status()
    return resp.content


# ── Turnup ───────────────────────────────────────────────────────────────────

async def submit_to_turnup(chat_id: int, message_id: int, text: str | None, image: bytes | None) -> dict:
    data = {
        "submitted_by": f"telegram:{chat_id}",
        # Same message twice (e.g. after a restart) is a no-op on Turnup's side.
        "external_id": f"tg-{chat_id}-{message_id}",
    }
    if text:
        m = URL_RE.search(text)
        if m:
            data["url"] = m.group(0).rstrip(").,!?>\"'")
            text = (text[:m.start()] + text[m.end():]).strip()
        if text:
            data["text"] = text
    files = {"image": ("poster.jpg", image, "image/jpeg")} if image else None
    resp = await turnup.post("/drafts", data=data, files=files)
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code in (401, 403):
        log.error("Turnup refused the API key (%s): %s", resp.status_code, body)
        return {"message": "Sorry, I can't reach Turnup right now. Please try again later."}
    if "message" not in body:  # validation errors (413, 415, 422 without a status...)
        detail = body.get("detail")
        log.warning("Turnup answered %s: %s", resp.status_code, detail)
        return {"message": detail if isinstance(detail, str) else "Sorry, I couldn't send that to Turnup."}
    return body


async def handle_message(msg: dict) -> None:
    chat_id, message_id = msg["chat"]["id"], msg["message_id"]
    text = msg.get("text") or msg.get("caption")
    if text and text.strip().split("@")[0].lower() in ("/start", "/help"):
        await send(chat_id, HELP)
        return

    file_id = None
    if msg.get("photo"):
        file_id = msg["photo"][-1]["file_id"]  # largest size is last
    elif str((msg.get("document") or {}).get("mime_type", "")).startswith("image/"):
        file_id = msg["document"]["file_id"]  # poster sent "as a file"
    if not text and not file_id:
        await send(chat_id, "Send me a poster, a link or the event details as text. /help")
        return

    await tg.post("/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
    image = None
    if file_id:
        try:
            image = await download_file(file_id)
        except (httpx.HTTPError, KeyError) as e:
            log.warning("Couldn't download the image: %s", e)
            await send(chat_id, "I couldn't open that image. Please send it again.")
            return

    try:
        result = await submit_to_turnup(chat_id, message_id, text, image)
    except httpx.HTTPError as e:
        log.warning("Turnup request failed: %s", e)
        await send(chat_id, "Sorry, I can't reach Turnup right now. Please try again in a bit.")
        return

    if result.get("repeated"):
        return  # already answered this message
    if result.get("status") == "created":
        pending[result["submission_id"]] = {"chat_id": chat_id, "title": result.get("event_title")}
        save_pending(pending)
        reply = f"Got it: “{result['event_title']}”.\n{result['message']}"
    else:
        reply = result["message"]
    await send(chat_id, reply)


async def check_reviews() -> None:
    """Every so often, ask Turnup how pending submissions were reviewed and tell the sender."""
    while True:
        await asyncio.sleep(REVIEW_CHECK_SECONDS)
        for sub_id, info in list(pending.items()):
            try:
                resp = await turnup.get(f"/submissions/{sub_id}")
            except httpx.HTTPError:
                break  # Turnup unreachable: try again next round
            if resp.status_code == 404:
                pending.pop(sub_id)
                continue
            status = resp.json()
            if status.get("review_status") in ("approved", "rejected"):
                await send(info["chat_id"], status["message"])
                pending.pop(sub_id)
        save_pending(pending)


async def poll_telegram() -> None:
    me = (await tg.get("/getMe")).json()
    if not me.get("ok"):
        raise SystemExit(f"Telegram rejected TELEGRAM_BOT_TOKEN: {me.get('description')}")
    # Long polling and a webhook can't both be on: drop any webhook set earlier.
    await tg.post("/deleteWebhook")
    check = await turnup.get("/me")
    if check.status_code != 200:
        raise SystemExit(f"Turnup rejected TURNUP_API_KEY ({check.status_code}): {check.text}")
    log.info("Running as @%s, connected to Turnup as %r", me["result"]["username"], check.json()["name"])

    offset = None
    while True:
        params = {"timeout": 50, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = offset
        try:
            body = (await tg.get("/getUpdates", params=params)).json()
        except (httpx.HTTPError, ValueError) as e:
            body = {"ok": False, "description": str(e)}
        if not body.get("ok"):
            # e.g. 409 Conflict: another copy of the bot is running with the same token.
            log.warning("getUpdates failed: %s", body.get("description"))
            await asyncio.sleep(5)
            continue
        updates = body.get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            if "message" in update:
                # One at a time keeps it simple; drafting a poster takes a few seconds.
                try:
                    await handle_message(update["message"])
                except Exception:
                    log.exception("Failed to handle a message")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    await asyncio.gather(poll_telegram(), check_reviews())


if __name__ == "__main__":
    asyncio.run(main())
