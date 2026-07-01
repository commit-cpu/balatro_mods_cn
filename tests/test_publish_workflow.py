from pathlib import Path
from typing import Any

from app.api.publish_workflow import publish_mod_to_fork
from app.db.connection import connect
from app.db.migrate import migrate


class FakeGitHubClient:
    def __init__(self) -> None:
        self.created_branches: list[tuple[str, str, str, str]] = []
        self.uploads: list[dict[str, Any]] = []

    def repo(self, owner: str, repo: str) -> dict[str, Any]:
        assert (owner, repo) == ("bot", "alpha")
        return {"default_branch": "main"}

    def create_branch(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        base_branch: str,
    ) -> bool:
        self.created_branches.append((owner, repo, branch, base_branch))
        return True

    def file_sha(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        assert (owner, repo, ref) == ("bot", "alpha", "bot/zh-cn/alpha_mod")
        assert path == "localization/zh_CN.lua"
        return "old-sha"

    def put_file(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        path: str,
        content: bytes,
        message: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        self.uploads.append(
            {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "path": path,
                "content": content,
                "message": message,
                "sha": sha,
            }
        )
        return {"commit": {"sha": "new-commit-sha"}}


def test_publish_mod_to_fork_commits_target_file_and_records_state(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "Alpha"
    target = repo_path / "localization" / "zh_CN.lua"
    target.parent.mkdir(parents=True)
    target.write_text("return { misc = { dictionary = { test = '测试' } } }\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.execute(
            """
            insert into mod_workflows(
                mod_id, upstream_url, fork_slug, fork_status, workflow_status, next_action
            ) values (
                'Alpha Mod', 'https://github.com/example/alpha',
                'bot/alpha', 'already_exists', 'applied', 'commit'
            )
            """
        )
        db.commit()
    client = FakeGitHubClient()

    result = publish_mod_to_fork(
        db_path=db_path,
        mod_id="alpha_mod",
        client=client,
    )

    assert result["repo_slug"] == "bot/alpha"
    assert result["branch"] == "bot/zh-cn/alpha_mod"
    assert result["commit_sha"] == "new-commit-sha"
    assert client.created_branches == [("bot", "alpha", "bot/zh-cn/alpha_mod", "main")]
    assert client.uploads[0]["path"] == "localization/zh_CN.lua"
    assert client.uploads[0]["sha"] == "old-sha"
    assert client.uploads[0]["content"] == target.read_bytes()

    with connect(db_path) as db:
        pr = db.execute(
            "select mod_id, repo_slug, branch, state, last_commit_sha from pull_requests"
        ).fetchone()
        workflow = db.execute(
            "select workflow_status, next_action from mod_workflows where mod_id = 'Alpha Mod'"
        ).fetchone()
    assert dict(pr) == {
        "mod_id": "alpha_mod",
        "repo_slug": "bot/alpha",
        "branch": "bot/zh-cn/alpha_mod",
        "state": "fork_committed",
        "last_commit_sha": "new-commit-sha",
    }
    assert dict(workflow) == {"workflow_status": "committed", "next_action": "pr"}


def test_publish_mod_to_fork_verifies_existing_fork_before_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "Alpha"
    target = repo_path / "localization" / "zh_CN.lua"
    target.parent.mkdir(parents=True)
    target.write_text("return { misc = { dictionary = { test = '测试' } } }\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.execute(
            """
            insert into mod_workflows(
                mod_id, upstream_url, fork_slug, fork_status, workflow_status, next_action
            ) values (
                'Alpha Mod', 'https://github.com/example/alpha',
                'bot/alpha', 'not_requested', 'probed', 'fork'
            )
            """
        )
        db.commit()
    client = FakeGitHubClient()

    result = publish_mod_to_fork(
        db_path=db_path,
        mod_id="alpha_mod",
        client=client,
    )

    assert result["commit_sha"] == "new-commit-sha"
    with connect(db_path) as db:
        workflow = db.execute(
            """
            select fork_status, workflow_status, next_action
            from mod_workflows
            where mod_id = 'Alpha Mod'
            """
        ).fetchone()
    assert dict(workflow) == {
        "fork_status": "already_exists",
        "workflow_status": "committed",
        "next_action": "pr",
    }
