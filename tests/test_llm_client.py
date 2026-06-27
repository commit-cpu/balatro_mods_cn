import httpx

from app.llm.client import OpenAICompatibleClient


def test_chat_json_does_not_force_response_format_by_default() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "{\"translation\":\"测试\"}",
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://llm.example/v1",
        api_key="key",
        model="custom-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.chat_json([{"role": "user", "content": "translate"}])

    assert result == {"translation": "测试"}
    assert b"response_format" not in requests[0]


def test_chat_json_retries_transient_read_timeout() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "{\"translation\":\"重试成功\"}",
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://llm.example/v1",
        api_key="key",
        model="custom-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_delay_seconds=0,
    )

    result = client.chat_json([{"role": "user", "content": "translate"}])

    assert result == {"translation": "重试成功"}
    assert attempts == 2


def test_default_timeout_is_180_seconds() -> None:
    client = OpenAICompatibleClient(
        base_url="https://llm.example/v1",
        api_key="key",
        model="custom-model",
    )

    assert client._client.timeout.read == 180.0
    client._client.close()
