from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx

from app.lua.extractor import LuaExtractor
from app.cli.main import _residual_english_severity


SOURCE_LOCALE_NAMES = ("en-us.lua", "default.lua", "en.lua")
TARGET_LOCALE_NAME = "zh_CN.lua"
STATUS_PRIORITY = {
    "parse_error": 0,
    "missing_zh_CN": 1,
    "no_translatable_units": 2,
    "missing_keys": 3,
    "untranslated_keys": 4,
    "residual_english": 5,
    "complete": 6,
}


@dataclass(frozen=True)
class LocaleFileAnalysis:
    source_path: str
    target_path: str
    status: str
    source_units: int
    zh_units: int
    missing_keys: list[str] = field(default_factory=list)
    extra_keys: list[str] = field(default_factory=list)
    same_as_source_keys: list[str] = field(default_factory=list)
    residual_english_keys: list[str] = field(default_factory=list)
    source_error: str | None = None
    zh_error: str | None = None

    @property
    def missing_count(self) -> int:
        return len(self.missing_keys)

    @property
    def extra_count(self) -> int:
        return len(self.extra_keys)

    @property
    def untranslated_count(self) -> int:
        return len(self.same_as_source_keys)

    @property
    def residual_english_count(self) -> int:
        return len(self.residual_english_keys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_path,
            "zh": self.target_path,
            "status": self.status,
            "zh_exists": self.status != "missing_zh_CN",
            "source_units": self.source_units,
            "zh_units": self.zh_units,
            "missing_count": self.missing_count,
            "extra_count": self.extra_count,
            "untranslated_count": self.untranslated_count,
            "residual_english_count": self.residual_english_count,
            "source_error": self.source_error,
            "zh_error": self.zh_error,
            "samples": {
                "missing_keys": self.missing_keys[:10],
                "extra_keys": self.extra_keys[:10],
                "same_as_source_keys": self.same_as_source_keys[:10],
                "residual_english_keys": self.residual_english_keys[:10],
            },
        }


@dataclass(frozen=True)
class RepoLocalizationAnalysis:
    status: str
    localization_dirs: list[str]
    source_files: list[str]
    zh_files: list[str]
    details: list[LocaleFileAnalysis] = field(default_factory=list)
    tree_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "localization_dirs": self.localization_dirs,
            "source_files": self.source_files,
            "zh_files": self.zh_files,
            "tree_truncated": self.tree_truncated,
            "summary": {
                "status": self.status,
                "locale_pairs": len(self.details),
                "source_units": sum(item.source_units for item in self.details),
                "zh_units": sum(item.zh_units for item in self.details),
                "missing_keys": sum(item.missing_count for item in self.details),
                "extra_keys": sum(item.extra_count for item in self.details),
                "untranslated_keys": sum(item.untranslated_count for item in self.details),
                "residual_english": sum(
                    item.residual_english_count for item in self.details
                ),
            },
            "details": [item.to_dict() for item in self.details],
        }


def parse_github_repo_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.rstrip("/"))
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        raise ValueError(f"Not a GitHub repository URL: {url}")
    return parts[0], parts[1].removesuffix(".git")


def canonical_repo_from_meta(
    meta: dict[str, Any],
    *,
    fallback_owner: str,
    fallback_repo: str,
) -> tuple[str, str]:
    full_name = meta.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        owner, repo = full_name.split("/", 1)
        if owner and repo:
            return owner, repo
    name = meta.get("name")
    return fallback_owner, name if isinstance(name, str) and name else fallback_repo


def classify_locale_pair(
    *,
    source_path: str,
    target_path: str,
    source_units: dict[str, str],
    target_units: dict[str, str] | None,
    source_error: str | None = None,
    zh_error: str | None = None,
) -> LocaleFileAnalysis:
    if target_units is None:
        missing_keys = sorted(source_units)
        return LocaleFileAnalysis(
            source_path=source_path,
            target_path=target_path,
            status="missing_zh_CN",
            source_units=len(source_units),
            zh_units=0,
            missing_keys=missing_keys,
            source_error=source_error,
        )

    source_keys = set(source_units)
    target_keys = set(target_units)
    missing_keys = sorted(source_keys - target_keys)
    extra_keys = sorted(target_keys - source_keys)
    same_as_source_keys = sorted(
        key
        for key in source_keys & target_keys
        if source_units[key] == target_units[key] and _contains_ascii_word(source_units[key])
    )
    residual_english_keys = sorted(
        key
        for key, text in target_units.items()
        if key in source_keys and _residual_english_severity(text) == "rerun"
    )

    status = "complete"
    if source_error or zh_error:
        status = "parse_error"
    elif not source_units:
        status = "no_translatable_units"
    elif missing_keys:
        status = "missing_keys"
    elif same_as_source_keys:
        status = "untranslated_keys"
    elif residual_english_keys:
        status = "residual_english"

    return LocaleFileAnalysis(
        source_path=source_path,
        target_path=target_path,
        status=status,
        source_units=len(source_units),
        zh_units=len(target_units),
        missing_keys=missing_keys,
        extra_keys=extra_keys,
        same_as_source_keys=same_as_source_keys,
        residual_english_keys=residual_english_keys,
        source_error=source_error,
        zh_error=zh_error,
    )


