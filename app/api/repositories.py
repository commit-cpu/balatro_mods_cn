from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.api.schemas import FeedbackCreate, ReviewGroupApprove, ReviewItemUpdate
from app.db.connection import connect


DEFAULT_MOD_INDEX_PATH = Path("data/repos/balatro-mod-index/mods/all.json")
DEFAULT_PROBE_REPORT_PATH = Path("data/artifacts/github_no_clone_l10n_probe/report.json")
DEFAULT_GITHUB_CACHE_TTL_SECONDS = 6 * 60 * 60
_SKIPPED_PROBE_STATUSES = {"no_localization_dir", "no_source_files", None}
_AI_STATUS_LABELS = {
    "unknown": "未探测",
    "skipped": "跳过",
    "running": "正在汉化",
    "translated_needs_review": "已经汉化（未review）",
    "complete": "完全汉化",
    "merged_upstream": "完全汉化并且 merge到官方仓库",
}
_WORKFLOW_STATUS_LABELS = {
    "unprobed": "未探测",
    "probed": "已探测",
    "forked": "已 Fork",
    "translating": "翻译中",
    "review_pending": "待审核",
    "approved": "已审核",
    "applied": "已应用",
    "committed": "已提交 Fork",
    "pr_open": "PR 已创建",
    "merged": "已合并",
    "upstream_complete": "上游已完整汉化",
    "skipped": "跳过",
    "failed": "失败",
}
_NEXT_ACTION_LABELS = {
    "probe": "探测",
    "fork": "验证/创建 Fork",
    "translate": "启动翻译",
    "review": "审核",
    "apply": "应用",
    "commit": "提交",
    "pr": "PR",
    "none": "无",
    "retry": "重试",
}
_REVIEW_FIELD_RE = re.compile(r"^(?P<entry>.+)\.(?P<field>name|text\[\d+\]|unlock\[\d+\])$")


