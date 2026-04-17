"""OpenAI-compatible adapters."""

from __future__ import annotations

import time

import httpx

from model_forensics.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)
from model_forensics.schemas import CompletionResponse, ModelTarget

from .base import ModelAdapter


class OpenAIAdapter(ModelAdapter):
    """Official OpenAI Chat Completions adapter."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, target: ModelTarget) -> None:
        normalized = target.model_copy(
            update={"base_url": target.base_url or self.DEFAULT_BASE_URL}
        )
        super().__init__(normalized)

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.target.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.target.extra_headers)
        return headers

    async def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        system_prompt: str = "",
    ) -> CompletionResponse:
        request_messages = list(messages)
        if system_prompt:
            request_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": model_name,
            "messages": request_messages,
            "temperature": DEFAULT_TEMPERATURE,
            "top_p": DEFAULT_TOP_P,
            "max_tokens": DEFAULT_MAX_TOKENS,
        }

        client = await self._get_client()
        started = time.perf_counter()
        try:
            response = await client.post(f"{self.target.base_url.rstrip('/')}/chat/completions", json=payload)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - started) * 1000
            data = response.json()
            return self._parse_response(data, latency_ms)
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return CompletionResponse(
                text="",
                latency_ms=latency_ms,
                error=str(exc),
            )

    def _parse_response(self, data: dict[str, object], latency_ms: float) -> CompletionResponse:
        usage = data.get("usage", {})
        choices = data.get("choices", [])
        text = ""
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content", "")
                    if isinstance(content, str):
                        text = content
        raw_model_name = data.get("model")
        return CompletionResponse(
            text=text,
            prompt_tokens=_maybe_int(usage, "prompt_tokens"),
            completion_tokens=_maybe_int(usage, "completion_tokens"),
            total_tokens=_maybe_int(usage, "total_tokens"),
            latency_ms=latency_ms,
            raw_model_name=raw_model_name if isinstance(raw_model_name, str) else None,
            raw_response=data,
        )


class GenericOpenAIAdapter(OpenAIAdapter):
    """OpenAI-compatible custom endpoint adapter."""

    def __init__(self, target: ModelTarget) -> None:
        if not target.base_url:
            msg = "base_url is required for generic OpenAI-compatible targets"
            raise ValueError(msg)
        super().__init__(target)


def _maybe_int(payload: object, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value if isinstance(value, int) else None
