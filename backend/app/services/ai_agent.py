import base64
import json
import re
from datetime import datetime, timezone

import httpx

from app.config import settings

_URL_FETCH_TIMEOUT = 15
_MAX_HTML_CHARS = 20000
_MAX_IMAGE_BYTES = 8 * 1024 * 1024

_TOOL_NAME = "extract_event_details"
_TOOL_DESCRIPTION = "Structured event details extracted from the supplied source material."

# Shared JSON-schema-style field definitions. Every provider adapter below translates this into
# whatever shape its own function/tool-calling (or structured-output) API expects, so adding a
# new field only ever needs to happen here.
_EXTRACT_PROPERTIES = {
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
}
_EXTRACT_REQUIRED = ["title", "description", "confidence_notes"]


class AIAgentError(Exception):
    pass


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


async def _build_prompt_text(
    text: str | None, url: str | None, has_image: bool, category_names: list[str],
) -> str:
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
    if has_image:
        prompt_parts.append("A flyer image is attached — read any text/dates/venue/pricing on it.")

    prompt_parts.append(
        f"Extract the event details and call {_TOOL_NAME}. "
        "If a field truly cannot be determined, omit it rather than inventing a value, "
        "except title, description, and confidence_notes which are required."
    )
    return "\n\n".join(prompt_parts)


async def _draft_anthropic(prompt_text: str, image_bytes: bytes | None, image_media_type: str | None) -> dict:
    if not settings.anthropic_api_key:
        raise AIAgentError("AI drafting is not configured (missing ANTHROPIC_API_KEY).")
    from anthropic import AsyncAnthropic

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
    content.append({"type": "text", "text": prompt_text})

    tool = {
        "name": _TOOL_NAME,
        "description": _TOOL_DESCRIPTION,
        "input_schema": {"type": "object", "properties": _EXTRACT_PROPERTIES, "required": _EXTRACT_REQUIRED},
    }
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            tools=[tool],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        raise AIAgentError(f"AI drafting failed (Anthropic): {e}")

    for block in resp.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return block.input
    raise AIAgentError("AI did not return structured event details.")


async def _draft_openai(prompt_text: str, image_bytes: bytes | None, image_media_type: str | None) -> dict:
    if not settings.openai_api_key:
        raise AIAgentError("AI drafting is not configured (missing OPENAI_API_KEY).")
    from openai import AsyncOpenAI

    user_content: list[dict] = [{"type": "text", "text": prompt_text}]
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        media_type = image_media_type or "image/jpeg"
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{b64}"},
        })

    tool = {
        "type": "function",
        "function": {
            "name": _TOOL_NAME,
            "description": _TOOL_DESCRIPTION,
            "parameters": {"type": "object", "properties": _EXTRACT_PROPERTIES, "required": _EXTRACT_REQUIRED},
        },
    }
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": user_content}],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
        )
    except Exception as e:
        raise AIAgentError(f"AI drafting failed (OpenAI): {e}")

    calls = resp.choices[0].message.tool_calls or []
    for call in calls:
        if call.function.name == _TOOL_NAME:
            try:
                return json.loads(call.function.arguments)
            except json.JSONDecodeError as e:
                raise AIAgentError(f"AI returned malformed JSON: {e}")
    raise AIAgentError("AI did not return structured event details.")


async def _draft_gemini(prompt_text: str, image_bytes: bytes | None, image_media_type: str | None) -> dict:
    if not settings.gemini_api_key:
        raise AIAgentError("AI drafting is not configured (missing GEMINI_API_KEY).")
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    schema = {"type": "object", "properties": _EXTRACT_PROPERTIES, "required": _EXTRACT_REQUIRED}
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config={"response_mime_type": "application/json", "response_schema": schema},
    )

    parts: list = [prompt_text]
    if image_bytes:
        parts.append({"mime_type": image_media_type or "image/jpeg", "data": image_bytes})

    try:
        resp = await model.generate_content_async(parts)
    except Exception as e:
        raise AIAgentError(f"AI drafting failed (Gemini): {e}")

    try:
        return json.loads(resp.text)
    except (ValueError, AttributeError) as e:
        raise AIAgentError(f"AI did not return structured event details: {e}")


_KNOWN_PROVIDERS = ("anthropic", "openai", "gemini")


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

    if settings.ai_provider not in _KNOWN_PROVIDERS:
        raise AIAgentError(
            f"Unknown AI_PROVIDER '{settings.ai_provider}' — expected one of: {', '.join(_KNOWN_PROVIDERS)}."
        )

    prompt_text = await _build_prompt_text(text, url, bool(image_bytes), category_names)

    # Dispatched by bare name (not a dict of function references captured at import time) so
    # tests can patch.object(ai_agent, "_draft_openai", ...) and have it actually take effect.
    if settings.ai_provider == "anthropic":
        return await _draft_anthropic(prompt_text, image_bytes, image_media_type)
    elif settings.ai_provider == "openai":
        return await _draft_openai(prompt_text, image_bytes, image_media_type)
    else:
        return await _draft_gemini(prompt_text, image_bytes, image_media_type)
