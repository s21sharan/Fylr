from .base import LLMProvider, LLMResponse
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider
from .gemini_provider import GeminiProvider

_PROVIDERS = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(online_mode: bool = True) -> LLMProvider:
    """Return the appropriate LLM provider based on mode.

    When online, defaults to Gemini. Falls back to OpenAI if the Gemini key
    is not configured.
    """
    if online_mode:
        gemini = GeminiProvider()
        if gemini.is_available():
            return gemini
        return OpenAIProvider()
    return OllamaProvider()


def resolve_provider(online_mode: bool = True, provider_name: str | None = None) -> LLMProvider:
    """Pick provider from an explicit name or fall back to mode-based default.

    This is the preferred entry point when reading from a config dict:
        provider = resolve_provider(config.get('online_mode', True),
                                    config.get('provider'))
    """
    if provider_name:
        return get_provider_by_name(provider_name)
    return get_provider(online_mode)


def get_provider_by_name(name: str) -> LLMProvider:
    """Return a provider by explicit name ("gemini", "openai", "ollama")."""
    cls = _PROVIDERS.get(name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown provider {name!r}. "
            f"Choose from: {', '.join(_PROVIDERS)}"
        )
    return cls()


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "OllamaProvider",
    "GeminiProvider",
    "get_provider",
    "get_provider_by_name",
    "resolve_provider",
]