class ApiRepository:
    def __init__(
        self,
        db_path: Path | str,
        *,
        mod_index_path: Path | str = DEFAULT_MOD_INDEX_PATH,
        probe_report_path: Path | str = DEFAULT_PROBE_REPORT_PATH,
    ) -> None:
        self._db_path = db_path
        self._mod_index_path = Path(mod_index_path)
        self._probe_report_path = Path(probe_report_path)

    @property
    def mod_index_path(self) -> Path:
        return self._mod_index_path

    @property
    def probe_report_path(self) -> Path:
        return self._probe_report_path

    def summary(self) -> dict[str, int]:
        with connect(self._db_path) as db:
            return {
                "mods": _count(db, "mod_sources"),
                "jobs": _count(db, "jobs"),
                "pending_jobs": _count_where(db, "jobs", "status = 'pending'"),
                "failed_jobs": _count_where(db, "jobs", "status = 'failed'"),
                "feedback": _count(db, "feedback"),
                "pending_feedback": _count_where(db, "feedback", "status = 'pending'"),
                "review_items": _count(db, "review_items"),
                "pending_reviews": _count_where(
                    db,
                    "review_items",
                    "status = 'pending'",
                ),
                "vector_outbox_pending": _count_where(
                    db,
                    "vector_outbox",
                    "status = 'pending'",
                ),
            }

    def dashboard(self) -> dict[str, Any]:
        items = self.mod_index_items()
        return {
            "collected_mods": len(items),
            "localized_mods": sum(
                1
                for item in items
                if item["localization_status"] in {"partial", "complete"}
            ),
            "ai_translated_mods": sum(
                1
                for item in items
                if item["ai_translation_status"]
                in {"translated_needs_review", "complete", "merged_upstream"}
            ),
            "last_updated_at": self._last_updated_at(),
        }

    def mod_index(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        localization_status: str | None = None,
        ai_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        items = self.mod_index_items()
        categories = sorted({cat for item in items for cat in item["categories"]})
        filtered = items
        if q:
            query = q.casefold()
            filtered = [
                item
                for item in filtered
                if query in item["name"].casefold()
                or query in (item["repo_url"] or "").casefold()
            ]
        if category:
            filtered = [item for item in filtered if category in item["categories"]]
        if localization_status:
            filtered = [
                item
                for item in filtered
                if item["localization_status"] == localization_status
            ]
        if ai_status:
            filtered = [
                item
                for item in filtered
                if item["ai_translation_status"] == ai_status
            ]
        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": filtered[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "categories": categories,
        }

    def mod_index_items(self) -> list[dict[str, Any]]:
        report_by_url, report_by_name = self._probe_report_indexes()
        ai_status_by_mod = self._ai_status_by_mod()
        workflow_by_mod = self._workflow_by_mod()
        local_mod_by_key = self._local_mod_by_key()
        latest_fork_branch_by_mod = self._latest_fork_branch_by_mod()
        return [
            self._mod_index_item(
                raw,
                report_by_url,
                report_by_name,
                ai_status_by_mod,
                workflow_by_mod,
                local_mod_by_key,
                latest_fork_branch_by_mod,
            )
            for raw in self._load_json_list(self._mod_index_path)
        ]

    def _load_json_list(self, path: Path) -> list[dict[str, Any]]:
        data = _read_json(path)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _probe_report_indexes(
        self,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        report = _read_json(self._probe_report_path)
        if not isinstance(report, dict):
            return {}, {}
        report_by_url: dict[str, dict[str, Any]] = {}
        report_by_name: dict[str, dict[str, Any]] = {}
        for item in report.get("items", []):
            if not isinstance(item, dict):
                continue
            url_key = _repo_key(item.get("url"))
            if url_key:
                report_by_url[url_key] = item
            name = item.get("name")
            if isinstance(name, str) and name:
                report_by_name[name.casefold()] = item
        return report_by_url, report_by_name

    def _mod_index_item(
        self,
        raw: dict[str, Any],
        report_by_url: dict[str, dict[str, Any]],
        report_by_name: dict[str, dict[str, Any]],
        ai_status_by_mod: dict[str, str],
        workflow_by_mod: dict[str, dict[str, Any]],
        local_mod_by_key: dict[str, dict[str, Any]],
        latest_fork_branch_by_mod: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        name = str(raw.get("name") or "")
        repo_url = raw.get("github_repo_url")
        repo_url = repo_url if isinstance(repo_url, str) else None
        local_mod = _match_local_mod(
            name=name,
            repo_url=repo_url,
            local_mod_by_key=local_mod_by_key,
        )
        report = report_by_url.get(_repo_key(repo_url)) or report_by_name.get(
            name.casefold()
        )
        probed = report is not None
        analysis = report.get("analysis", {}) if isinstance(report, dict) else {}
        summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
        probe_status = analysis.get("status") if isinstance(analysis, dict) else None
        localization_status, progress = _localization_status(
            probe_status,
            summary,
            probed=probed,
        )
        ai_status = ai_status_by_mod.get(name.casefold()) or ai_status_by_mod.get(
            _repo_key(repo_url)
        )
        if ai_status is None and local_mod is not None:
            ai_status = ai_status_by_mod.get(str(local_mod["mod_id"]).casefold())
        if ai_status is None:
            ai_status = "skipped" if probed else "unknown"
        workflow = self._resolved_workflow(
            name=name,
            repo_url=repo_url,
            report=report,
            probed=probed,
            localization_status=localization_status,
            ai_status=ai_status,
            workflow_by_mod=workflow_by_mod,
        )
        branch_row = None
        if local_mod is not None:
            branch_row = latest_fork_branch_by_mod.get(str(local_mod["mod_id"]).casefold())
        if branch_row is None:
            branch_row = latest_fork_branch_by_mod.get(name.casefold())
        branch_url = _github_branch_page_url(branch_row)
        return {
            "name": name,
            "repo_url": repo_url,
            "original_page_url": repo_url,
            "ai_translation_branch_url": branch_url,
            "ai_translation_repo_url": branch_url or _github_repo_page_url(
                _verified_fork_slug(report=report, workflow=workflow)
            ),
            "stars": _as_int(raw.get("stars")),
            "categories": [
                str(category)
                for category in raw.get("categories", [])
                if isinstance(category, str)
            ],
            "requires_steamodded": bool(raw.get("requires-steamodded")),
            "requires_talisman": bool(raw.get("requires-talisman")),
            "localization_status": localization_status,
            "localization_status_label": _localization_label(
                localization_status,
                progress,
            ),
            "localization_progress": progress,
            "ai_translation_status": ai_status,
            "ai_translation_status_label": _AI_STATUS_LABELS[ai_status],
            "translation_available": local_mod is not None,
            "translation_mod_id": local_mod["mod_id"] if local_mod else None,
            "workflow_status": workflow["workflow_status"],
            "workflow_status_label": _WORKFLOW_STATUS_LABELS.get(
                workflow["workflow_status"],
                workflow["workflow_status"],
            ),
            "next_action": workflow["next_action"],
            "next_action_label": _NEXT_ACTION_LABELS.get(
                workflow["next_action"],
                workflow["next_action"],
            ),
            "workflow_updated_at": workflow.get("updated_at"),
            "cache_expires_at": workflow.get("cache_expires_at"),
            "source_units": _as_int(summary.get("source_units")),
            "zh_units": _as_int(summary.get("zh_units")),
            "missing_keys": _as_int(summary.get("missing_keys")),
            "untranslated_keys": _as_int(summary.get("untranslated_keys")),
            "residual_english": _as_int(summary.get("residual_english")),
        }

    def _local_mod_by_key(self) -> dict[str, dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for mod in self.list_mods(limit=10_000):
            keys = {
                str(mod["mod_id"]).casefold(),
                Path(str(mod["repo_path"])).name.casefold(),
            }
            repo_path = Path(str(mod["repo_path"]))
            if repo_path.parent.name:
                keys.add(repo_path.parent.name.casefold())
            for key in keys:
                if key:
                    by_key[key] = mod
        return by_key

    def _workflow_by_mod(self) -> dict[str, dict[str, Any]]:
        workflows: dict[str, dict[str, Any]] = {}
        with connect(self._db_path) as db:
            try:
                rows = db.execute("select * from mod_workflows").fetchall()
            except sqlite3.OperationalError:
                return workflows
        for row in rows:
            data = dict(row)
            workflows[data["mod_id"].casefold()] = data
            if data.get("upstream_url"):
                workflows[_repo_key(data["upstream_url"])] = data
        return workflows

    def _resolved_workflow(
        self,
        *,
        name: str,
        repo_url: str | None,
        report: dict[str, Any] | None,
        probed: bool,
        localization_status: str,
        ai_status: str,
        workflow_by_mod: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        workflow = workflow_by_mod.get(name.casefold()) or workflow_by_mod.get(
            _repo_key(repo_url)
        )
        if workflow is None:
            if not probed:
                return {"workflow_status": "unprobed", "next_action": "probe"}
            workflow = _workflow_from_probe_row(
                mod_id=name,
                upstream_url=repo_url,
                report=report or {},
                localization_status=localization_status,
            )
        status = str(workflow.get("workflow_status") or "unprobed")
        action = str(workflow.get("next_action") or "probe")
        if ai_status == "running":
            status, action = "translating", "none"
        elif ai_status == "translated_needs_review":
            status, action = "review_pending", "review"
        elif ai_status == "merged_upstream":
            status, action = "merged", "none"
        elif ai_status == "complete" and status not in {"committed", "merged", "pr_open"}:
            status, action = "applied", "commit"
        data = dict(workflow)
        data["workflow_status"] = status
        data["next_action"] = action
        return data

    def upsert_workflows_from_probe_report(
        self,
        report: dict[str, Any],
        *,
        job_id: int | None = None,
        cache_ttl_seconds: int = DEFAULT_GITHUB_CACHE_TTL_SECONDS,
    ) -> int:
        items = report.get("items", [])
        if not isinstance(items, list):
            return 0
        expires_at = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + cache_ttl_seconds,
            tz=timezone.utc,
        ).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            status = _workflow_from_probe_row(
                mod_id=str(item.get("name") or ""),
                upstream_url=item.get("url") if isinstance(item.get("url"), str) else None,
                report=item,
                localization_status=_probe_localization_status(item),
            )
            rows.append(
                (
                    status["mod_id"],
                    status["upstream_url"],
                    status["upstream_slug"],
                    status["canonical_upstream"],
                    status["fork_slug"],
                    status["fork_status"],
                    status["localization_status"],
                    status["workflow_status"],
                    status["next_action"],
                    now,
                    expires_at,
                    job_id,
                    status["last_error"],
                    now,
                )
            )
        with connect(self._db_path) as db:
            db.executemany(
                """
                insert into mod_workflows(
                    mod_id, upstream_url, upstream_slug, canonical_upstream,
                    fork_slug, fork_status, localization_status,
                    workflow_status, next_action, last_probe_at, cache_expires_at,
                    last_job_id, last_error, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(mod_id) do update set
                    upstream_url = excluded.upstream_url,
                    upstream_slug = excluded.upstream_slug,
                    canonical_upstream = excluded.canonical_upstream,
                    fork_slug = excluded.fork_slug,
                    fork_status = excluded.fork_status,
                    localization_status = excluded.localization_status,
                    workflow_status = excluded.workflow_status,
                    next_action = excluded.next_action,
                    last_probe_at = excluded.last_probe_at,
                    cache_expires_at = excluded.cache_expires_at,
                    last_job_id = excluded.last_job_id,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            db.commit()
        return len(rows)

    def _ai_status_by_mod(self) -> dict[str, str]:
        status_by_mod: dict[str, str] = {}
        with connect(self._db_path) as db:
            for row in db.execute(
                """
                select mod_id, state
                from pull_requests
                order by updated_at asc, id asc
                """
            ).fetchall():
                mod_id = row["mod_id"]
                if row["state"] == "merged":
                    status_by_mod[mod_id.casefold()] = "merged_upstream"
                elif mod_id.casefold() not in status_by_mod:
                    status_by_mod[mod_id.casefold()] = "complete"
            for row in db.execute(
                """
                select distinct mod_id
                from review_items
                where status in ('pending', 'needs_changes')
                """
            ).fetchall():
                key = row["mod_id"].casefold()
                if status_by_mod.get(key) != "merged_upstream":
                    status_by_mod[key] = "translated_needs_review"
            for row in db.execute(
                """
                select payload_json
                from jobs
                where status in ('pending', 'running')
                  and type like '%translate%'
                """
            ).fetchall():
                mod_id = _job_mod_id(row["payload_json"])
                if mod_id and mod_id.casefold() not in status_by_mod:
                    status_by_mod[mod_id.casefold()] = "running"
        return status_by_mod

    def _latest_fork_branch_by_mod(self) -> dict[str, dict[str, Any]]:
        with connect(self._db_path) as db:
            try:
                rows = db.execute(
                    """
                    select mod_id, repo_slug, branch, state, last_commit_sha, updated_at
                    from pull_requests
                    where state = 'fork_committed'
                    order by updated_at asc, id asc
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                return {}
        return {row["mod_id"].casefold(): dict(row) for row in rows}

    def _last_updated_at(self) -> str | None:
        candidates = [
            value
            for value in (
                _iso_mtime(self._mod_index_path),
                _iso_mtime(self._probe_report_path),
            )
            if value
        ]
        with connect(self._db_path) as db:
            for table in ("jobs", "feedback", "review_items", "pull_requests"):
                row = db.execute(f"select max(updated_at) as updated_at from {table}").fetchone()
                if row and row["updated_at"]:
                    candidates.append(str(row["updated_at"]))
        return max(candidates) if candidates else None

    def admin_mods(self) -> list[dict[str, Any]]:
        review_counts = self._review_counts_by_mod()
        queue_by_mod = {
            row["mod_id"].casefold(): row
            for row in self.list_translation_queue(limit=10_000)
            if row["status"] in {"queued", "running", "failed"}
        }
        fork_by_mod = self._latest_fork_branch_by_mod()
        latest_job_by_mod = self._latest_translation_job_by_mod()
        items: list[dict[str, Any]] = []
        for item in self.mod_index_items():
            local_mod_id = item.get("translation_mod_id")
            key = str(local_mod_id or item["name"]).casefold()
            reviews = review_counts.get(key, {"pending": 0, "approved": 0})
            queue = queue_by_mod.get(key)
            fork = fork_by_mod.get(key) or fork_by_mod.get(str(item["name"]).casefold())
            latest_job = latest_job_by_mod.get(key)
            items.append(
                {
                    **item,
                    "pending_review_items": reviews["pending"],
                    "approved_review_items": reviews["approved"],
                    "queue_status": queue["status"] if queue else None,
                    "queue_id": queue["id"] if queue else None,
                    "latest_job_status": latest_job.get("status") if latest_job else None,
                    "fork_slug": fork["repo_slug"] if fork else None,
                    "latest_fork_branch_url": _github_branch_page_url(fork),
                }
            )
        return items

    def _review_counts_by_mod(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select mod_id, status, count(*) as c
                from review_items
                where status in ('pending', 'needs_changes', 'approved')
                group by mod_id, status
                """
            ).fetchall()
        for row in rows:
            key = row["mod_id"].casefold()
            item = counts.setdefault(key, {"pending": 0, "approved": 0})
            if row["status"] in {"pending", "needs_changes"}:
                item["pending"] += int(row["c"])
            elif row["status"] == "approved":
                item["approved"] += int(row["c"])
        return counts

    def _latest_translation_job_by_mod(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select *
                from jobs
                where type = 'translate_entry_loop'
                order by updated_at asc, id asc
                """
            ).fetchall()
        for row in rows:
            job = _job_row(row)
            mod_id = job["payload"].get("mod_id")
            if isinstance(mod_id, str) and mod_id:
                latest[mod_id.casefold()] = job
        return latest

    def list_mods(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select id, mod_id, repo_path, source_locale_path, target_locale_path,
                       import_enabled, created_at
                from mod_sources
                order by mod_id
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                **dict(row),
                "import_enabled": bool(row["import_enabled"]),
            }
            for row in rows
        ]

    def get_mod(self, mod_id: str) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                """
                select id, mod_id, repo_path, source_locale_path, target_locale_path,
                       import_enabled, created_at
                from mod_sources
                where mod_id = ?
                """,
                (mod_id,),
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "import_enabled": bool(row["import_enabled"])}

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "select * from jobs"
        params: list[Any] = []
        if status:
            sql += " where status = ?"
            params.append(status)
        sql += " order by created_at desc, id desc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [_job_row(row) for row in rows]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute("select * from jobs where id = ?", (job_id,)).fetchone()
        return _job_row(row) if row is not None else None

    def get_admin_settings(self) -> dict[str, Any]:
        with connect(self._db_path) as db:
            rows = db.execute("select key, value_json from app_settings").fetchall()
        values: dict[str, Any] = {}
        for row in rows:
            try:
                values[row["key"]] = json.loads(row["value_json"])
            except json.JSONDecodeError:
                values[row["key"]] = None
        interval = values.get("auto_translate_interval_hours", 5)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = 5
        return {
            "auto_translate_enabled": bool(values.get("auto_translate_enabled", False)),
            "auto_translate_interval_hours": max(1, interval),
            "last_auto_translate_at": values.get("last_auto_translate_at"),
        }

    def update_admin_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "auto_translate_enabled",
            "auto_translate_interval_hours",
            "last_auto_translate_at",
        }
        rows = [
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
            for key, value in values.items()
            if key in allowed
        ]
        if rows:
            with connect(self._db_path) as db:
                db.executemany(
                    """
                    insert into app_settings(key, value_json)
                    values (?, ?)
                    on conflict(key) do update set
                        value_json = excluded.value_json,
                        updated_at = current_timestamp
                    """,
                    rows,
                )
                db.commit()
        return self.get_admin_settings()

    def enqueue_translation(
        self,
        *,
        mod_id: str,
        source_name: str | None,
        repo_url: str | None,
    ) -> dict[str, Any]:
        priority = self._next_queue_priority()
        try:
            with connect(self._db_path) as db:
                cursor = db.execute(
                    """
                    insert into translation_queue(mod_id, source_name, repo_url, priority, status)
                    values (?, ?, ?, ?, 'queued')
                    """,
                    (mod_id, source_name, repo_url, priority),
                )
                queue_id = int(cursor.lastrowid)
                db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"mod is already queued or running: {mod_id}") from exc
        item = self.get_translation_queue_item(queue_id)
        if item is None:
            raise RuntimeError(f"created queue item disappeared: {queue_id}")
        return item

    def list_translation_queue(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = "select * from translation_queue"
        params: list[Any] = []
        if status:
            sql += " where status = ?"
            params.append(status)
        sql += " order by priority asc, created_at asc, id asc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [_queue_row(row) for row in rows]

    def get_translation_queue_item(self, queue_id: int) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                "select * from translation_queue where id = ?",
                (queue_id,),
            ).fetchone()
        return _queue_row(row) if row is not None else None

    def next_queued_translation(self) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                """
                select *
                from translation_queue
                where status = 'queued'
                order by priority asc, created_at asc, id asc
                limit 1
                """
            ).fetchone()
        return _queue_row(row) if row is not None else None

    def mark_translation_queue_running(
        self,
        queue_id: int,
        job_id: int,
    ) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            db.execute(
                """
                update translation_queue
                set status = 'running',
                    locked_job_id = ?,
                    last_error = null,
                    updated_at = current_timestamp,
                    started_at = coalesce(started_at, current_timestamp),
                    finished_at = null
                where id = ?
                """,
                (job_id, queue_id),
            )
            db.commit()
        return self.get_translation_queue_item(queue_id)

    def mark_translation_queue_finished(
        self,
        queue_id: int,
        status: str,
        *,
        last_error: str | None = None,
    ) -> dict[str, Any] | None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError(f"invalid finished queue status: {status}")
        with connect(self._db_path) as db:
            db.execute(
                """
                update translation_queue
                set status = ?,
                    last_error = ?,
                    updated_at = current_timestamp,
                    finished_at = current_timestamp
                where id = ?
                """,
                (status, last_error, queue_id),
            )
            db.commit()
        return self.get_translation_queue_item(queue_id)

    def cancel_translation_queue_item(self, queue_id: int) -> dict[str, Any]:
        item = self.mark_translation_queue_finished(queue_id, "cancelled")
        if item is None:
            raise KeyError(queue_id)
        return item

    def retry_translation_queue_item(self, queue_id: int) -> dict[str, Any]:
        priority = self._next_queue_priority()
        with connect(self._db_path) as db:
            db.execute(
                """
                update translation_queue
                set status = 'queued',
                    priority = ?,
                    locked_job_id = null,
                    last_error = null,
                    updated_at = current_timestamp,
                    started_at = null,
                    finished_at = null
                where id = ?
                """,
                (priority, queue_id),
            )
            db.commit()
        item = self.get_translation_queue_item(queue_id)
        if item is None:
            raise KeyError(queue_id)
        return item

    def reorder_translation_queue(self, queue_id: int, *, direction: str) -> dict[str, Any]:
        if direction not in {"up", "down"}:
            raise ValueError("direction must be up or down")
        current = self.get_translation_queue_item(queue_id)
        if current is None:
            raise KeyError(queue_id)
        comparator = "<" if direction == "up" else ">"
        order = "desc" if direction == "up" else "asc"
        with connect(self._db_path) as db:
            neighbor = db.execute(
                f"""
                select *
                from translation_queue
                where status = 'queued'
                  and priority {comparator} ?
                order by priority {order}, created_at {order}, id {order}
                limit 1
                """,
                (current["priority"],),
            ).fetchone()
            if neighbor is not None:
                db.execute(
                    "update translation_queue set priority = ?, updated_at = current_timestamp where id = ?",
                    (neighbor["priority"], current["id"]),
                )
                db.execute(
                    "update translation_queue set priority = ?, updated_at = current_timestamp where id = ?",
                    (current["priority"], neighbor["id"]),
                )
                db.commit()
        updated = self.get_translation_queue_item(queue_id)
        if updated is None:
            raise KeyError(queue_id)
        return updated

    def has_active_translation(self) -> bool:
        with connect(self._db_path) as db:
            job = db.execute(
                """
                select 1
                from jobs
                where type = 'translate_entry_loop'
                  and status in ('pending', 'running')
                limit 1
                """
            ).fetchone()
            queue = db.execute(
                """
                select 1
                from translation_queue
                where status = 'running'
                limit 1
                """
            ).fetchone()
        return job is not None or queue is not None

    def mark_interrupted_translation_jobs_failed(self, reason: str) -> int:
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select *
                from jobs
                where type = 'translate_entry_loop'
                  and status in ('pending', 'running')
                order by id asc
                """
            ).fetchall()
            if not rows:
                return 0
            job_ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in job_ids)
            db.execute(
                f"""
                update jobs
                set status = 'failed',
                    last_error = ?,
                    updated_at = current_timestamp,
                    finished_at = current_timestamp
                where id in ({placeholders})
                """,
                [reason, *job_ids],
            )
            event_rows = [
                (
                    job_id,
                    "warning",
                    "translation.loop.interrupted",
                    reason,
                    json.dumps({"job_id": job_id}, ensure_ascii=False, sort_keys=True),
                )
                for job_id in job_ids
            ]
            db.executemany(
                """
                insert into job_events(job_id, level, event, message, payload_json)
                values (?, ?, ?, ?, ?)
                """,
                event_rows,
            )
            db.execute(
                f"""
                update translation_queue
                set status = 'failed',
                    last_error = ?,
                    updated_at = current_timestamp,
                    finished_at = current_timestamp
                where status = 'running'
                  and locked_job_id in ({placeholders})
                """,
                [reason, *job_ids],
            )
            db.commit()
        return len(job_ids)

    def _next_queue_priority(self) -> int:
        with connect(self._db_path) as db:
            row = db.execute(
                "select coalesce(max(priority), 0) + 1000 as priority from translation_queue"
            ).fetchone()
        return int(row["priority"])

    def log_job_event(
        self,
        job_id: int,
        *,
        event: str,
        message: str,
        level: str = "info",
        payload: dict[str, Any] | None = None,
    ) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
        with connect(self._db_path) as db:
            db.execute(
                """
                insert into job_events(job_id, level, event, message, payload_json)
                values (?, ?, ?, ?, ?)
                """,
                (job_id, level, event, message, payload_json),
            )
            db.commit()

    def list_job_events(self, job_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select *
                from (
                    select *
                    from job_events
                    where job_id = ?
                    order by id desc
                    limit ?
                )
                order by id asc
                """,
                (job_id, limit),
            ).fetchall()
        return [_job_event_row(row) for row in rows]

    def create_translation_job(
        self,
        *,
        mod_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        existing = self._active_translation_job(mod_id)
        if existing is not None:
            return existing, False
        idempotency_key = (
            f"translate_entry_loop:{mod_id}:"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        )
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with connect(self._db_path) as db:
            cursor = db.execute(
                """
                insert into jobs(type, status, idempotency_key, payload_json)
                values ('translate_entry_loop', 'pending', ?, ?)
                """,
                (idempotency_key, payload_json),
            )
            job_id = int(cursor.lastrowid)
            db.commit()
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError(f"created translation job disappeared: {job_id}")
        return job, True

    def create_github_probe_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        existing = self._active_job_by_type(job_type)
        if existing is not None:
            return existing, False
        idempotency_key = (
            f"{job_type}:"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        )
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with connect(self._db_path) as db:
            cursor = db.execute(
                """
                insert into jobs(type, status, idempotency_key, payload_json)
                values (?, 'pending', ?, ?)
                """,
                (job_type, idempotency_key, payload_json),
            )
            job_id = int(cursor.lastrowid)
            db.commit()
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError(f"created GitHub probe job disappeared: {job_id}")
        return job, True

    def update_job_status(
        self,
        job_id: int,
        status: str,
        *,
        last_error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        assignments = ["status = ?", "updated_at = current_timestamp"]
        params: list[Any] = [status]
        if status == "running":
            assignments.append("started_at = coalesce(started_at, current_timestamp)")
            assignments.append("attempts = attempts + 1")
        if status in {"succeeded", "failed", "cancelled"}:
            assignments.append("finished_at = current_timestamp")
        if last_error is not None:
            assignments.append("last_error = ?")
            params.append(last_error)
        if result is not None:
            assignments.append("payload_json = ?")
            existing = self.get_job(job_id)
            payload = dict(existing["payload"] if existing else {})
            payload.update({"result": result})
            params.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        params.append(job_id)
        with connect(self._db_path) as db:
            db.execute(
                f"update jobs set {', '.join(assignments)} where id = ?",
                params,
            )
            db.commit()
        return self.get_job(job_id)

    def _active_translation_job(self, mod_id: str) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select *
                from jobs
                where type = 'translate_entry_loop'
                  and status in ('pending', 'running')
                order by created_at desc, id desc
                """
            ).fetchall()
        for row in rows:
            job = _job_row(row)
            if job["payload"].get("mod_id") == mod_id:
                return job
        return None

    def _active_job_by_type(self, job_type: str) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                """
                select *
                from jobs
                where type = ?
                  and status in ('pending', 'running')
                order by created_at desc, id desc
                limit 1
                """,
                (job_type,),
            ).fetchone()
        return _job_row(row) if row is not None else None

    def list_review_items(
        self,
        *,
        status: str | None = None,
        mod_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = "select * from review_items"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if mod_id:
            clauses.append("mod_id = ?")
            params.append(mod_id)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc, id desc limit ? offset ?"
        params.extend([limit, offset])
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_review_items(
        self,
        *,
        status: str | None = None,
        mod_id: str | None = None,
    ) -> int:
        sql = "select count(*) as c from review_items"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if mod_id:
            clauses.append("mod_id = ?")
            params.append(mod_id)
        if clauses:
            sql += " where " + " and ".join(clauses)
        with connect(self._db_path) as db:
            return int(db.execute(sql, params).fetchone()["c"])

    def list_review_mods(self, *, status: str | None = None) -> list[dict[str, Any]]:
        rows = self.list_review_items(status=status, limit=100_000)
        by_mod: dict[str, dict[str, Any]] = {}
        for row in rows:
            mod = by_mod.setdefault(
                row["mod_id"],
                {
                    "mod_id": row["mod_id"],
                    "pending_items": 0,
                    "entry_keys": set(),
                    "latest_updated_at": None,
                },
            )
            mod["pending_items"] += 1
            mod["entry_keys"].add(_review_entry_key(row["unit_key"]))
            if row["updated_at"] and (
                mod["latest_updated_at"] is None
                or row["updated_at"] > mod["latest_updated_at"]
            ):
                mod["latest_updated_at"] = row["updated_at"]
        return [
            {
                "mod_id": item["mod_id"],
                "pending_items": item["pending_items"],
                "entry_groups": len(item["entry_keys"]),
                "latest_updated_at": item["latest_updated_at"],
            }
            for item in sorted(
                by_mod.values(),
                key=lambda item: (
                    item["latest_updated_at"] or "",
                    item["pending_items"],
                    item["mod_id"],
                ),
                reverse=True,
            )
        ]

    def list_review_groups(
        self,
        *,
        status: str | None = None,
        mod_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self.list_review_items(status=status, mod_id=mod_id, limit=100_000)
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            entry_key = _review_entry_key(row["unit_key"])
            key = (row["mod_id"], entry_key)
            group = groups.setdefault(
                key,
                {
                    "mod_id": row["mod_id"],
                    "entry_key": entry_key,
                    "status": row["status"],
                    "latest_updated_at": None,
                    "items": [],
                },
            )
            group["items"].append({**row, "field": _review_field(row["unit_key"])})
            if row["updated_at"] and (
                group["latest_updated_at"] is None
                or row["updated_at"] > group["latest_updated_at"]
            ):
                group["latest_updated_at"] = row["updated_at"]
        for group in groups.values():
            group["item_count"] = len(group["items"])
        ordered = sorted(
            groups.values(),
            key=lambda item: (
                item["latest_updated_at"] or "",
                item["item_count"],
                item["mod_id"],
                item["entry_key"],
            ),
            reverse=True,
        )
        page_items = ordered[offset : offset + limit]
        for group in page_items:
            group["items"].sort(key=lambda item: _review_field_sort_key(item["field"]))
        return {"items": page_items, "total": len(ordered)}

    def get_review_item(self, item_id: int) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                "select * from review_items where id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def approve_review_group(self, update: ReviewGroupApprove) -> list[dict[str, Any]]:
        reviewed_ids = [int(item_id) for item_id in update.item_ids]
        placeholders = ",".join("?" for _ in reviewed_ids)
        now_assignments = [
            "status = 'approved'",
            "reviewer = ?",
            "comment = ?",
            "updated_at = current_timestamp",
            "reviewed_at = current_timestamp",
        ]
        with connect(self._db_path) as db:
            rows = db.execute(
                f"select * from review_items where id in ({placeholders})",
                reviewed_ids,
            ).fetchall()
            by_id = {row["id"]: dict(row) for row in rows}
            if len(by_id) != len(reviewed_ids):
                return [by_id[item_id] for item_id in reviewed_ids if item_id in by_id]
            for item_id in reviewed_ids:
                edited = update.edited_target_texts.get(str(item_id))
                assignments = list(now_assignments)
                params: list[Any] = [update.reviewer, update.comment]
                if edited is not None:
                    assignments.insert(0, "edited_target_text = ?")
                    params.insert(0, edited)
                params.append(item_id)
                db.execute(
                    f"update review_items set {', '.join(assignments)} where id = ?",
                    params,
                )
            db.commit()
            rows = db.execute(
                f"select * from review_items where id in ({placeholders})",
                reviewed_ids,
            ).fetchall()
        by_id = {row["id"]: dict(row) for row in rows}
        return [by_id[item_id] for item_id in reviewed_ids if item_id in by_id]

    def update_review_item(
        self,
        item_id: int,
        update: ReviewItemUpdate,
    ) -> dict[str, Any] | None:
        existing = self.get_review_item(item_id)
        if existing is None:
            return None
        values = update.model_dump(exclude_unset=True)
        if not values:
            return existing
        assignments = [f"{key} = ?" for key in values]
        params = list(values.values())
        assignments.append("updated_at = current_timestamp")
        if values.get("status") in {"approved", "rejected"}:
            assignments.append("reviewed_at = current_timestamp")
        params.append(item_id)
        with connect(self._db_path) as db:
            db.execute(
                f"update review_items set {', '.join(assignments)} where id = ?",
                params,
            )
            db.commit()
        return self.get_review_item(item_id)

    def list_feedback(
        self,
        *,
        status: str | None = None,
        mod_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "select * from feedback"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if mod_id:
            clauses.append("mod_id = ?")
            params.append(mod_id)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc, id desc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_tm_entries(
        self,
        *,
        mod_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = """
            select id, mod_id, unit_key, context_type, source_text, target_text,
                   quality, qdrant_point_id, source_hash, target_hash,
                   created_at, updated_at
            from tm_entries
        """
        params: list[Any] = []
        if mod_id:
            sql += " where mod_id = ?"
            params.append(mod_id)
        sql += " order by updated_at desc, id desc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_vector_outbox(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "select * from vector_outbox"
        params: list[Any] = []
        if status:
            sql += " where status = ?"
            params.append(status)
        sql += " order by created_at desc, id desc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_pull_requests(
        self,
        *,
        mod_id: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "select * from pull_requests"
        clauses: list[str] = []
        params: list[Any] = []
        if mod_id:
            clauses.append("mod_id = ?")
            params.append(mod_id)
        if state:
            clauses.append("state = ?")
            params.append(state)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc, id desc limit ?"
        params.append(limit)
        with connect(self._db_path) as db:
            rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_feedback(self, feedback_id: int) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                "select * from feedback where id = ?",
                (feedback_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_feedback_with_job(
        self,
        feedback: FeedbackCreate,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with connect(self._db_path) as db:
            cursor = db.execute(
                """
                insert into feedback(
                    mod_id, unit_key, translation_id, feedback_type,
                    suggested_text, comment
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.mod_id,
                    feedback.unit_key,
                    feedback.translation_id,
                    feedback.feedback_type,
                    feedback.suggested_text,
                    feedback.comment,
                ),
            )
            feedback_id = int(cursor.lastrowid)
            idempotency_key = f"feedback:{feedback_id}"
            payload = json.dumps(
                {"feedback_id": feedback_id, "mod_id": feedback.mod_id},
                ensure_ascii=False,
                sort_keys=True,
            )
            job_cursor = db.execute(
                """
                insert into jobs(type, status, idempotency_key, payload_json)
                values ('evaluate_feedback', 'pending', ?, ?)
                """,
                (idempotency_key, payload),
            )
            job_id = int(job_cursor.lastrowid)
            db.commit()
            feedback_row = db.execute(
                "select * from feedback where id = ?",
                (feedback_id,),
            ).fetchone()
            job_row = db.execute("select * from jobs where id = ?", (job_id,)).fetchone()
        return dict(feedback_row), _job_row(job_row)


def _count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"select count(*) as c from {table}").fetchone()["c"])


