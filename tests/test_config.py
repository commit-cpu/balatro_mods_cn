from pathlib import Path

from app.config import load_settings


def test_load_settings_reads_network_and_git_proxy_config(monkeypatch) -> None:
    monkeypatch.delenv("GIT_HTTP_PROXY", raising=False)
    monkeypatch.delenv("GIT_HTTPS_PROXY", raising=False)
    monkeypatch.delenv("GIT_NO_PROXY", raising=False)

    settings = load_settings(Path("config/app.yml"))

    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 8000
    assert settings.qdrant.url == "http://127.0.0.1:6333"
    assert settings.sqlite.database_path == "./data/balatro_cn.db"
    assert settings.embedding.provider == "ollama"
    assert settings.embedding.base_url == "http://127.0.0.1:11434"
    assert settings.embedding.model == "qwen3-embedding:8b"
    assert settings.embedding.batch_size == 16
    assert settings.embedding.api_key_env == "EMBEDDING_API_KEY"
    assert settings.embedding.dimensions is None
    assert settings.embedding.instruction == ""
    assert settings.embedding.failover_enabled is False
    assert settings.git.clone_timeout_seconds == 600
    assert settings.git.http_proxy == "http://127.0.0.1:7890"
    assert settings.git.https_proxy == "http://127.0.0.1:7890"
    assert settings.git.no_proxy == "127.0.0.1,localhost"


def test_git_proxy_env_returns_cli_compatible_proxy_variables(monkeypatch) -> None:
    monkeypatch.delenv("GIT_HTTP_PROXY", raising=False)
    monkeypatch.delenv("GIT_HTTPS_PROXY", raising=False)
    monkeypatch.delenv("GIT_NO_PROXY", raising=False)

    settings = load_settings(Path("config/app.yml"))

    assert settings.git.proxy_env() == {
        "http_proxy": "http://127.0.0.1:7890",
        "https_proxy": "http://127.0.0.1:7890",
        "no_proxy": "127.0.0.1,localhost",
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "HTTPS_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "127.0.0.1,localhost",
    }


def test_load_settings_reads_openai_compatible_embedding_config(tmp_path: Path) -> None:
    config = tmp_path / "app.yml"
    config.write_text(
        """
app: {env: development, data_dir: ./data}
api: {host: 127.0.0.1, port: 8000}
worker:
  name: worker
  poll_interval_seconds: 5
  max_retry_attempts: 3
  job_visibility_timeout_seconds: 900
sqlite:
  database_path: ./data/test.db
  busy_timeout_ms: 5000
  journal_mode: WAL
  synchronous: NORMAL
qdrant:
  url: http://127.0.0.1:6333
  grpc_url: http://127.0.0.1:6334
  collection: tm_test
  timeout_seconds: 30
embedding:
  provider: openai-compatible
  base_url: https://ai.gitee.com/v1
  model: Qwen3-Embedding-8B
  batch_size: 16
  api_key_env: GITEE_AI_API_KEY
  dimensions: 4096
  instruction: 指令：用于 Balatro 汉化 translation memory 检索。
  failover_enabled: true
reranker: {model: BAAI/bge-reranker-v2-m3, device: cuda, use_fp16: true}
rag: {dense_top_k: 30, fts_top_k: 20, rerank_top_k: 16, reference_limit: 4}
llm: {base_url: https://api.openai.com/v1, translation_model: gpt-4.1-mini, review_model: gpt-4.1-mini}
git:
  repos_dir: ./data/repos
  clone_timeout_seconds: 600
  default_branch: main
  http_proxy:
  https_proxy:
  no_proxy:
github: {bot_owner: bot}
scheduler: {enabled: false, poll_minutes: 360}
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.embedding.provider == "openai-compatible"
    assert settings.embedding.base_url == "https://ai.gitee.com/v1"
    assert settings.embedding.model == "Qwen3-Embedding-8B"
    assert settings.embedding.api_key_env == "GITEE_AI_API_KEY"
    assert settings.embedding.dimensions == 4096
    assert settings.embedding.instruction.startswith("指令：")
    assert settings.embedding.failover_enabled is True
