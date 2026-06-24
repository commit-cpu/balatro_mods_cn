from pathlib import Path

from app.config import load_settings


def test_load_settings_reads_network_and_git_proxy_config() -> None:
    settings = load_settings(Path("config/app.yml"))

    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 8000
    assert settings.qdrant.url == "http://127.0.0.1:6333"
    assert settings.sqlite.database_path == "./data/balatro_cn.db"
    assert settings.embedding.provider == "ollama"
    assert settings.embedding.base_url == "http://127.0.0.1:11434"
    assert settings.embedding.model == "qwen3-embedding:8b"
    assert settings.embedding.batch_size == 16
    assert settings.git.clone_timeout_seconds == 600
    assert settings.git.http_proxy == "http://127.0.0.1:7890"
    assert settings.git.https_proxy == "http://127.0.0.1:7890"
    assert settings.git.no_proxy == "127.0.0.1,localhost"


def test_git_proxy_env_returns_cli_compatible_proxy_variables() -> None:
    settings = load_settings(Path("config/app.yml"))

    assert settings.git.proxy_env() == {
        "http_proxy": "http://127.0.0.1:7890",
        "https_proxy": "http://127.0.0.1:7890",
        "no_proxy": "127.0.0.1,localhost",
        "HTTP_PROXY": "http://127.0.0.1:7890",
        "HTTPS_PROXY": "http://127.0.0.1:7890",
        "NO_PROXY": "127.0.0.1,localhost",
    }
