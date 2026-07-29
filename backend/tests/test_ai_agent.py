"""Tests for the pluggable AI drafting service: provider dispatch and each adapter
(Anthropic/OpenAI/Gemini) in isolation, with each provider's client mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services import ai_agent


@pytest.mark.asyncio
async def test_draft_event_requires_some_input():
    with pytest.raises(ai_agent.AIAgentError):
        await ai_agent.draft_event(text=None, url=None, image_bytes=None, image_media_type=None, category_names=[])


@pytest.mark.asyncio
async def test_draft_event_rejects_oversized_image():
    with pytest.raises(ai_agent.AIAgentError):
        await ai_agent.draft_event(
            text=None, url=None, image_bytes=b"x" * (9 * 1024 * 1024),
            image_media_type="image/jpeg", category_names=[],
        )


@pytest.mark.asyncio
async def test_draft_event_rejects_unknown_provider():
    with patch.object(settings, "ai_provider", "does-not-exist"):
        with pytest.raises(ai_agent.AIAgentError, match="Unknown AI_PROVIDER"):
            await ai_agent.draft_event(text="party tonight", url=None, image_bytes=None, image_media_type=None, category_names=[])


@pytest.mark.asyncio
async def test_draft_event_dispatches_to_selected_provider():
    fake_result = {"title": "T", "description": "D", "confidence_notes": "n"}
    with patch.object(settings, "ai_provider", "openai"), \
         patch.object(ai_agent, "_draft_openai", new=AsyncMock(return_value=fake_result)) as mock_openai, \
         patch.object(ai_agent, "_draft_anthropic", new=AsyncMock(side_effect=AssertionError("should not be called"))):
        result = await ai_agent.draft_event(
            text="party", url=None, image_bytes=None, image_media_type=None, category_names=["Music"],
        )
    assert result == fake_result
    mock_openai.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_prompt_text_includes_categories_and_text():
    prompt = await ai_agent._build_prompt_text("Party tonight", None, False, ["Music", "Comedy"])
    assert "Music, Comedy" in prompt
    assert "Party tonight" in prompt


# ── Anthropic adapter ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_anthropic_missing_key():
    with patch.object(settings, "anthropic_api_key", ""):
        with pytest.raises(ai_agent.AIAgentError, match="ANTHROPIC_API_KEY"):
            await ai_agent._draft_anthropic("prompt", None, None)


@pytest.mark.asyncio
async def test_draft_anthropic_parses_tool_use_response():
    fake_block = MagicMock()
    fake_block.type = "tool_use"
    fake_block.name = "extract_event_details"
    fake_block.input = {"title": "Party", "description": "desc", "confidence_notes": "ok"}
    fake_resp = MagicMock(content=[fake_block])

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "anthropic_api_key", "test-key"), \
         patch("anthropic.AsyncAnthropic", return_value=fake_client):
        result = await ai_agent._draft_anthropic("prompt text", None, None)

    assert result["title"] == "Party"
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "extract_event_details"}
    assert kwargs["messages"][0]["content"][0]["text"] == "prompt text"


@pytest.mark.asyncio
async def test_draft_anthropic_includes_image_block():
    # Note: `name=` in the MagicMock() constructor is special-cased by unittest.mock (it sets
    # the mock's repr, not a `.name` attribute) — must be assigned separately.
    fake_block = MagicMock(type="tool_use", input={"title": "P", "description": "D", "confidence_notes": "n"})
    fake_block.name = "extract_event_details"
    fake_resp = MagicMock(content=[fake_block])
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "anthropic_api_key", "test-key"), \
         patch("anthropic.AsyncAnthropic", return_value=fake_client):
        await ai_agent._draft_anthropic("prompt text", b"fake-bytes", "image/png")

    _, kwargs = fake_client.messages.create.call_args
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1]["type"] == "text"


@pytest.mark.asyncio
async def test_draft_anthropic_raises_when_no_tool_use_block():
    fake_resp = MagicMock(content=[])
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "anthropic_api_key", "test-key"), \
         patch("anthropic.AsyncAnthropic", return_value=fake_client):
        with pytest.raises(ai_agent.AIAgentError, match="did not return structured"):
            await ai_agent._draft_anthropic("prompt text", None, None)


# ── OpenAI adapter ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_openai_missing_key():
    with patch.object(settings, "openai_api_key", ""):
        with pytest.raises(ai_agent.AIAgentError, match="OPENAI_API_KEY"):
            await ai_agent._draft_openai("prompt", None, None)


@pytest.mark.asyncio
async def test_draft_openai_parses_tool_call_response():
    fake_call = MagicMock()
    fake_call.function.name = "extract_event_details"
    fake_call.function.arguments = json.dumps({"title": "Party", "description": "desc", "confidence_notes": "ok"})
    fake_message = MagicMock(tool_calls=[fake_call])
    fake_choice = MagicMock(message=fake_message)
    fake_resp = MagicMock(choices=[fake_choice])

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "openai_api_key", "test-key"), \
         patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await ai_agent._draft_openai("prompt text", None, None)

    assert result["title"] == "Party"
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "extract_event_details"}}


@pytest.mark.asyncio
async def test_draft_openai_includes_image_url_block():
    fake_call = MagicMock()
    fake_call.function.name = "extract_event_details"
    fake_call.function.arguments = json.dumps({"title": "P", "description": "D", "confidence_notes": "n"})
    fake_resp = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[fake_call]))])
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "openai_api_key", "test-key"), \
         patch("openai.AsyncOpenAI", return_value=fake_client):
        await ai_agent._draft_openai("prompt text", b"fake-bytes", "image/png")

    _, kwargs = fake_client.chat.completions.create.call_args
    content = kwargs["messages"][0]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_draft_openai_raises_when_no_tool_calls():
    fake_resp = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None))])
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "openai_api_key", "test-key"), \
         patch("openai.AsyncOpenAI", return_value=fake_client):
        with pytest.raises(ai_agent.AIAgentError, match="did not return structured"):
            await ai_agent._draft_openai("prompt text", None, None)


# ── Gemini adapter ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_gemini_missing_key():
    with patch.object(settings, "gemini_api_key", ""):
        with pytest.raises(ai_agent.AIAgentError, match="GEMINI_API_KEY"):
            await ai_agent._draft_gemini("prompt", None, None)


@pytest.mark.asyncio
async def test_draft_gemini_parses_json_response():
    fake_resp = MagicMock()
    fake_resp.text = json.dumps({"title": "Party", "description": "desc", "confidence_notes": "ok"})
    fake_model = MagicMock()
    fake_model.generate_content_async = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "gemini_api_key", "test-key"), \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=fake_model):
        result = await ai_agent._draft_gemini("prompt text", None, None)

    assert result["title"] == "Party"


@pytest.mark.asyncio
async def test_draft_gemini_raises_on_malformed_json():
    fake_resp = MagicMock()
    fake_resp.text = "not json"
    fake_model = MagicMock()
    fake_model.generate_content_async = AsyncMock(return_value=fake_resp)

    with patch.object(settings, "gemini_api_key", "test-key"), \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=fake_model):
        with pytest.raises(ai_agent.AIAgentError, match="did not return structured"):
            await ai_agent._draft_gemini("prompt text", None, None)
