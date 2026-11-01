from .base import LLMProvider, LLMResponse
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider


def get_provider(online_mode: bool = True) -> LLMProvider:
    """Return the appropriate LLM provider based on mode."""
    if online_mode:
        return OpenAIProvider()
    return OllamaProvider()


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "OllamaProvider",
    "get_provider",
]
