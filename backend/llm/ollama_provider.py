import os
import json
import base64
import logging
from typing import Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "mistral"
DEFAULT_VISION_MODEL = "llama3.2-vision"
OLLAMA_HOST = "http://localhost:11434"
VISION_MODELS = ("moondream", "llama3.2-vision")


class OllamaProvider(LLMProvider):

    def __init__(self, host: Optional[str] = None):
        self._host = host or OLLAMA_HOST
        self._client = None

    def _get_client(self):
        if self._client is None:
            from ollama import Client
            self._client = Client(host=self._host)
            logger.info("Ollama client initialized")
        return self._client

    # -- chat ----------------------------------------------------------------

    def chat(
        self,
        messages,
        *,
        model=None,
        temperature=0,
        max_tokens=256,
        tools=None,
        tool_choice=None,
        response_format=None,
    ) -> LLMResponse:
        client = self._get_client()
        model = model or DEFAULT_CHAT_MODEL

        options = {"temperature": temperature, "num_predict": max_tokens}

        def _call():
            return client.chat(model=model, messages=messages, options=options)

        raw, latency = self._timed(_call)

        content = raw["message"]["content"].strip()
        return LLMResponse(
            content=content,
            tokens_used=raw.get("eval_count", 0),
            model=model,
            latency_ms=latency,
        )

    # -- vision --------------------------------------------------------------

    def vision(
        self,
        image_bytes,
        prompt,
        *,
        model=None,
        tools=None,
        tool_choice=None,
        max_tokens=300,
        detail="low",
    ) -> LLMResponse:
        client = self._get_client()
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        models_to_try = [model] if model else list(VISION_MODELS)

        for m in models_to_try:
            try:
                def _call():
                    return client.chat(
                        model=m,
                        messages=[{
                            "role": "user",
                            "content": prompt,
                            "images": [b64],
                        }],
                        options={
                            "temperature": 0,
                            "num_predict": max_tokens,
                            "num_thread": 4,
                        },
                        keep_alive="5m",
                    )

                raw, latency = self._timed(_call)
                content = raw["message"]["content"].strip()
                if content:
                    return LLMResponse(
                        content=content,
                        tokens_used=raw.get("eval_count", 0),
                        model=m,
                        latency_ms=latency,
                    )
            except Exception as e:
                logger.warning(f"{m} not available: {e}")
                continue

        return LLMResponse(content="", model="none", latency_ms=0)

    # -- meta ----------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            client = self._get_client()
            client.list()
            return True
        except Exception:
            return False

    @property
    def name(self) -> str:
        return "ollama"