def _count_where(db: sqlite3.Connection, table: str, where: str) -> int:
    return int(
        db.execute(f"select count(*) as c from {table} where {where}").fetchone()["c"]
    )


def _job_row(row: sqlite3.Row) -> dict[str, Any]:
    payload_json = row["payload_json"]
    try:
        payload = json.loads(payload_json) if isinstance(payload_json, str) else {}
    except json.JSONDecodeError:
        payload = {}
    data = dict(row)
    data["payload"] = payload
    data.pop("payload_json", None)
    return data


def _job_event_row(row: sqlite3.Row) -> dict[str, Any]:
    payload_json = row["payload_json"]
    try:
        payload = json.loads(payload_json) if isinstance(payload_json, str) else {}
    except json.JSONDecodeError:
        payload = {}
    data = dict(row)
    data["payload"] = payload
    data.pop("payload_json", None)
    return data


def _queue_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _repo_key(url: str | None) -> str:
    return (url or "").removesuffix("/").casefold()


def _github_repo_page_url(slug: Any) -> str | None:
    if not isinstance(slug, str) or "/" not in slug:
        return None
    owner, repo = slug.strip().split("/", 1)
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def _github_branch_page_url(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    repo_slug = row.get("repo_slug")
    branch = row.get("branch")
    if not isinstance(repo_slug, str) or "/" not in repo_slug:
        return None
    if not isinstance(branch, str) or not branch:
        return None
    owner, repo = repo_slug.strip().split("/", 1)
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}/tree/{branch}"


