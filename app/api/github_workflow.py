from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from dotenv import load_dotenv

from app.api.repositories import ApiRepository
from app.db.connection import connect
from app.github.no_clone_l10n_probe import (
    GitHubApi,
    load_index_items,
    probe_index_item,
    run_github_l10n_probe,
)


DEFAULT_GITHUB_CACHE_DIR = Path("data/artifacts/github_no_clone_l10n_probe/cache")
DEFAULT_GITHUB_CACHE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_GITHUB_LOCALIZATION_ROOT = Path("data/repos/github-localization")


def run_github_probe_job(db_path: Path, job_id: int, payload: dict[str, Any]) -> None:
    repo = ApiRepository(db_path)
    repo.update_job_status(job_id, "running")
    repo.log_job_event(
        job_id,
        event="github.probe.start",
        message="Starting GitHub probe",
        payload={
            "mod_name": payload.get("mod_name"),
            "repo_url": payload.get("repo_url"),
            "fork": bool(payload.get("fork")),
            "limit": payload.get("limit"),
        },
    )
    try:
        token = _github_token()
        report_path = Path(payload["report_path"])
        existing_report = _read_probe_report(report_path)
        report = run_github_l10n_probe(
            token=token,
            index_path=Path(payload["index_path"]),
            report_path=report_path,
            limit=int(payload["limit"]),
            mod_name=payload.get("mod_name"),
            repo_url=payload.get("repo_url"),
            fork=bool(payload.get("fork")),
            cache_dir=Path(payload["cache_dir"]),
            refresh_cache=bool(payload.get("refresh_cache")),
            cache_ttl_seconds=int(
                payload.get("cache_ttl_seconds", DEFAULT_GITHUB_CACHE_TTL_SECONDS)
            ),
        )
        if payload.get("mod_name") or payload.get("repo_url"):
            merged_report = _merge_probe_report(existing_report, report)
            report_path.write_text(
                json.dumps(merged_report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        workflow_rows = repo.upsert_workflows_from_probe_report(
            report,
            job_id=job_id,
            cache_ttl_seconds=int(
                payload.get("cache_ttl_seconds", DEFAULT_GITHUB_CACHE_TTL_SECONDS)
            ),
        )
        repo.log_job_event(
            job_id,
            event="github.probe.complete",
            message="GitHub probe completed",
            payload={
                "items": len(report.get("items", [])),
                "workflow_rows": workflow_rows,
                "fork": bool(payload.get("fork")),
            },
        )
        repo.update_job_status(
            job_id,
            "succeeded",
            result={
                "items": len(report.get("items", [])),
                "workflow_rows": workflow_rows,
                "report_path": payload["report_path"],
                "fork": bool(payload.get("fork")),
            },
        )
    except Exception as exc:
        repo.log_job_event(
            job_id,
            level="error",
            event="github.probe.failed",
            message=str(exc),
        )
        repo.update_job_status(job_id, "failed", last_error=str(exc))


def github_probe_payload(
    *,
    index_path: Path,
    report_path: Path,
    limit: int,
    fork: bool,
    refresh_cache: bool,
    mod_name: str | None = None,
    repo_url: str | None = None,
    cache_dir: Path = DEFAULT_GITHUB_CACHE_DIR,
    cache_ttl_seconds: int = DEFAULT_GITHUB_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    return {
        "index_path": str(index_path),
        "report_path": str(report_path),
        "limit": limit,
        "mod_name": mod_name,
        "repo_url": repo_url,
        "fork": fork,
        "refresh_cache": refresh_cache,
        "cache_dir": str(cache_dir),
        "cache_ttl_seconds": cache_ttl_seconds,
    }


def materialize_github_localization_source(
    *,
    db_path: Path,
    index_path: Path,
    mod_name: str | None,
    repo_url: str | None,
    cache_dir: Path = DEFAULT_GITHUB_CACHE_DIR,
    refresh_cache: bool = False,
    cache_ttl_seconds: int = DEFAULT_GITHUB_CACHE_TTL_SECONDS,
    local_root: Path = DEFAULT_GITHUB_LOCALIZATION_ROOT,
) -> dict[str, Any]:
    items = load_index_items(index_path, 1, mod_name=mod_name, repo_url=repo_url)
    if not items:
        raise ValueError("selected GitHub mod was not found in mod index")
    token = _github_token()
    client = GitHubApi(
        token,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    try:
        github_user = client.current_user()
        row = probe_index_item(
            client=client,
            github_user=github_user,
            item=items[0],
            index=1,
            fork=False,
            create_empty_zh_once=False,
            did_test_commit=False,
            branch="codex-test-empty-zh-cn",
        )
        return materialize_probe_row_localization(
            db_path=db_path,
            row=row,
            client=client,
            local_root=local_root,
        )
    finally:
        client.close()


def materialize_probe_row_localization(
    *,
    db_path: Path,
    row: dict[str, Any],
    client: Any,
    local_root: Path,
) -> dict[str, Any]:
    if row.get("error"):
        raise ValueError(str(row["error"]))
    detail = _first_locale_detail(row)
    source_path = str(detail["source"])
    target_path = str(detail["zh"])
    owner, repo = _row_repo_owner_name(row)
    branch = str(row.get("default_branch") or "main")
    repo_path = local_root / _safe_repo_dir(row)

    source_text = client.file_text(owner, repo, source_path, branch)
    if source_text is None:
        raise ValueError(f"source localization file not found: {source_path}")
    _write_text(repo_path / source_path, source_text)

    target_text = client.file_text(owner, repo, target_path, branch)
    if target_text is not None:
        _write_text(repo_path / target_path, target_text)

    mod_id = _safe_mod_id(str(row.get("name") or repo))
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(
                mod_id, repo_path, source_locale_path, target_locale_path
            ) values (?, ?, ?, ?)
            on conflict(mod_id) do update set
                repo_path = excluded.repo_path,
                source_locale_path = excluded.source_locale_path,
                target_locale_path = excluded.target_locale_path
            """,
            (mod_id, str(repo_path), source_path, target_path),
        )
        db.commit()

    mod = ApiRepository(db_path).get_mod(mod_id)
    if mod is None:
        raise RuntimeError(f"materialized mod source disappeared: {mod_id}")
    return mod


def _first_locale_detail(row: dict[str, Any]) -> dict[str, Any]:
    analysis = row.get("analysis")
    details = analysis.get("details") if isinstance(analysis, dict) else None
    if not isinstance(details, list):
        raise ValueError("selected GitHub mod has no recognized localization source")
    for detail in details:
        if not isinstance(detail, dict):
            continue
        if isinstance(detail.get("source"), str) and isinstance(detail.get("zh"), str):
            return detail
    raise ValueError("selected GitHub mod has no recognized localization source")


def _row_repo_owner_name(row: dict[str, Any]) -> tuple[str, str]:
    slug = row.get("canonical_upstream") or row.get("upstream")
    if isinstance(slug, str) and "/" in slug:
        owner, repo = slug.split("/", 1)
        if owner and repo:
            return owner, repo
    url = str(row.get("url") or "")
    parts = [part for part in url.removesuffix("/").removesuffix(".git").split("/") if part]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    raise ValueError("selected GitHub mod has no usable repository slug")


def _safe_repo_dir(row: dict[str, Any]) -> str:
    slug = str(row.get("canonical_upstream") or row.get("upstream") or row.get("name") or "mod")
    return _safe_path_part(slug.replace("/", "__"))


def _safe_mod_id(name: str) -> str:
    return _safe_path_part(name).replace("-", "_").casefold()


def _safe_path_part(value: str) -> str:
    return "_".join(re.findall(r"[A-Za-z0-9]+", value)) or "mod"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_probe_report(report_path: Path) -> dict[str, Any]:
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return existing if isinstance(existing, dict) else {}


def _merge_probe_report(
    existing: dict[str, Any],
    selected_report: dict[str, Any],
) -> dict[str, Any]:
    existing_items = existing.get("items")
    if not isinstance(existing_items, list):
        existing_items = []
    selected_items = selected_report.get("items")
    if not isinstance(selected_items, list):
        selected_items = []

    merged_items: list[Any] = []
    selected_by_key = {
        _probe_row_key(item): item
        for item in selected_items
        if isinstance(item, dict) and _probe_row_key(item)
    }
    seen: set[tuple[str, str]] = set()
    for item in existing_items:
        if not isinstance(item, dict):
            continue
        key = _probe_row_key(item)
        if key in selected_by_key:
            merged_items.append(selected_by_key[key])
            seen.add(key)
        else:
            merged_items.append(item)
    for key, item in selected_by_key.items():
        if key not in seen:
            merged_items.append(item)

    merged = dict(existing)
    for key, value in selected_report.items():
        if key != "items":
            merged[key] = value
    merged["items"] = merged_items
    return merged


def _probe_row_key(item: dict[str, Any]) -> tuple[str, str]:
    url = str(item.get("url") or "").removesuffix("/").removesuffix(".git").casefold()
    if url:
        return ("url", url)
    name = str(item.get("name") or "").casefold()
    return ("name", name) if name else ("", "")


def _github_token() -> str:
    load_dotenv()
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN, GH_TOKEN, or GITHUB_PAT.")
    return token
