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