def _verified_fork_slug(
    *,
    report: dict[str, Any] | None,
    workflow: dict[str, Any],
) -> str | None:
    workflow_fork = workflow.get("fork_slug")
    workflow_status = workflow.get("fork_status")
    if (
        isinstance(workflow_fork, str)
        and workflow_fork
        and workflow_status in {"created", "already_exists"}
    ):
        return workflow_fork
    if not isinstance(report, dict):
        return None
    report_fork = report.get("fork")
    report_status = report.get("fork_status")
    if (
        isinstance(report_fork, str)
        and report_fork
        and report_status in {"created", "already_exists"}
    ):
        return report_fork
    return None


def _match_local_mod(
    *,
    name: str,
    repo_url: str | None,
    local_mod_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [name.casefold()]
    if repo_url:
        repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        candidates.append(repo_name.casefold())
    for key in candidates:
        if key in local_mod_by_key:
            return local_mod_by_key[key]
    return None


def _workflow_from_probe_row(
    *,
    mod_id: str,
    upstream_url: str | None,
    report: dict[str, Any],
    localization_status: str,
) -> dict[str, Any]:
    fork_status = report.get("fork_status")
    fork_slug = report.get("fork")
    error = report.get("error")
    if error:
        workflow_status = "failed"
        next_action = "retry"
    elif localization_status == "complete":
        workflow_status = "upstream_complete"
        next_action = "none"
    elif fork_status in {"created", "already_exists"} and isinstance(fork_slug, str):
        workflow_status = "forked"
        next_action = "translate"
    elif report:
        workflow_status = "probed"
        next_action = "fork"
    else:
        workflow_status = "unprobed"
        next_action = "probe"
    return {
        "mod_id": mod_id,
        "upstream_url": upstream_url,
        "upstream_slug": report.get("upstream") if isinstance(report.get("upstream"), str) else None,
        "canonical_upstream": (
            report.get("canonical_upstream")
            if isinstance(report.get("canonical_upstream"), str)
            else None
        ),
        "fork_slug": fork_slug if isinstance(fork_slug, str) and fork_slug else None,
        "fork_status": fork_status if isinstance(fork_status, str) else None,
        "localization_status": localization_status,
        "workflow_status": workflow_status,
        "next_action": next_action,
        "last_error": str(error) if error else None,
    }


def _probe_localization_status(item: dict[str, Any]) -> str:
    analysis = item.get("analysis", {})
    summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
    probe_status = analysis.get("status") if isinstance(analysis, dict) else None
    status, _progress = _localization_status(
        probe_status,
        summary if isinstance(summary, dict) else {},
        probed=bool(analysis),
    )
    return status


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _localization_status(
    probe_status: Any,
    summary: dict[str, Any],
    *,
    probed: bool = True,
) -> tuple[str, int]:
    if not probed:
        return "unknown", 0
    source_units = _as_int(summary.get("source_units"))
    zh_units = _as_int(summary.get("zh_units"))
    missing = _as_int(summary.get("missing_keys"))
    untranslated = _as_int(summary.get("untranslated_keys"))
    residual = _as_int(summary.get("residual_english"))
    if probe_status in {"no_localization_dir", "no_source_files", "missing_zh_CN", None}:
        return "none", 0
    if source_units <= 0:
        return "none", 0
    progress = min(100, max(0, round((zh_units / source_units) * 100)))
    if missing == 0 and untranslated == 0 and residual == 0 and progress >= 100:
        return "complete", 100
    return "partial", progress


def _localization_label(status: str, progress: int) -> str:
    if status == "complete":
        return "完全汉化"
    if status == "partial":
        return f"汉化部分（{progress}%）"
    if status == "unknown":
        return "未探测"
    return "无汉化"


def _job_mod_id(payload_json: str | None) -> str | None:
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    mod_id = payload.get("mod_id")
    return mod_id if isinstance(mod_id, str) and mod_id else None


def _review_entry_key(unit_key: str) -> str:
    match = _REVIEW_FIELD_RE.match(unit_key)
    if match:
        return match.group("entry")
    return unit_key


def _review_field(unit_key: str) -> str:
    match = _REVIEW_FIELD_RE.match(unit_key)
    if match:
        return match.group("field")
    return "value"


def _review_field_sort_key(field: str) -> tuple[int, int, str]:
    if field == "name":
        return (0, 0, field)
    text_match = re.fullmatch(r"text\[(\d+)\]", field)
    if text_match:
        return (1, int(text_match.group(1)), field)
    unlock_match = re.fullmatch(r"unlock\[(\d+)\]", field)
    if unlock_match:
        return (2, int(unlock_match.group(1)), field)
    return (3, 0, field)
