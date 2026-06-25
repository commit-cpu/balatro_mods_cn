from __future__ import annotations

from typing import Any

import httpx


class LlmClientError(RuntimeError):
    """Raised when the LLM API response is invalid."""


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = http_client or httpx.Client(timeout=timeout)

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": messages,
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmClientError("Invalid chat completion response") from exc

        if isinstance(content, dict):
            return content

        import json

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmClientError("LLM did not return valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LlmClientError("LLM JSON response must be an object")
        return parsed
