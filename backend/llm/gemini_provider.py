"""Gemini LLM provider using the google-genai SDK.

Requires: pip install google-genai>=1.0,<4
Env var:  GEMINI_API_KEY
"""

import os
import base64
import logging
from typing import Optional

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "gemini-2.5-flash"
DEFAULT_VISION_MODEL = "gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"


class GeminiProvider(LLMProvider):

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            if not self._api_key:
                raise ValueError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=self._api_key)
            logger.info("Gemini client initialized")
        return self._client

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _convert_messages(messages: list[dict]):
        """Convert OpenAI-style messages to Gemini contents + system_instruction.

        OpenAI uses roles: system, user, assistant.
        Gemini uses roles: user, model (system goes to system_instruction).
        """
        from google.genai import types

        system_parts = []
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")

            if role == "system":
                system_parts.append(text)
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append(
                    types.Content(
                        role=gemini_role,
                        parts=[types.Part.from_text(text=text)],
                    )
                )

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return contents, system_instruction

    @staticmethod
    def _convert_tools(tools: list[dict]):
        """Convert OpenAI-format tool definitions to Gemini FunctionDeclarations.

        OpenAI format:
            {"type": "function", "function": {"name": ..., "description": ...,
             "parameters": {...}}}

        Gemini format:
            types.FunctionDeclaration(name=..., description=..., parameters=...)
        """
        from google.genai import types

        declarations = []
        for tool in tools:
            func = tool.get("function", tool)
            declarations.append(
                types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=func.get("parameters"),
                )
            )
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def _extract_tool_call(response) -> Optional[dict]:
        """Pull the first function_call from a Gemini response, if present."""
        try:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    return {
                        "name": fc.name,
                        "arguments": dict(fc.args) if fc.args else {},
                    }
        except (IndexError, AttributeError):
            pass
        return None

    @staticmethod
    def _token_count(response) -> int:
        """Extract total token count from response usage metadata."""
        try:
            return response.usage_metadata.total_token_count
        except AttributeError:
            return 0

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
        from google.genai import types

        client = self._get_client()
        model = model or DEFAULT_CHAT_MODEL

        contents, system_instruction = self._convert_messages(messages)

        config_kwargs = dict(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            config_kwargs["tools"] = self._convert_tools(tools)
        if response_format and response_format.get("type") == "json_object":
            config_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_kwargs)

        def _call():
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        raw, latency = self._timed(_call)
        return self._parse_response(raw, model, latency)

    def _parse_response(self, raw, model, latency) -> LLMResponse:
        tool_call = self._extract_tool_call(raw)
        content = ""
        try:
            content = raw.text or ""
        except (AttributeError, ValueError):
            # .text raises ValueError when the response has no text parts
            pass

        return LLMResponse(
            content=content,
            tool_call=tool_call,
            tokens_used=self._token_count(raw),
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
        from google.genai import types

        client = self._get_client()
        model = model or DEFAULT_VISION_MODEL

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                ],
            )
        ]

        config_kwargs = dict(
            temperature=0,
            max_output_tokens=max_tokens,
        )
        if tools:
            config_kwargs["tools"] = self._convert_tools(tools)

        config = types.GenerateContentConfig(**config_kwargs)

        def _call():
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        raw, latency = self._timed(_call)
        return self._parse_response(raw, model, latency)

    # -- meta ----------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key or os.getenv("GEMINI_API_KEY"))

    @property
    def name(self) -> str:
        return "gemini"
