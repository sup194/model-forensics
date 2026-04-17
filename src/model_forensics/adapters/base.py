"""Base adapter definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from model_forensics.schemas import CompletionResponse, ModelTarget


class ModelAdapter(ABC):
    """Abstract chat adapter."""

    def __init__(self, target: ModelTarget) -> None:
        self.target = target
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.target.timeout_seconds),
                headers=self._build_headers(),
                trust_env=False,
            )
        return self._client

    @abstractmethod
    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""

    @abstractmethod
    async def complete(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        system_prompt: str = "",
    ) -> CompletionResponse:
        """Execute a chat request."""

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
