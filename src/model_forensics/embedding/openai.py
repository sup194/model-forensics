"""OpenAI embedding client."""

from __future__ import annotations

import hashlib

import httpx

from model_forensics.config import DEFAULT_EMBEDDING_MODEL


class OpenAIEmbeddingClient:
    """Async client for OpenAI text embeddings."""

    def __init__(self, api_key: str, model: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._cache: dict[str, list[float]] = {}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            trust_env=False,
        )

    async def embed_text(self, text: str) -> list[float] | None:
        """Embed one text value."""
        cache_key = f"{self._model}:{hashlib.md5(text.encode()).hexdigest()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        response = await self._client.post(
            "https://api.openai.com/v1/embeddings",
            json={"model": self._model, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        embedding_data = data.get("data", [])
        if not isinstance(embedding_data, list) or not embedding_data:
            return None
        first = embedding_data[0]
        if not isinstance(first, dict):
            return None
        embedding = first.get("embedding")
        if not isinstance(embedding, list):
            return None
        numeric_embedding = [float(value) for value in embedding]
        self._cache[cache_key] = numeric_embedding
        return numeric_embedding

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
