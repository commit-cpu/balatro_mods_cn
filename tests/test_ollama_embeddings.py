import json

import httpx
import pytest

from app.rag.ollama_embeddings import (
    OllamaEmbeddingClient,
    OllamaEmbeddingError,
    OpenAICompatibleEmbeddingClient,
)


def test_default_ollama_client_ignores_proxy_environment(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")

    client = OllamaEmbeddingClient(
        base_url="http://127.0.0.1:11434",
        model="qwen3-embedding:8b",
    )

    assert client._client._trust_env is False


def test_embed_texts_calls_ollama_embed_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        model="qwen3-embedding:8b",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    vectors = client.embed_texts(["one", "two"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert requests[0].url.path == "/api/embed"
    assert requests[0].read() == b'{"model":"qwen3-embedding:8b","input":["one","two"]}'


def test_embedding_dimension_returns_vector_length() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        model="qwen3-embedding:8b",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.embedding_dimension() == 3


def test_embed_texts_rejects_invalid_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[]]})

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        model="qwen3-embedding:8b",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OllamaEmbeddingError):
        client.embed_texts(["bad"])


def test_openai_compatible_embed_texts_calls_embeddings_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ]
            },
        )

    client = OpenAICompatibleEmbeddingClient(
        base_url="https://ai.gitee.com/v1",
        api_key="test-key",
        model="Qwen3-Embedding-8B",
        dimensions=4096,
        instruction="检索 Balatro 汉化术语",
        failover_enabled=True,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    vectors = client.embed_texts(["one", "two"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert requests[0].url == "https://ai.gitee.com/v1/embeddings"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert requests[0].headers["x-failover-enabled"] == "true"
    assert json.loads(requests[0].read()) == {
        "model": "Qwen3-Embedding-8B",
        "input": ["one", "two"],
        "dimensions": 4096,
        "instruction": "检索 Balatro 汉化术语",
    }


def test_openai_compatible_embed_texts_rejects_invalid_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": []}]})

    client = OpenAICompatibleEmbeddingClient(
        base_url="https://ai.gitee.com/v1",
        api_key="test-key",
        model="Qwen3-Embedding-8B",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OllamaEmbeddingError):
        client.embed_texts(["bad"])
