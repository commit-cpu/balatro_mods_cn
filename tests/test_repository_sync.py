"""Tests for RepositorySyncer – uses a real local git repo as fixture."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from git import Repo

from app.config import GitSettings
from app.github.mod_config import GitRepoRef, ModConfig
from app.github.repository_sync import RepositorySyncer


@pytest.fixture
def git_settings(tmp_path: Path) -> GitSettings:
    return GitSettings(
        repos_dir=str(tmp_path / "repos"),
        clone_timeout_seconds=60,
        default_branch="main",
        http_proxy=None,
        https_proxy=None,
        no_proxy=None,
    )


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Repo:
    """Create a bare 'upstream' repo that we can clone from."""
    upstream_dir = tmp_path / "upstream.git"
    upstream_dir.mkdir()
    repo = Repo.init(str(upstream_dir), bare=True)

    # Clone the bare repo, add a commit, and push so there is content
    work_dir = tmp_path / "upstream_work"
    work = repo.clone(str(work_dir))

    (work_dir / "en.lua").write_text('return {name = "hello"}', encoding="utf-8")
    work.index.add(["en.lua"])
    work.index.commit("initial commit")
    work.remotes.origin.push("main")
    return repo


@pytest.fixture
def mod_config() -> ModConfig:
    return ModConfig(
        id="test_mod",
        origin=GitRepoRef(owner="fake", repo="test-mod", branch="main"),
        fork=GitRepoRef(owner="bot", repo="test-mod", branch="main"),
        publish_mode="fork_only",
        source_locale_paths=["localization/en.lua"],
        target_locale_path="localization/zh_CN.lua",
        poll_minutes=360,
        parser_profile="steamodded_lua_v1",
    )


class TestRepositorySyncer:
    def test_clone_creates_local_repo(
        self, git_settings: GitSettings, upstream_repo: Repo, mod_config: ModConfig
    ) -> None:
        syncer = RepositorySyncer(git_settings)
        url = str(upstream_repo.working_dir)
        with patch.object(GitRepoRef, "clone_url", new_callable=PropertyMock) as mock_url:
            mock_url.return_value = url
            repo = syncer.ensure_cloned(mod_config)

        assert repo.working_dir is not None
        assert Path(repo.working_dir, "en.lua").exists()
        assert not repo.head.is_detached

    def test_ensure_cloned_is_idempotent(
        self, git_settings: GitSettings, upstream_repo: Repo, mod_config: ModConfig
    ) -> None:
        syncer = RepositorySyncer(git_settings)
        url = str(upstream_repo.working_dir)
        with patch.object(GitRepoRef, "clone_url", new_callable=PropertyMock) as mock_url:
            mock_url.return_value = url
            repo1 = syncer.ensure_cloned(mod_config)
            repo2 = syncer.ensure_cloned(mod_config)
        assert repo1.working_dir == repo2.working_dir

    def test_fetch_updates_refs(
        self,
        git_settings: GitSettings,
        upstream_repo: Repo,
        mod_config: ModConfig,
        tmp_path: Path,
    ) -> None:
        syncer = RepositorySyncer(git_settings)
        url = str(upstream_repo.working_dir)
        with patch.object(GitRepoRef, "clone_url", new_callable=PropertyMock) as mock_url:
            mock_url.return_value = url
            repo = syncer.ensure_cloned(mod_config)

        # Push a new commit to upstream
        work_dir = tmp_path / "upstream_work2"
        work = upstream_repo.clone(str(work_dir))
        (work_dir / "new_file.lua").write_text("return {}", encoding="utf-8")
        work.index.add(["new_file.lua"])
        work.index.commit("second commit")
        work.remotes.origin.push("main")

        # Fetch into the clone
        syncer.fetch(repo, mod_config)
        latest = syncer.latest_commit_sha(repo, "origin/main")
        assert latest is not None
        assert len(latest) == 40  # full SHA

    def test_checkout_commit_detaches_head(
        self, git_settings: GitSettings, upstream_repo: Repo, mod_config: ModConfig
    ) -> None:
        syncer = RepositorySyncer(git_settings)
        url = str(upstream_repo.working_dir)
        with patch.object(GitRepoRef, "clone_url", new_callable=PropertyMock) as mock_url:
            mock_url.return_value = url
            repo = syncer.ensure_cloned(mod_config)

        sha = syncer.latest_commit_sha(repo, "origin/main")
        syncer.checkout_commit(repo, sha)
        assert repo.head.is_detached
        assert repo.head.commit.hexsha == sha

    def test_create_branch_and_push(
        self,
        git_settings: GitSettings,
        upstream_repo: Repo,
        mod_config: ModConfig,
    ) -> None:
        syncer = RepositorySyncer(git_settings)
        url = str(upstream_repo.working_dir)
        with patch.object(GitRepoRef, "clone_url", new_callable=PropertyMock) as mock_url:
            mock_url.return_value = url
            repo = syncer.ensure_cloned(mod_config)

        syncer.create_branch(repo, "bot/zh-cn/test_mod")
        assert "bot/zh-cn/test_mod" in repo.heads
        assert not repo.head.is_detached

        # Make a change and commit
        lua_path = Path(repo.working_dir, "zh_CN.lua")
        lua_path.write_text('return {name = "你好"}', encoding="utf-8")
        syncer.commit_file(repo, "zh_CN.lua", "Add CN translation")

        # Push should succeed (pushing to the local bare repo)
        syncer.push(repo, "bot/zh-cn/test_mod")
