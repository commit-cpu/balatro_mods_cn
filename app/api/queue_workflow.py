from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks

from app.api.github_workflow import materialize_github_localization_source
from app.api.repositories import ApiRepository
from app.api.schemas import TranslationStart
from app.api.translation_workflow import run_translation_job, translation_payload


TranslationRunner = Callable[[Path, int, dict[str, Any]], None]


def start_translation_queue_item(
    *,
    db_path: Path,
    queue_id: int,
    background_tasks: BackgroundTasks | None,
    translation_runner: TranslationRunner = run_translation_job,
) -> dict[str, Any]:
    repo = ApiRepository(db_path)
    item = repo.get_translation_queue_item(queue_id)
    if item is None:
        raise KeyError(queue_id)
    if repo.has_active_translation():
        raise ValueError("another translation job is already active")

    mod = repo.get_mod(str(item["mod_id"]))
    if mod is None:
        repo_url = item.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url:
            raise ValueError("queued mod has no local source or repo URL")
        mod = materialize_github_localization_source(
            db_path=db_path,
            index_path=repo.mod_index_path,
            mod_name=item.get("source_name"),
            repo_url=repo_url,
        )

    job, created = repo.create_translation_job(
        mod_id=str(mod["mod_id"]),
        payload=translation_payload(mod, TranslationStart()),
    )
    repo.mark_translation_queue_running(queue_id, job["id"])
    if created:
        if background_tasks is None:
            _run_queue_translation_job(
                db_path=db_path,
                queue_id=queue_id,
                job_id=job["id"],
                payload=job["payload"],
                translation_runner=translation_runner,
            )
        else:
            background_tasks.add_task(
                _run_queue_translation_job,
                db_path=db_path,
                queue_id=queue_id,
                job_id=job["id"],
                payload=job["payload"],
                translation_runner=translation_runner,
            )
    return job


def run_translation_queue_tick(
    *,
    db_path: Path,
    translation_runner: TranslationRunner = run_translation_job,
) -> dict[str, Any] | None:
    repo = ApiRepository(db_path)
    settings = repo.get_admin_settings()
    if not settings["auto_translate_enabled"]:
        return None
    if repo.has_active_translation():
        return None

    last = _parse_time(settings.get("last_auto_translate_at"))
    interval = timedelta(hours=int(settings["auto_translate_interval_hours"]))
    now = datetime.now(timezone.utc)
    if last is not None and now - last < interval:
        return None

    item = repo.next_queued_translation()
    if item is None:
        return None
    job = start_translation_queue_item(
        db_path=db_path,
        queue_id=item["id"],
        background_tasks=None,
        translation_runner=translation_runner,
    )
    repo.update_admin_settings({"last_auto_translate_at": now.isoformat()})
    return {"queue": item, "job": job}


def _run_queue_translation_job(
    *,
    db_path: Path,
    queue_id: int,
    job_id: int,
    payload: dict[str, Any],
    translation_runner: TranslationRunner,
) -> None:
    repo = ApiRepository(db_path)
    try:
        translation_runner(db_path, job_id, payload)
        job = repo.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled"}:
            status = "succeeded" if job["status"] == "succeeded" else "failed"
            repo.mark_translation_queue_finished(
                queue_id,
                status,
                last_error=job.get("last_error"),
            )
    except Exception as exc:
        repo.mark_translation_queue_finished(queue_id, "failed", last_error=str(exc))
        raise


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
