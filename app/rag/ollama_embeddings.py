from __future__ import annotations

from typing import Any

import httpx


class OllamaEmbeddingError(RuntimeError):
    """Raised when an embedding provider returns an invalid response."""


class OllamaEmbeddingClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        http_client: httpx.Client | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = http_client or httpx.Client(timeout=timeout, trust_env=False)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        return _validate_embeddings(embeddings, expected_count=len(texts))

    def embedding_dimension(self) -> int:
        return len(self.embed_texts(["dimension probe"])[0])


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        instruction: str = "",
        failover_enabled: bool = False,
        http_client: httpx.Client | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._instruction = instruction
        self._failover_enabled = failover_enabled
        self._client = http_client or httpx.Client(timeout=timeout)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        if self._dimensions is not None:
            payload["dimensions"] = self._dimensions
        if self._instruction:
            payload["instruction"] = self._instruction

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._failover_enabled:
            headers["X-Failover-Enabled"] = "true"

        response = self._client.post(
            f"{self._base_url}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = _openai_embedding_vectors(data)
        return _validate_embeddings(embeddings, expected_count=len(texts))

    def embedding_dimension(self) -> int:
        return len(self.embed_texts(["dimension probe"])[0])


def _openai_embedding_vectors(data: Any) -> Any:
    if not isinstance(data, dict):
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        return None
    return [row.get("embedding") if isinstance(row, dict) else None for row in rows]


def _validate_embeddings(value: Any, *, expected_count: int) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != expected_count:
        raise OllamaEmbeddingError(
            f"Invalid embeddings response: expected {expected_count} vectors"
        )

    vectors: list[list[float]] = []
    for vector in value:
        if not isinstance(vector, list) or not vector:
            raise OllamaEmbeddingError("Invalid embeddings response: empty vector")
        converted: list[float] = []
        for item in vector:
            if not isinstance(item, int | float):
                raise OllamaEmbeddingError("Invalid embeddings response: non-numeric value")
            converted.append(float(item))
        vectors.append(converted)
    return vectors
