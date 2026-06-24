"""Pull-request creation and update strategies."""

from __future__ import annotations

import logging

from app.github.client import GitHubClient, GhPullRequest
from app.github.mod_config import ModConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PR_BRANCH_PREFIX = "bot/zh-cn"

# ---------------------------------------------------------------------------
# public helpers
# ---------------------------------------------------------------------------


def pr_branch_name(mod: ModConfig) -> str:
    """Return the conventional branch name for a mod's CN translation PR."""
    return f"{PR_BRANCH_PREFIX}/{mod.id}"


def pr_title(mod: ModConfig, commit_sha: str) -> str:
    """Generate a PR title for a Chinese translation update."""
    short = commit_sha[:7]
    return f"🌐 更新简体中文翻译 ({short})"


def pr_body(mod: ModConfig, commit_sha: str, unit_count: int) -> str:
    """Generate a PR body describing the translation update."""
    return (
        f"## 简体中文翻译更新\n\n"
        f"自动翻译了上游 `{mod.origin.branch}` 分支的 "
        f"[`{commit_sha[:7]}`](https://github.com/{mod.origin.slug}/commit/{commit_sha}) "
        f"提交。\n\n"
        f"- 翻译单元数：**{unit_count}**\n"
        f"- 目标文件：`{mod.target_locale_path}`\n\n"
        f"🤖 由 Balatro CN 翻译机器人自动生成。"
    )


# ---------------------------------------------------------------------------
# PR manager
# ---------------------------------------------------------------------------


class PullRequestManager:
    """Decides whether to create or update a PR based on publish_mode."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    def publish(
        self,
        mod: ModConfig,
        *,
        commit_sha: str,
        unit_count: int,
        dry_run: bool = False,
    ) -> GhPullRequest | None:
        """Create or update a PR for *mod*, respecting its publish_mode.

        Returns the PR if one was created/updated, or None if the mode
        prevents publishing (e.g. ``disabled`` or ``fork_only``).
        """
        if mod.publish_mode == "disabled":
            logger.info("Skipping PR for %s (publish_mode=disabled)", mod.id)
            return None

        branch = pr_branch_name(mod)
        title = pr_title(mod, commit_sha)
        body = pr_body(mod, commit_sha, unit_count)

        existing = self._client.find_open_pr(mod, branch)

        if mod.publish_mode == "fork_only":
            logger.info(
                "publish_mode=fork_only for %s – skipping PR to upstream (branch %s exists=%s)",
                mod.id,
                branch,
                existing is not None,
            )
            return None

        # publish_mode == "upstream_pr"
        if existing is not None:
            if dry_run:
                logger.info("[dry-run] Would update PR #%d for %s", existing.number, mod.id)
                return existing
            updated = self._client.update_pr(
                mod, existing.number, title=title, body=body
            )
            logger.info("Updated PR #%d for %s", updated.number, mod.id)
            return updated

        if dry_run:
            logger.info("[dry-run] Would create PR for %s", mod.id)
            return None

        created = self._client.create_pr(
            mod,
            head_branch=branch,
            title=title,
            body=body,
        )
        logger.info("Created PR #%d for %s: %s", created.number, mod.id, created.html_url)
        return created