def summarize_repo_analysis(
    *,
    localization_dirs: list[str],
    locale_files: list[LocaleFileAnalysis],
    source_files: list[str] | None = None,
    zh_files: list[str] | None = None,
    tree_truncated: bool = False,
) -> RepoLocalizationAnalysis:
    if not localization_dirs:
        status = "no_localization_dir"
    elif not locale_files:
        status = "localization_without_known_source"
    elif all(item.status == "complete" for item in locale_files):
        status = "complete"
    else:
        status = min(
            (item.status for item in locale_files),
            key=lambda value: STATUS_PRIORITY.get(value, 99),
        )

    return RepoLocalizationAnalysis(
        status=status,
        localization_dirs=sorted(localization_dirs),
        source_files=sorted(source_files or [item.source_path for item in locale_files]),
        zh_files=sorted(zh_files or []),
        details=locale_files,
        tree_truncated=tree_truncated,
    )


class GitHubApi:
    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        cache_dir: Path | str | None = None,
        refresh_cache: bool = False,
        cache_ttl_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._refresh_cache = refresh_cache
        self._cache_ttl_seconds = cache_ttl_seconds
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "balatro-mods-cn-no-clone-probe/0.1",
            },
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def current_user(self) -> str:
        return self._get("/user")["login"]

    def repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._get(f"/repos/{owner}/{repo}")

    def fork_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._post(f"/repos/{owner}/{repo}/forks", json={})

    def ensure_fork(
        self,
        upstream_owner: str,
        repo: str,
        fork_owner: str,
    ) -> tuple[dict[str, Any], str]:
        try:
            fork = self.repo(fork_owner, repo)
            if fork.get("fork"):
                return fork, "already_exists"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

        self.fork_repo(upstream_owner, repo)
        fork = self.wait_for_repo(fork_owner, repo)
        return fork, "created"

    def wait_for_repo(
        self,
        owner: str,
        repo: str,
        *,
        attempts: int = 30,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return self.repo(owner, repo)
            except Exception as exc:  # pragma: no cover - timing depends on GitHub
                last_error = exc
                time.sleep(3)
        raise RuntimeError(f"Repository {owner}/{repo} was not ready: {last_error}")

    def recursive_tree(self, owner: str, repo: str, ref: str) -> tuple[list[dict[str, Any]], bool]:
        data = self._get(f"/repos/{owner}/{repo}/git/trees/{ref}", params={"recursive": "1"})
        tree = data.get("tree")
        return tree if isinstance(tree, list) else [], bool(data.get("truncated"))

    def file_text(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        encoded = _quote_path(path)
        try:
            data = self._get(
                f"/repos/{owner}/{repo}/contents/{encoded}",
                params={"ref": ref},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            return None
        raw = base64.b64decode(data["content"])
        return raw.decode("utf-8")

    def create_branch(self, owner: str, repo: str, *, branch: str, base_branch: str) -> bool:
        ref = self._get(f"/repos/{owner}/{repo}/git/ref/heads/{quote(base_branch, safe='')}")
        sha = ref["object"]["sha"]
        try:
            self._post(
                f"/repos/{owner}/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": sha},
            )
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 422 and "Reference already exists" in exc.text:
                return False
            raise

    def file_sha(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        encoded = _quote_path(path)
        try:
            data = self._get(
                f"/repos/{owner}/{repo}/contents/{encoded}",
                params={"ref": ref},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        sha = data.get("sha")
        return sha if isinstance(sha, str) and sha else None

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
        encoded = _quote_path(path)
        payload = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        }
        if sha is not None:
            payload["sha"] = sha
        return self._put(f"/repos/{owner}/{repo}/contents/{encoded}", json=payload)

    def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        cache_path = self._cache_path(path, kwargs)
        if (
            cache_path is not None
            and not self._refresh_cache
            and cache_path.exists()
            and not self._cache_expired(cache_path)
        ):
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                return cached

        response = self._client.get(path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if cache_path is not None and isinstance(payload, dict):
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return payload

    def _post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.post(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.put(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _cache_path(self, path: str, kwargs: dict[str, Any]) -> Path | None:
        if self._cache_dir is None:
            return None
        key = json.dumps(
            {
                "path": path,
                "params": kwargs.get("params") or {},
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def _cache_expired(self, path: Path) -> bool:
        if self._cache_ttl_seconds is None:
            return False
        age = time.time() - path.stat().st_mtime
        return age > self._cache_ttl_seconds


def run_github_l10n_probe(
    *,
    token: str,
    index_path: Path,
    report_path: Path,
    limit: int,
    mod_name: str | None = None,
    repo_url: str | None = None,
    fork: bool = False,
    create_empty_zh_once: bool = False,
    branch: str = "codex-test-empty-zh-cn",
    cache_dir: Path | None = None,
    refresh_cache: bool = False,
    cache_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    items = load_index_items(
        index_path,
        limit,
        mod_name=mod_name,
        repo_url=repo_url,
    )
    client = GitHubApi(
        token,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    report: dict[str, Any] = {
        "index": str(index_path),
        "limit": limit,
        "items": [],
        "test_commit": None,
    }

    try:
        github_user = client.current_user()
        report["github_user"] = github_user
        did_test_commit = False

        for index, item in enumerate(items, 1):
            row = probe_index_item(
                client=client,
                github_user=github_user,
                item=item,
                index=index,
                fork=fork,
                create_empty_zh_once=create_empty_zh_once,
                did_test_commit=did_test_commit,
                branch=branch,
            )
            if row.get("test_commit"):
                report["test_commit"] = row["test_commit"]
                did_test_commit = True
            report["items"].append(row)
    finally:
        client.close()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def probe_index_item(
    *,
    client: GitHubApi,
    github_user: str,
    item: dict[str, Any],
    index: int,
    fork: bool,
    create_empty_zh_once: bool,
    did_test_commit: bool,
    branch: str,
) -> dict[str, Any]:
    url = str(item.get("github_repo_url") or "")
    name = str(item.get("name") or "")
    row: dict[str, Any] = {
        "index": index,
        "name": name,
        "url": url,
        "upstream": "",
        "canonical_upstream": "",
        "fork": "",
        "fork_status": "not_requested",
        "analysis": {},
        "error": None,
    }
    try:
        owner, repo = parse_github_repo_url(url)
        row["upstream"] = f"{owner}/{repo}"
        row["fork"] = f"{github_user}/{repo}"

        analysis, upstream_meta = analyze_repository_no_clone(
            client=client,
            owner=owner,
            repo=repo,
        )
        canonical_owner, canonical_repo = canonical_repo_from_meta(
            upstream_meta,
            fallback_owner=owner,
            fallback_repo=repo,
        )
        row["canonical_upstream"] = f"{canonical_owner}/{canonical_repo}"
        row["fork"] = f"{github_user}/{canonical_repo}"
        row["default_branch"] = str(upstream_meta.get("default_branch") or "main")
        row["analysis"] = analysis.to_dict()

        fork_meta: dict[str, Any] | None = None
        if fork or (
            create_empty_zh_once
            and not did_test_commit
            and analysis.status == "missing_zh_CN"
            and analysis.details
        ):
            fork_meta, fork_status = client.ensure_fork(
                canonical_owner,
                canonical_repo,
                github_user,
            )
            row["fork_status"] = fork_status

        if (
            create_empty_zh_once
            and not did_test_commit
            and fork_meta is not None
            and analysis.status == "missing_zh_CN"
            and analysis.details
        ):
            target_path = analysis.details[0].target_path
            default_branch = str(
                fork_meta.get("default_branch")
                or upstream_meta.get("default_branch")
                or "main"
            )
            existing = client.file_text(
                github_user,
                canonical_repo,
                target_path,
                branch,
            )
            if existing is None:
                commit_info = create_empty_zh_file_once(
                    client=client,
                    fork_owner=github_user,
                    repo=canonical_repo,
                    default_branch=default_branch,
                    target_path=target_path,
                    branch=branch,
                )
                commit_info["upstream"] = row["upstream"]
                commit_info["canonical_upstream"] = row["canonical_upstream"]
                commit_info["created_file"] = True
            else:
                commit_info = {
                    "repo": row["fork"],
                    "upstream": row["upstream"],
                    "canonical_upstream": row["canonical_upstream"],
                    "branch": branch,
                    "path": target_path,
                    "created_file": False,
                    "commit": None,
                }
            row["test_commit"] = commit_info
    except Exception as exc:
        row["error"] = str(exc)
    return row


def analyze_repository_no_clone(
    *,
    client: GitHubApi,
    owner: str,
    repo: str,
    ref: str | None = None,
) -> tuple[RepoLocalizationAnalysis, dict[str, Any]]:
    repo_meta = client.repo(owner, repo)
    branch = ref or str(repo_meta.get("default_branch") or "main")
    tree, truncated = client.recursive_tree(owner, repo, branch)
    file_paths = sorted(
        item["path"]
        for item in tree
        if item.get("type") == "blob" and isinstance(item.get("path"), str)
    )
    dir_paths = sorted(
        item["path"]
        for item in tree
        if item.get("type") == "tree" and isinstance(item.get("path"), str)
    )
    localization_dirs = _localization_dirs(file_paths=file_paths, dir_paths=dir_paths)
    source_files = [
        path
        for path in file_paths
        if Path(path).name in SOURCE_LOCALE_NAMES and Path(path).parent.name == "localization"
    ]
    zh_files = [
        path
        for path in file_paths
        if Path(path).name == TARGET_LOCALE_NAME and Path(path).parent.name == "localization"
    ]

    details: list[LocaleFileAnalysis] = []
    for source_path in source_files:
        target_path = str(Path(source_path).with_name(TARGET_LOCALE_NAME))
        source_text = client.file_text(owner, repo, source_path, branch)
        source_units, source_error = _extract_lua_units(source_text, source_path)
        target_text = client.file_text(owner, repo, target_path, branch)
        if target_text is None:
            target_units = None
            target_error = None
        else:
            target_units, target_error = _extract_lua_units(target_text, target_path)
        details.append(
            classify_locale_pair(
                source_path=source_path,
                target_path=target_path,
                source_units=source_units,
                target_units=target_units,
                source_error=source_error,
                zh_error=target_error,
            )
        )

    analysis = summarize_repo_analysis(
        localization_dirs=localization_dirs,
        locale_files=details,
        source_files=source_files,
        zh_files=zh_files,
        tree_truncated=truncated,
    )
    return analysis, repo_meta


def create_empty_zh_file_once(
    *,
    client: GitHubApi,
    fork_owner: str,
    repo: str,
    default_branch: str,
    target_path: str,
    branch: str = "codex-test-empty-zh-cn",
) -> dict[str, Any]:
    branch_created = client.create_branch(
        fork_owner,
        repo,
        branch=branch,
        base_branch=default_branch,
    )
    content = client.put_file(
        fork_owner,
        repo,
        branch=branch,
        path=target_path,
        content=b"",
        message="test: add empty zh_CN localization file",
    )
    return {
        "repo": f"{fork_owner}/{repo}",
        "branch": branch,
        "branch_created": branch_created,
        "path": target_path,
        "commit": content.get("commit", {}).get("sha"),
    }


def load_index_items(
    path: Path,
    limit: int,
    *,
    mod_name: str | None = None,
    repo_url: str | None = None,
) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    items = [item for item in data if isinstance(item, dict)]
    if repo_url:
        repo_key = _normal_repo_url(repo_url)
        items = [
            item
            for item in items
            if _normal_repo_url(item.get("github_repo_url")) == repo_key
        ]
    elif mod_name:
        name_key = mod_name.casefold()
        items = [
            item
            for item in items
            if str(item.get("name") or "").casefold() == name_key
        ]
    return items[:limit]


def _normal_repo_url(value: Any) -> str:
    return str(value or "").removesuffix("/").removesuffix(".git").casefold()


def _extract_lua_units(text: str | None, label: str) -> tuple[dict[str, str], str | None]:
    if text is None:
        return {}, f"missing file content: {label}"
    tmp_dir = Path("/tmp/balatro_mods_cn_no_clone_probe")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / _safe_tmp_name(label)
    tmp_path.write_text(text, encoding="utf-8")
    try:
        units = LuaExtractor().extract_file(tmp_path)
        return {unit.unit_key: unit.source_text for unit in units}, None
    except Exception as exc:
        return {}, str(exc)
    finally:
        tmp_path.unlink(missing_ok=True)


def _safe_tmp_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "locale.lua"


def _contains_ascii_word(text: str) -> bool:
    return bool(re.search(r"[A-Za-z][A-Za-z0-9_.?'-]{1,}", text))


def _localization_dirs(*, file_paths: list[str], dir_paths: list[str]) -> list[str]:
    dirs = {path for path in dir_paths if Path(path).name == "localization"}
    for path in file_paths:
        parent = Path(path).parent
        if parent.name == "localization":
            dirs.add(str(parent))
    return sorted(dirs)


def _quote_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.strip("/").split("/"))
