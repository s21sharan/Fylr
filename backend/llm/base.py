from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: str = ""
    tool_call: Optional[dict] = None
    tokens_used: int = 0
    model: str = ""
    latency_ms: float = 0


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0,
        max_tokens: int = 256,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        max_tokens: int = 300,
        detail: str = "low",
    ) -> LLMResponse:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def _timed(self, fn):
        """Helper: call fn, measure wall-clock ms, return (result, ms)."""
        start = time.perf_counter()
        result = fn()
        elapsed = (time.perf_counter() - start) * 1000
        return result, elapsed
