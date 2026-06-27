from __future__ import annotations

import time
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
        timeout: float = 180.0,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = http_client or httpx.Client(timeout=timeout)
        self._max_retries = max(0, max_retries)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = self._post_chat_completion(messages)
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

    def _post_chat_completion(self, messages: list[dict[str, str]]) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
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
                return response
            except httpx.HTTPStatusError as exc:
                if not _is_retryable_status(exc.response.status_code):
                    raise
                if attempt >= self._max_retries:
                    raise
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self._max_retries:
                    raise
            self._sleep_before_retry(attempt)

        raise RuntimeError("unreachable")

    def _sleep_before_retry(self, attempt: int) -> None:
        if self._retry_delay_seconds <= 0:
            return
        time.sleep(self._retry_delay_seconds * (2**attempt))


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600
