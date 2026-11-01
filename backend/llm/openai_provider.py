import os
import json
import base64
import logging
from typing import Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_VISION_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            if not self._api_key:
                raise ValueError("OPENAI_API_KEY is not set")
            self._client = OpenAI(api_key=self._api_key)
            logger.info("OpenAI client initialized")
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

        kwargs = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format

        def _call():
            return client.chat.completions.create(**kwargs)

        raw, latency = self._timed(_call)
        return self._parse_chat(raw, model, latency)

    @staticmethod
    def _parse_chat(raw, model, latency) -> LLMResponse:
        msg = raw.choices[0].message
        tool_call = None
        content = msg.content or ""
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_call = json.loads(tc.function.arguments)
        tokens = raw.usage.total_tokens if raw.usage else 0
        return LLMResponse(
            content=content,
            tool_call=tool_call,
            tokens_used=tokens,
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
        model = model or DEFAULT_VISION_MODEL
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": detail,
                    },
                },
            ],
        }]

        kwargs = dict(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        def _call():
            return client.chat.completions.create(**kwargs)

        raw, latency = self._timed(_call)
        return self._parse_chat(raw, model, latency)

    # -- meta ----------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key or os.getenv("OPENAI_API_KEY"))

    @property
    def name(self) -> str:
        return "openai"
