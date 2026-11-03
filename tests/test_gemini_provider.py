"""Tests for the Gemini LLM provider."""

import json
from unittest.mock import MagicMock, patch

import pytest

from llm import get_provider, get_provider_by_name, LLMResponse
from llm.gemini_provider import GeminiProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gemini_response(text="hello", function_call=None, total_tokens=42):
    """Build a fake Gemini generate_content response object."""
    part = MagicMock()
    part.function_call = function_call

    # If no function call, .text should work normally
    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.total_token_count = total_tokens

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    response.text = text
    return response


def _gemini_provider_with_mock_client():
    """Create a GeminiProvider with a pre-injected mock client."""
    provider = GeminiProvider(api_key="test-key-123")
    mock_client = MagicMock()
    provider._client = mock_client  # bypass lazy _get_client
    return provider, mock_client


# ---------------------------------------------------------------------------
# Chat tests
# ---------------------------------------------------------------------------

def test_gemini_chat():
    provider, mock_client = _gemini_provider_with_mock_client()
    mock_client.models.generate_content.return_value = _make_gemini_response(
        text="Gemini says hi", total_tokens=88
    )

    resp = provider.chat([{"role": "user", "content": "hello"}])

    assert isinstance(resp, LLMResponse)
    assert resp.content == "Gemini says hi"
    assert resp.tool_call is None
    assert resp.tokens_used == 88
    assert resp.model == "gemini-2.5-flash"
    assert resp.latency_ms >= 0
    mock_client.models.generate_content.assert_called_once()


def test_gemini_chat_with_system_message():
    """System messages are extracted and passed as system_instruction."""
    provider, mock_client = _gemini_provider_with_mock_client()
    mock_client.models.generate_content.return_value = _make_gemini_response(
        text="I am a cat", total_tokens=20
    )

    messages = [
        {"role": "system", "content": "You are a cat."},
        {"role": "user", "content": "Who are you?"},
    ]
    resp = provider.chat(messages)

    assert resp.content == "I am a cat"
    # Verify the config passed to generate_content includes system_instruction
    call_kwargs = mock_client.models.generate_content.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert config.system_instruction == "You are a cat."


def test_gemini_chat_with_tools():
    provider, mock_client = _gemini_provider_with_mock_client()

    fc = MagicMock()
    fc.name = "rename"
    fc.args = {"filename": "report.pdf"}

    mock_client.models.generate_content.return_value = _make_gemini_response(
        text="", function_call=fc, total_tokens=55
    )

    tools = [{"type": "function", "function": {
        "name": "rename",
        "description": "Rename a file",
        "parameters": {"type": "object", "properties": {}},
    }}]
    resp = provider.chat(
        [{"role": "user", "content": "rename file"}],
        tools=tools,
    )

    assert resp.tool_call is not None
    assert resp.tool_call["name"] == "rename"
    assert resp.tool_call["arguments"] == {"filename": "report.pdf"}
    assert resp.tokens_used == 55


# ---------------------------------------------------------------------------
# Vision tests
# ---------------------------------------------------------------------------

def test_gemini_vision():
    provider, mock_client = _gemini_provider_with_mock_client()
    mock_client.models.generate_content.return_value = _make_gemini_response(
        text="A cat sitting on a table", total_tokens=70
    )

    resp = provider.vision(b"\x89PNG fake image bytes", "Describe this image")

    assert isinstance(resp, LLMResponse)
    assert resp.content == "A cat sitting on a table"
    assert resp.tokens_used == 70
    assert resp.model == "gemini-2.5-flash"
    mock_client.models.generate_content.assert_called_once()


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_gemini_not_available():
    with patch.dict("os.environ", {}, clear=True):
        provider = GeminiProvider(api_key=None)
        provider._api_key = None
        assert provider.is_available() is False


def test_gemini_available_with_key():
    provider = GeminiProvider(api_key="some-key")
    assert provider.is_available() is True


# ---------------------------------------------------------------------------
# Factory / get_provider
# ---------------------------------------------------------------------------

def test_get_provider_online_returns_gemini():
    """Online mode should prefer Gemini when a key is available."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False):
        provider = get_provider(online_mode=True)
        assert isinstance(provider, GeminiProvider)


def test_get_provider_online_falls_back_to_openai():
    """When no Gemini key is set, online mode falls back to OpenAI."""
    with patch.dict("os.environ", {}, clear=True):
        provider = get_provider(online_mode=True)
        from llm.openai_provider import OpenAIProvider
        assert isinstance(provider, OpenAIProvider)


def test_get_provider_by_name():
    provider = get_provider_by_name("gemini")
    assert isinstance(provider, GeminiProvider)

    provider = get_provider_by_name("openai")
    from llm.openai_provider import OpenAIProvider
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_by_name_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider_by_name("nonexistent")


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------

def test_convert_messages_roles():
    """Verify assistant -> model mapping and system extraction."""
    messages = [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Bye"},
    ]
    contents, sys_instr = GeminiProvider._convert_messages(messages)

    assert sys_instr == "Be concise."
    assert len(contents) == 3
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[2].role == "user"
