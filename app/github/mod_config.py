"""Mod configuration model and YAML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


PublishMode = Literal["fork_only", "upstream_pr", "disabled"]


@dataclass(frozen=True)
class GitRepoRef:
    """Identifies a GitHub repository and branch."""

    owner: str
    repo: str
    branch: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class ModConfig:
    """Configuration for a single mod tracked by the system."""

    id: str
    origin: GitRepoRef
    fork: GitRepoRef
    publish_mode: PublishMode
    source_locale_paths: list[str]
    target_locale_path: str
    poll_minutes: int
    parser_profile: str

    @classmethod
    def from_yaml(cls, path: Path | str) -> ModConfig:
        """Load a mod config from a YAML file."""
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Mod config is empty or invalid: {path}")

        origin = raw.get("origin", {})
        fork = raw.get("fork", {})

        return cls(
            id=_require_str(raw, "id"),
            origin=GitRepoRef(
                owner=_require_str(origin, "owner"),
                repo=_require_str(origin, "repo"),
                branch=_require_str(origin, "branch"),
            ),
            fork=GitRepoRef(
                owner=_require_str(fork, "owner"),
                repo=_require_str(fork, "repo"),
                branch=_require_str(origin, "branch"),  # fork tracks the same branch name
            ),
            publish_mode=_require_publish_mode(raw, "publish_mode"),
            source_locale_paths=_require_str_list(raw, "source_locale_paths"),
            target_locale_path=_require_str(raw, "target_locale_path"),
            poll_minutes=int(raw.get("poll_minutes", 360)),
            parser_profile=_require_str(raw, "parser_profile"),
        )

    @classmethod
    def load_all(cls, config_dir: Path) -> list[ModConfig]:
        """Load all mod config YAML files from a directory."""
        mods: list[ModConfig] = []
        for yaml_path in sorted(config_dir.glob("*.yaml")):
            mods.append(cls.from_yaml(yaml_path))
        return mods

    @property
    def repo_dir_name(self) -> str:
        """Directory name for the local clone of this mod's origin repo."""
        return f"{self.origin.owner}__{self.origin.repo}"


def _require_str(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or empty config key: {key}")
    return value


def _require_str_list(raw: dict, key: str) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"Missing or invalid config key: {key} (expected list of strings)")
    return value


def _require_publish_mode(raw: dict, key: str) -> PublishMode:
    value = raw.get(key)
    if value not in ("fork_only", "upstream_pr", "disabled"):
        raise ValueError(
            f"Invalid publish_mode: {value!r} (expected fork_only, upstream_pr, or disabled)"
        )
    return value
