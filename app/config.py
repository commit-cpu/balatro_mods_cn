from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml


T = TypeVar("T")
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int


@dataclass(frozen=True)
class WorkerSettings:
    name: str
    poll_interval_seconds: int
    max_retry_attempts: int
    job_visibility_timeout_seconds: int


@dataclass(frozen=True)
class SQLiteSettings:
    database_path: str
    busy_timeout_ms: int
    journal_mode: str
    synchronous: str


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    grpc_url: str
    collection: str
    timeout_seconds: int


@dataclass(frozen=True)
class GitSettings:
    repos_dir: str
    clone_timeout_seconds: int
    default_branch: str
    http_proxy: str | None
    https_proxy: str | None
    no_proxy: str | None

    def proxy_env(self) -> dict[str, str]:
        pairs = {
            "http_proxy": self.http_proxy,
            "https_proxy": self.https_proxy,
            "no_proxy": self.no_proxy,
        }
        env = {key: value for key, value in pairs.items() if value}
        env.update({key.upper(): value for key, value in env.items()})
        return env


@dataclass(frozen=True)
class ModelSettings:
    model: str
    device: str


@dataclass(frozen=True)
class EmbeddingSettings(ModelSettings):
    batch_size: int


@dataclass(frozen=True)
class RerankerSettings(ModelSettings):
    use_fp16: bool


@dataclass(frozen=True)
class RagSettings:
    dense_top_k: int
    fts_top_k: int
    rerank_top_k: int
    reference_limit: int


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    translation_model: str
    review_model: str


@dataclass(frozen=True)
class GithubSettings:
    bot_owner: str


@dataclass(frozen=True)
class SchedulerSettings:
    enabled: bool
    poll_minutes: int


@dataclass(frozen=True)
class AppSettings:
    env: str
    data_dir: str
    api: ApiSettings
    worker: WorkerSettings
    sqlite: SQLiteSettings
    qdrant: QdrantSettings
    embedding: EmbeddingSettings
    reranker: RerankerSettings
    rag: RagSettings
    llm: LlmSettings
    git: GitSettings
    github: GithubSettings
    scheduler: SchedulerSettings


def load_settings(path: Path | str = Path("config/app.yml")) -> AppSettings:
    config_path = Path(path)
    raw = yaml.safe_load(_expand_env(config_path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ValueError(f"Settings file is empty or invalid: {config_path}")

    app = _section(raw, "app")
    return AppSettings(
        env=_value(app, "env", str),
        data_dir=_value(app, "data_dir", str),
        api=ApiSettings(**_section(raw, "api")),
        worker=WorkerSettings(**_section(raw, "worker")),
        sqlite=SQLiteSettings(**_section(raw, "sqlite")),
        qdrant=QdrantSettings(**_section(raw, "qdrant")),
        embedding=EmbeddingSettings(**_section(raw, "embedding")),
        reranker=RerankerSettings(**_section(raw, "reranker")),
        rag=RagSettings(**_section(raw, "rag")),
        llm=LlmSettings(**_section(raw, "llm")),
        git=GitSettings(**_section(raw, "git")),
        github=GithubSettings(**_section(raw, "github")),
        scheduler=SchedulerSettings(**_section(raw, "scheduler")),
    )


def _expand_env(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        default = match.group(2)
        return os.environ.get(name, default or "")

    return _ENV_PATTERN.sub(replace, text)


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Missing settings section: {name}")
    return value


def _value(raw: dict[str, Any], name: str, expected_type: type[T]) -> T:
    value = raw.get(name)
    if not isinstance(value, expected_type):
        raise ValueError(f"Missing or invalid settings value: {name}")
    return value
