"""Tests for the LLM provider layer (llm/ package)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from llm import get_provider, LLMResponse
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider
from llm.gemini_provider import GeminiProvider


# ---------------------------------------------------------------------------
# get_provider factory
# ---------------------------------------------------------------------------

def test_get_provider_online():
    """Online mode returns Gemini when its key is set, otherwise OpenAI."""
    provider = get_provider(True)
    assert isinstance(provider, (GeminiProvider, OpenAIProvider))


def test_get_provider_offline():
    provider = get_provider(False)
    assert isinstance(provider, OllamaProvider)


# ---------------------------------------------------------------------------
# LLMResponse dataclass defaults
# ---------------------------------------------------------------------------

def test_llm_response_dataclass():
    resp = LLMResponse()
    assert resp.content == ""
    assert resp.tool_call is None
    assert resp.tokens_used == 0
    assert resp.model == ""
    assert resp.latency_ms == 0


# ---------------------------------------------------------------------------
# OpenAI provider helpers
# ---------------------------------------------------------------------------

def _make_openai_raw(content="hello", tool_calls=None, total_tokens=42):
    """Build a fake OpenAI chat completion response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.total_tokens = total_tokens

    raw = MagicMock()
    raw.choices = [choice]
    raw.usage = usage
    return raw


def _openai_provider_with_mock_client():
    """Create an OpenAIProvider with a pre-injected mock client."""
    provider = OpenAIProvider(api_key="sk-test")
    mock_client = MagicMock()
    provider._client = mock_client  # bypass lazy _get_client
    return provider, mock_client


# ---------------------------------------------------------------------------
# OpenAI provider tests
# ---------------------------------------------------------------------------

def test_openai_chat():
    provider, mock_client = _openai_provider_with_mock_client()
    mock_client.chat.completions.create.return_value = _make_openai_raw(
        content="Sure thing", total_tokens=100
    )

    resp = provider.chat([{"role": "user", "content": "hi"}])

    assert isinstance(resp, LLMResponse)
    assert resp.content == "Sure thing"
    assert resp.tool_call is None
    assert resp.tokens_used == 100
    assert resp.model == "gpt-4o-mini"
    assert resp.latency_ms >= 0
    mock_client.chat.completions.create.assert_called_once()


def test_openai_chat_with_tools():
    provider, mock_client = _openai_provider_with_mock_client()

    tool_args = {"filename": "report.pdf"}
    tc = MagicMock()
    tc.function.arguments = json.dumps(tool_args)

    mock_client.chat.completions.create.return_value = _make_openai_raw(
        content="", tool_calls=[tc], total_tokens=55
    )

    tools = [{"type": "function", "function": {"name": "rename", "parameters": {}}}]
    resp = provider.chat(
        [{"role": "user", "content": "rename file"}],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "rename"}},
    )

    assert resp.tool_call == tool_args
    assert isinstance(resp.tool_call, dict)
    assert resp.tokens_used == 55


def test_openai_vision():
    provider, mock_client = _openai_provider_with_mock_client()
    mock_client.chat.completions.create.return_value = _make_openai_raw(
        content="A cat sitting on a table", total_tokens=80
    )

    resp = provider.vision(b"\x89PNG fake image bytes", "Describe this image")

    assert isinstance(resp, LLMResponse)
    assert resp.content == "A cat sitting on a table"
    assert resp.tokens_used == 80
    assert resp.model == "gpt-4o-mini"
    mock_client.chat.completions.create.assert_called_once()


def test_openai_not_available():
    with patch.dict("os.environ", {}, clear=True):
        provider = OpenAIProvider(api_key=None)
        # Manually clear in case env had the key before construction
        provider._api_key = None
        assert provider.is_available() is False


# ---------------------------------------------------------------------------
# Ollama provider helpers
# ---------------------------------------------------------------------------

def _make_ollama_raw(content="hello", eval_count=30):
    return {
        "message": {"content": content},
        "eval_count": eval_count,
    }


def _ollama_provider_with_mock_client():
    """Create an OllamaProvider with a pre-injected mock client."""
    provider = OllamaProvider()
    mock_client = MagicMock()
    provider._client = mock_client  # bypass lazy _get_client
    return provider, mock_client


# ---------------------------------------------------------------------------
# Ollama provider tests
# ---------------------------------------------------------------------------

def test_ollama_chat():
    provider, mock_client = _ollama_provider_with_mock_client()
    mock_client.chat.return_value = _make_ollama_raw(
        content="Ollama says hi", eval_count=25
    )

    resp = provider.chat([{"role": "user", "content": "hello"}])

    assert isinstance(resp, LLMResponse)
    assert resp.content == "Ollama says hi"
    assert resp.tokens_used == 25
    assert resp.model == "mistral"
    assert resp.latency_ms >= 0
    mock_client.chat.assert_called_once()


def test_ollama_vision_fallback():
    provider, mock_client = _ollama_provider_with_mock_client()

    # First model (moondream) fails, second (llama3.2-vision) succeeds
    def side_effect(**kwargs):
        if kwargs.get("model") == "moondream":
            raise ConnectionError("moondream not available")
        return _make_ollama_raw(content="A dog playing fetch", eval_count=40)

    mock_client.chat.side_effect = side_effect

    resp = provider.vision(b"\x89PNG fake image", "What is in this image?")

    assert resp.content == "A dog playing fetch"
    assert resp.model == "llama3.2-vision"
    assert resp.tokens_used == 40
    assert mock_client.chat.call_count == 2
