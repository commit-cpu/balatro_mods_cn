"""Git repository clone, fetch, and checkout operations."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo
from git.remote import RemoteProgress

from app.config import GitSettings
from app.github.mod_config import ModConfig

logger = logging.getLogger(__name__)


class CloneProgress(RemoteProgress):
    """Logs git clone/fetch progress."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label
        self._last_pct = -1

    def update(
        self,
        op_code: int,
        cur_count: float,
        max_count: float | None = None,
        message: str = "",
    ) -> None:
        pct = int(cur_count / (max_count or 100) * 100) if max_count else -1
        if pct != self._last_pct and pct >= 0:
            logger.debug("%s: %d%% (%s)", self._label, pct, message.strip() or "...")
            self._last_pct = pct


class RepositorySyncer:
    """Manages local git clones of tracked mod repositories."""

    def __init__(self, settings: GitSettings) -> None:
        self._repos_dir = Path(settings.repos_dir).resolve()
        self._clone_timeout = settings.clone_timeout_seconds
        self._default_branch = settings.default_branch
        self._proxy_env = settings.proxy_env()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def ensure_cloned(self, mod: ModConfig) -> Repo:
        """Clone the mod's origin repo if not already present; return the Repo.

        If the target directory already exists and is a valid git repo, it is
        opened in-place.  Otherwise the directory is removed and re-cloned.
        """
        target = self._repos_dir / mod.repo_dir_name
        target.mkdir(parents=True, exist_ok=True)

        try:
            repo = Repo(str(target))
            # Validate that the remote matches what we expect
            origin_url = _normalise_url(repo.remotes.origin.url)
            expected = _normalise_url(mod.origin.clone_url)
            if origin_url != expected:
                logger.warning(
                    "Remote mismatch for %s: expected %s, got %s. Re-cloning.",
                    mod.id,
                    expected,
                    origin_url,
                )
                shutil.rmtree(str(target))
                target.mkdir(parents=True, exist_ok=True)
                return self._clone(mod, target)
            return repo
        except (InvalidGitRepositoryError, ValueError):
            # Directory exists but isn't a git repo, or remote is missing
            if any(target.iterdir()):
                shutil.rmtree(str(target))
                target.mkdir(parents=True, exist_ok=True)
            return self._clone(mod, target)

    def fetch(self, repo: Repo, mod: ModConfig) -> None:
        """Fetch latest refs from origin for the given repo."""
        with repo.git.custom_environment(**self._proxy_env):
            origin = repo.remotes.origin
            logger.info("Fetching origin for %s …", mod.id)
            fetch_infos = origin.fetch(progress=CloneProgress(f"fetch:{mod.id}"))
            for fi in fetch_infos:
                logger.debug("  %s -> %s", fi.ref, fi.commit)

    def checkout_commit(self, repo: Repo, commit_sha: str) -> None:
        """Checkout a specific commit (detached HEAD) and reset working tree."""
        repo.head.reference = repo.commit(commit_sha)
        repo.head.reset(index=True, working_tree=True)
        logger.info("Checked out %s (detached)", commit_sha[:8])

    def checkout_branch(self, repo: Repo, branch: str) -> None:
        """Checkout an existing branch."""
        if branch not in repo.heads:
            raise ValueError(f"Branch {branch!r} not found in repo {repo.working_dir}")
        repo.heads[branch].checkout()
        logger.info("Checked out branch %s", branch)

    def create_branch(self, repo: Repo, branch: str, commit_sha: str | None = None) -> None:
        """Create a new branch (replaces if exists) at the given commit."""
        commit = repo.commit(commit_sha) if commit_sha else repo.head.commit
        if branch in repo.heads:
            repo.delete_head(branch, force=True)
        new_head = repo.create_head(branch, commit=commit)
        new_head.checkout()
        logger.info("Created branch %s at %s", branch, commit.hexsha[:8])

    def commit_file(
        self,
        repo: Repo,
        file_path: str,
        message: str,
    ) -> str:
        """Stage and commit a single file. Returns the new commit SHA."""
        repo.index.add([file_path])
        commit = repo.index.commit(message)
        logger.info("Committed %s: %s", file_path, commit.hexsha[:8])
        return commit.hexsha

    def push(self, repo: Repo, branch: str) -> None:
        """Push a branch to origin."""
        with repo.git.custom_environment(**self._proxy_env):
            origin = repo.remotes.origin
            logger.info("Pushing %s to origin …", branch)
            result = origin.push(branch)
            for pi in result:
                logger.debug("  %s: %s", pi.remote_ref, pi.summary)

    def latest_commit_sha(self, repo: Repo, ref: str = "origin/main") -> str:
        """Return the hex SHA of the latest commit on *ref*."""
        commit = repo.commit(ref)
        return commit.hexsha

    def working_dir(self, repo: Repo) -> Path:
        """Return the working-tree directory for *repo*."""
        return Path(repo.working_dir)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _clone(self, mod: ModConfig, target: Path) -> Repo:
        logger.info("Cloning %s -> %s …", mod.origin.clone_url, target)
        try:
            repo = Repo.clone_from(
                url=mod.origin.clone_url,
                to_path=str(target),
                branch=mod.origin.branch,
                progress=CloneProgress(f"clone:{mod.id}"),
                env=self._proxy_env,
            )
        except GitCommandError as exc:
            # Clean up partial clone
            if target.exists():
                shutil.rmtree(str(target))
            raise RuntimeError(
                f"Clone failed for {mod.origin.clone_url}: {exc.stderr.strip()}"
            ) from exc
        return repo


def _normalise_url(url: str) -> str:
    """Normalise a git remote URL for comparison.

    Strips trailing ``.git`` and normalises https vs git@ protocol so that
    ``https://github.com/a/b.git`` and ``git@github.com:a/b`` compare equal.
    """
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # Normalise git@github.com:owner/repo -> https://github.com/owner/repo
    if url.startswith("git@"):
        url = url.replace(":", "/", 1).replace("git@", "https://", 1)
    return url.lower()
