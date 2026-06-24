"""GitHub REST API client (httpx-based) for commit detection and PR management."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.github.mod_config import ModConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GhCommit:
    sha: str
    message: str
    author: str
    timestamp: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> GhCommit:
        return cls(
            sha=payload["sha"],
            message=payload["commit"]["message"],
            author=payload["commit"]["author"]["name"],
            timestamp=payload["commit"]["author"]["date"],
        )


@dataclass(frozen=True)
class GhPullRequest:
    number: int
    title: str
    html_url: str
    state: str
    head_ref: str
    base_ref: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> GhPullRequest:
        return cls(
            number=payload["number"],
            title=payload["title"],
            html_url=payload["html_url"],
            state=payload["state"],
            head_ref=payload["head"]["ref"],
            base_ref=payload["base"]["ref"],
        )


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------


class GitHubClient:
    """Minimal GitHub REST API client for the Balatro CN worker."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        webhook_secret: str | None = None,
    ) -> None:
        self._token = token
        self._webhook_secret = webhook_secret
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "balatro-cn-worker/0.1",
            },
            timeout=httpx.Timeout(timeout),
        )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # commits
    # ------------------------------------------------------------------

    def latest_commit(self, mod: ModConfig, branch: str | None = None) -> GhCommit:
        """Return the latest commit on the origin repo's default branch."""
        branch = branch or mod.origin.branch
        commits = self._get_paginated(
            f"/repos/{mod.origin.slug}/commits",
            params={"sha": branch, "per_page": 1},
            limit=1,
        )
        if not commits:
            raise RuntimeError(f"No commits found for {mod.origin.slug}@{branch}")
        return GhCommit.from_api(commits[0])

    def compare_commits(
        self, mod: ModConfig, base: str, head: str
    ) -> list[GhCommit]:
        """Return commits between *base* and *head* (i.e. ``base..head``)."""
        data = self._get(
            f"/repos/{mod.origin.slug}/compare/{base}...{head}"
        )
        return [GhCommit.from_api(c) for c in data.get("commits", [])]

    # ------------------------------------------------------------------
    # pull requests
    # ------------------------------------------------------------------

    def find_open_pr(
        self, mod: ModConfig, head_branch: str
    ) -> GhPullRequest | None:
        """Return an open PR whose head ref is *head_branch*, or None."""
        prs = self._get_paginated(
            f"/repos/{mod.origin.slug}/pulls",
            params={
                "state": "open",
                "head": f"{mod.fork.owner}:{head_branch}",
                "sort": "updated",
                "direction": "desc",
            },
            limit=5,
        )
        for pr_data in prs:
            pr = GhPullRequest.from_api(pr_data)
            if pr.head_ref == head_branch:
                return pr
        return None

    def create_pr(
        self,
        mod: ModConfig,
        *,
        head_branch: str,
        title: str,
        body: str,
    ) -> GhPullRequest:
        """Create a pull request from fork:branch -> origin:default-branch."""
        payload = {
            "title": title,
            "body": body,
            "head": f"{mod.fork.owner}:{head_branch}",
            "base": mod.origin.branch,
        }
        data = self._post(f"/repos/{mod.origin.slug}/pulls", json=payload)
        return GhPullRequest.from_api(data)

    def update_pr(
        self,
        mod: ModConfig,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> GhPullRequest:
        """Update an existing PR's title and/or body."""
        payload: dict[str, str] = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        data = self._patch(
            f"/repos/{mod.origin.slug}/pulls/{pr_number}", json=payload
        )
        return GhPullRequest.from_api(data)

    # ------------------------------------------------------------------
    # forks
    # ------------------------------------------------------------------

    def fork_exists(self, mod: ModConfig) -> bool:
        """Check whether the bot's fork repo exists."""
        try:
            self._get(f"/repos/{mod.fork.slug}")
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise

    def fork_repo(self, mod: ModConfig) -> dict[str, Any]:
        """Create a fork of the origin repo under the bot owner."""
        logger.info("Forking %s …", mod.origin.slug)
        return self._post(
            f"/repos/{mod.origin.slug}/forks",
            json={"organization": mod.fork.owner} if mod.fork.owner else None,
        )

    # ------------------------------------------------------------------
    # webhook verification
    # ------------------------------------------------------------------

    def verify_signature(self, payload_body: bytes, signature: str) -> bool:
        """Verify an incoming webhook payload against its HMAC signature."""
        if not self._webhook_secret:
            logger.warning("Webhook secret not configured; skipping verification")
            return False
        mac = hmac.new(
            self._webhook_secret.encode(),
            payload_body,
            hashlib.sha256,
        )
        expected = f"sha256={mac.hexdigest()}"
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # internal HTTP helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
    )
    def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _get_paginated(
        self, path: str, *, limit: int, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """GET with pagination, collecting up to *limit* results."""
        params = kwargs.pop("params", {})
        params.setdefault("per_page", min(limit, 100))
        results: list[dict[str, Any]] = []
        resp = self._client.get(path, params=params, **kwargs)
        resp.raise_for_status()
        results.extend(resp.json())
        while len(results) < limit and "next" in resp.links:
            resp = self._client.get(resp.links["next"]["url"], **kwargs)
            resp.raise_for_status()
            results.extend(resp.json())
        return results[:limit]

    def _post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.post(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.patch(path, **kwargs)
        resp.raise_for_status()
        return resp.json()
