import httpx
import pytest

from app.rag.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingError


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
