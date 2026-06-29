from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.api.schemas import FeedbackCreate, ReviewItemUpdate
from app.db.connection import connect


DEFAULT_MOD_INDEX_PATH = Path("data/repos/balatro-mod-index/mods/all.json")
DEFAULT_PROBE_REPORT_PATH = Path("data/artifacts/github_no_clone_l10n_probe/report.json")
_SKIPPED_PROBE_STATUSES = {"no_localization_dir", "no_source_files", None}
_AI_STATUS_LABELS = {
    "skipped": "跳过",
    "running": "正在汉化",
    "translated_needs_review": "已经汉化（未review）",
    "complete": "完全汉化",
    "merged_upstream": "完全汉化并且 merge到官方仓库",
}


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
                1 for item in items if item["localization_status"] != "none"
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
        return [
            self._mod_index_item(raw, report_by_url, report_by_name, ai_status_by_mod)
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
    ) -> dict[str, Any]:
        name = str(raw.get("name") or "")
        repo_url = raw.get("github_repo_url")
        repo_url = repo_url if isinstance(repo_url, str) else None
        report = report_by_url.get(_repo_key(repo_url)) or report_by_name.get(
            name.casefold()
        )
        analysis = report.get("analysis", {}) if isinstance(report, dict) else {}
        summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
        probe_status = analysis.get("status") if isinstance(analysis, dict) else None
        localization_status, progress = _localization_status(probe_status, summary)
        ai_status = ai_status_by_mod.get(name.casefold()) or ai_status_by_mod.get(
            _repo_key(repo_url)
        )
        if ai_status is None:
            ai_status = "skipped" if probe_status in _SKIPPED_PROBE_STATUSES else "skipped"
        return {
            "name": name,
            "repo_url": repo_url,
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
            "source_units": _as_int(summary.get("source_units")),
            "zh_units": _as_int(summary.get("zh_units")),
            "missing_keys": _as_int(summary.get("missing_keys")),
            "untranslated_keys": _as_int(summary.get("untranslated_keys")),
            "residual_english": _as_int(summary.get("residual_english")),
        }

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

    def get_review_item(self, item_id: int) -> dict[str, Any] | None:
        with connect(self._db_path) as db:
            row = db.execute(
                "select * from review_items where id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row is not None else None

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


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _repo_key(url: str | None) -> str:
    return (url or "").removesuffix("/").casefold()


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
) -> tuple[str, int]:
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
