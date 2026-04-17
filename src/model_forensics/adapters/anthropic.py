"""Anthropic-compatible adapter."""

from __future__ import annotations

import time

import httpx

from model_forensics.config import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from model_forensics.schemas import CompletionResponse, ModelTarget

from .base import ModelAdapter


class AnthropicAdapter(ModelAdapter):
    """Anthropic Messages API adapter."""

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(self, target: ModelTarget) -> None:
        normalized = target.model_copy(
            update={"base_url": target.base_url or self.DEFAULT_BASE_URL}
        )
        super().__init__(normalized)

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "x-api-key": self.target.api_key,
            "anthropic-version": self.API_VERSION,
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
        payload: dict[str, object] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE,
        }
        if system_prompt:
            payload["system"] = system_prompt

        client = await self._get_client()
        started = time.perf_counter()
        try:
            response = await client.post(f"{self.target.base_url.rstrip('/')}/v1/messages", json=payload)
            response.raise_for_status()
            latency_ms = (time.perf_counter() - started) * 1000
            data = response.json()
            return self._parse_response(data, latency_ms)
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return CompletionResponse(text="", latency_ms=latency_ms, error=str(exc))

    def _parse_response(self, data: dict[str, object], latency_ms: float) -> CompletionResponse:
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)

        usage = data.get("usage", {})
        raw_model_name = data.get("model")
        return CompletionResponse(
            text="".join(text_parts),
            prompt_tokens=_maybe_int(usage, "input_tokens"),
            completion_tokens=_maybe_int(usage, "output_tokens"),
            total_tokens=None,
            latency_ms=latency_ms,
            raw_model_name=raw_model_name if isinstance(raw_model_name, str) else None,
            raw_response=data,
        )


def _maybe_int(payload: object, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value if isinstance(value, int) else None
