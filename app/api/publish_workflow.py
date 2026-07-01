from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from app.api.github_workflow import _github_token
from app.api.repositories import ApiRepository
from app.db.connection import connect
from app.github.no_clone_l10n_probe import GitHubApi


PUBLISH_BRANCH_PREFIX = "bot/zh-cn"


def publish_mod_to_fork(
    *,
    db_path: Path,
    mod_id: str,
    client: Any | None = None,
) -> dict[str, Any]:
    repo = ApiRepository(db_path)
    mod = repo.get_mod(mod_id)
    if mod is None:
        raise KeyError(mod_id)
    workflow = _workflow_for_mod(db_path, mod)
    fork_slug = workflow.get("fork_slug")
    if not isinstance(fork_slug, str) or "/" not in fork_slug:
        raise ValueError("selected mod has no verified fork")

    fork_owner, fork_repo = fork_slug.split("/", 1)
    branch = f"{PUBLISH_BRANCH_PREFIX}/{mod_id}"
    repo_path = Path(str(mod["repo_path"]))
    target_path = str(mod["target_locale_path"])
    target_file = repo_path / target_path
    if not target_file.exists():
        raise ValueError(f"target localization file does not exist: {target_file}")
    content = target_file.read_bytes()

    owns_client = client is None
    client = client or GitHubApi(_github_token())
    try:
        fork_meta = client.repo(fork_owner, fork_repo)
        if workflow.get("fork_status") not in {"already_exists", "created"}:
            _mark_fork_verified(
                db_path=db_path,
                workflow_mod_id=str(workflow["mod_id"]),
            )
            workflow["fork_status"] = "already_exists"
        default_branch = str(fork_meta.get("default_branch") or "main")
        client.create_branch(
            fork_owner,
            fork_repo,
            branch=branch,
            base_branch=default_branch,
        )
        sha = client.file_sha(fork_owner, fork_repo, target_path, branch)
        response = client.put_file(
            fork_owner,
            fork_repo,
            branch=branch,
            path=target_path,
            content=content,
            message=f"Update Simplified Chinese localization for {mod_id}",
            sha=sha,
        )
    finally:
        if owns_client:
            client.close()

    commit = response.get("commit") if isinstance(response, dict) else {}
    commit_sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(commit_sha, str) or not commit_sha:
        raise ValueError("GitHub did not return a commit sha")

    _record_fork_commit(
        db_path=db_path,
        mod_id=mod_id,
        workflow_mod_id=str(workflow["mod_id"]),
        repo_slug=fork_slug,
        branch=branch,
        commit_sha=commit_sha,
    )
    return {
        "mod_id": mod_id,
        "repo_slug": fork_slug,
        "branch": branch,
        "commit_sha": commit_sha,
        "target_path": target_path,
        "html_url": f"https://github.com/{fork_slug}/commit/{commit_sha}",
    }


def _mark_fork_verified(*, db_path: Path, workflow_mod_id: str) -> None:
    with connect(db_path) as db:
        db.execute(
            """
            update mod_workflows
            set fork_status = 'already_exists',
                workflow_status = case
                    when workflow_status in ('', 'unprobed', 'probed') then 'forked'
                    else workflow_status
                end,
                next_action = case
                    when next_action in ('', 'fork') then 'translate'
                    else next_action
                end,
                updated_at = current_timestamp
            where mod_id = ?
            """,
            (workflow_mod_id,),
        )
        db.commit()


def _workflow_for_mod(db_path: Path, mod: dict[str, Any]) -> dict[str, Any]:
    mod_id_key = _normalize_key(str(mod["mod_id"]))
    repo_name_key = _normalize_key(Path(str(mod["repo_path"])).name)
    with connect(db_path) as db:
        rows = db.execute("select * from mod_workflows").fetchall()
    for row in rows:
        data = dict(row)
        keys = [
            _normalize_key(str(data.get("mod_id") or "")),
            _normalize_key(str(data.get("upstream_slug") or "")),
            _normalize_key(str(data.get("canonical_upstream") or "")),
            _normalize_key(str(data.get("upstream_url") or "")),
        ]
        if mod_id_key in keys or repo_name_key in keys:
            return data
    raise ValueError("selected mod has no workflow/fork state")


def _record_fork_commit(
    *,
    db_path: Path,
    mod_id: str,
    workflow_mod_id: str,
    repo_slug: str,
    branch: str,
    commit_sha: str,
) -> None:
    with connect(db_path) as db:
        db.execute(
            """
            insert into pull_requests(
                mod_id, repo_slug, branch, state, last_commit_sha
            ) values (?, ?, ?, 'fork_committed', ?)
            on conflict(mod_id, repo_slug, branch) do update set
                state = excluded.state,
                last_commit_sha = excluded.last_commit_sha,
                updated_at = current_timestamp
            """,
            (mod_id, repo_slug, branch, commit_sha),
        )
        db.execute(
            """
            update mod_workflows
            set workflow_status = 'committed',
                next_action = 'pr',
                updated_at = current_timestamp
            where mod_id = ?
            """,
            (workflow_mod_id,),
        )
        db.commit()


def _normalize_key(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.casefold()))
