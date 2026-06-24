"""Tests for ModConfig YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.github.mod_config import ModConfig


SAMPLE_YAML = """\
id: example_mod

origin:
  owner: upstream-owner
  repo: example-mod
  branch: main

fork:
  owner: your-bot-owner
  repo: example-mod

publish_mode: fork_only

source_locale_paths:
  - localization/en-us.lua
  - localization/en.lua

target_locale_path: localization/zh_CN.lua

poll_minutes: 360
parser_profile: steamodded_lua_v1
"""


@pytest.fixture
def sample_yaml_file(tmp_path: Path) -> Path:
    path = tmp_path / "example_mod.yaml"
    path.write_text(SAMPLE_YAML, encoding="utf-8")
    return path


class TestModConfig:
    def test_loads_from_yaml(self, sample_yaml_file: Path) -> None:
        cfg = ModConfig.from_yaml(sample_yaml_file)

        assert cfg.id == "example_mod"
        assert cfg.origin.owner == "upstream-owner"
        assert cfg.origin.repo == "example-mod"
        assert cfg.origin.branch == "main"
        assert cfg.origin.clone_url == "https://github.com/upstream-owner/example-mod.git"
        assert cfg.origin.slug == "upstream-owner/example-mod"
        assert cfg.fork.owner == "your-bot-owner"
        assert cfg.fork.repo == "example-mod"
        assert cfg.publish_mode == "fork_only"
        assert cfg.source_locale_paths == ["localization/en-us.lua", "localization/en.lua"]
        assert cfg.target_locale_path == "localization/zh_CN.lua"
        assert cfg.poll_minutes == 360
        assert cfg.parser_profile == "steamodded_lua_v1"

    def test_repo_dir_name(self, sample_yaml_file: Path) -> None:
        cfg = ModConfig.from_yaml(sample_yaml_file)
        assert cfg.repo_dir_name == "upstream-owner__example-mod"

    def test_load_all(self, tmp_path: Path) -> None:
        (tmp_path / "mod_a.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
        (tmp_path / "mod_b.yaml").write_text(
            SAMPLE_YAML.replace("example_mod", "other_mod")
            .replace("upstream-owner", "other-owner")
            .replace("example-mod", "other-repo"),
            encoding="utf-8",
        )
        configs = ModConfig.load_all(tmp_path)
        assert len(configs) == 2
        assert {c.id for c in configs} == {"example_mod", "other_mod"}

    def test_invalid_publish_mode_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text(SAMPLE_YAML.replace("fork_only", "unknown_mode"), encoding="utf-8")
        with pytest.raises(ValueError, match="publish_mode"):
            ModConfig.from_yaml(path)

    def test_missing_origin_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("id: foo\npublish_mode: disabled\n", encoding="utf-8")
        with pytest.raises(ValueError):
            ModConfig.from_yaml(path)
