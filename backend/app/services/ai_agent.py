import base64
import json
import re
from datetime import datetime, timezone

import httpx
from anthropic import AsyncAnthropic

from app.config import settings

_URL_FETCH_TIMEOUT = 15
_MAX_HTML_CHARS = 20000
_MAX_IMAGE_BYTES = 8 * 1024 * 1024

_EXTRACT_TOOL = {
    "name": "extract_event_details",
    "description": "Structured event details extracted from the supplied source material.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event title"},
            "description": {"type": "string", "description": "A clean, promotional 2-4 sentence event description"},
            "venue_name": {"type": "string"},
            "address": {"type": "string", "description": "Street address, best guess if not explicit"},
            "city": {"type": "string"},
            "country": {"type": "string", "description": "ISO-ish country name, e.g. Nigeria, United States"},
            "start_date": {"type": "string", "description": "ISO 8601 datetime, resolve relative dates against the given current date"},
            "end_date": {"type": "string", "description": "ISO 8601 datetime; if unknown, assume 3 hours after start_date"},
            "is_free": {"type": "boolean"},
            "price_min": {"type": "number"},
            "price_max": {"type": "number"},
            "currency": {"type": "string", "description": "3-letter currency code, e.g. NGN, USD"},
            "event_type": {"type": "string", "enum": ["physical", "virtual", "hybrid"]},
            "category_guess": {"type": "string", "description": "Best-matching category name from the provided list, or empty string"},
            "tags": {"type": "string", "description": "Comma-separated short tags"},
            "confidence_notes": {"type": "string", "description": "Brief note on which fields were guessed/uncertain vs explicit in the source"},
        },
        "required": ["title", "description", "confidence_notes"],
    },
}


class AIAgentError(Exception):
    pass


def _client() -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise AIAgentError("AI drafting is not configured (missing ANTHROPIC_API_KEY).")
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def fetch_url_text(url: str) -> str:
    """Fetch a URL and strip it down to text a model can read. No JS rendering."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=_URL_FETCH_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TurnupBot/1.0)"})
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise AIAgentError(f"Could not fetch URL: {e}")

    html = resp.text[:_MAX_HTML_CHARS * 4]  # cap before regex work
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_HTML_CHARS]


async def draft_event(
    *,
    text: str | None,
    url: str | None,
    image_bytes: bytes | None,
    image_media_type: str | None,
    category_names: list[str],
) -> dict:
    if not text and not url and not image_bytes:
        raise AIAgentError("Provide at least one of: pasted text, a URL, or a flyer image.")

    if image_bytes and len(image_bytes) > _MAX_IMAGE_BYTES:
        raise AIAgentError("Flyer image is too large (max 8MB).")

    content: list[dict] = []
    if image_bytes:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type or "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            },
        })

    prompt_parts = [
        f"Today's date is {datetime.now(timezone.utc).isoformat()} (UTC). "
        "Resolve any relative dates (e.g. 'this Friday', 'next month') against it.",
    ]
    if category_names:
        prompt_parts.append("Available categories: " + ", ".join(category_names) + ".")
    if url:
        page_text = await fetch_url_text(url)
        prompt_parts.append(f"Source URL: {url}\n\nPage content:\n{page_text}")
    if text:
        prompt_parts.append(f"Pasted description:\n{text}")
    if image_bytes:
        prompt_parts.append("A flyer image is attached — read any text/dates/venue/pricing on it.")

    prompt_parts.append(
        "Extract the event details and call extract_event_details. "
        "If a field truly cannot be determined, omit it rather than inventing a value, "
        "except title, description, and confidence_notes which are required."
    )
    content.append({"type": "text", "text": "\n\n".join(prompt_parts)})

    client = _client()
    try:
        resp = await client.messages.create(
            model=settings.ai_agent_model,
            max_tokens=1500,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_event_details"},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        raise AIAgentError(f"AI drafting failed: {e}")

    for block in resp.content:
        if block.type == "tool_use" and block.name == "extract_event_details":
            return block.input
    raise AIAgentError("AI did not return structured event details.")
