# Production Admin Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect production admin workflows, add manageable translation queueing, and make fork-published status/linking accurate.

**Architecture:** Keep public read-only pages open while adding a cookie-based admin guard around admin HTML and operational APIs. Store settings and translation queue rows in SQLite, expose repository helpers through focused protected endpoints, and run a conservative in-process scheduler that starts at most one queued translation per configured interval.

**Tech Stack:** FastAPI, SQLite migrations, Pydantic schemas, existing static HTML/CSS/JS SPA, pytest targeted tests.

---

## File Structure

- Create: `migrations/006_admin_settings_queue.sql` for `app_settings` and `translation_queue`.
- Create: `app/api/admin_auth.py` for env-driven admin path/cookie validation.
- Create: `app/api/queue_workflow.py` for queue item execution and scheduler helpers.
- Modify: `app/api/main.py` to wire admin route, protected dependencies, queue/settings/admin endpoints, and startup scheduler.
- Modify: `app/api/repositories.py` to add settings, queue, admin summary, branch URL helpers, and queue-safe job checks.
- Modify: `app/api/schemas.py` to add settings, queue, and admin mod response models.
- Modify: `app/api/static/index.html` to support the hidden admin route and management panels.
- Modify: `app/api/static/app.js` to add admin auth-aware routing, queue controls, settings controls, admin mod filters, and branch AI repo links.
- Modify: `app/api/static/styles.css` to style compact admin management and queue controls.
- Modify: `.env.example` to document `ADMIN_PATH_SUFFIX` and `ADMIN_SECRET_KEY`.
- Modify: `tests/test_db_migrate.py` for new tables.
- Modify: `tests/test_api.py` for admin auth, protected APIs, settings, admin summary, and branch link behavior.
- Create: `tests/test_translation_queue.py` for repository queue behavior and scheduler/runner helpers.

---

### Task 1: Migration for Settings and Queue

**Files:**
- Create: `migrations/006_admin_settings_queue.sql`
- Modify: `tests/test_db_migrate.py`

- [ ] **Step 1: Write the failing migration test**

Add assertions to `tests/test_db_migrate.py::test_migrate_creates_core_tables`:

```python
    assert "app_settings" in tables
    assert "translation_queue" in tables
```

Add a new test in `tests/test_db_migrate.py`:

```python
def test_translation_queue_has_active_mod_unique_index(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)

    with connect(db_path) as db:
        db.execute(
            """
            insert into translation_queue(mod_id, source_name, repo_url, priority, status)
            values ('alpha_mod', 'Alpha Mod', 'https://github.com/example/alpha', 1000, 'queued')
            """
        )
        try:
            db.execute(
                """
                insert into translation_queue(mod_id, source_name, repo_url, priority, status)
                values ('alpha_mod', 'Alpha Mod', 'https://github.com/example/alpha', 1001, 'running')
                """
            )
        except Exception as exc:
            assert "unique" in str(exc).casefold()
        else:
            raise AssertionError("duplicate active queue row was accepted")
```

- [ ] **Step 2: Run the targeted failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_db_migrate.py::test_migrate_creates_core_tables tests/test_db_migrate.py::test_translation_queue_has_active_mod_unique_index -q
```

Expected: fail because `app_settings` and `translation_queue` do not exist.

- [ ] **Step 3: Add migration**

Create `migrations/006_admin_settings_queue.sql`:

```sql
create table if not exists app_settings (
    key text primary key,
    value_json text not null,
    updated_at text not null default current_timestamp
);

insert into app_settings(key, value_json)
values
    ('auto_translate_enabled', 'false'),
    ('auto_translate_interval_hours', '5'),
    ('last_auto_translate_at', 'null')
on conflict(key) do nothing;

create table if not exists translation_queue (
    id integer primary key,
    mod_id text not null,
    source_name text,
    repo_url text,
    priority integer not null default 1000,
    status text not null default 'queued'
        check(status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    locked_job_id integer,
    last_error text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    started_at text,
    finished_at text
);

create unique index if not exists idx_translation_queue_active_mod
on translation_queue(mod_id)
where status in ('queued', 'running');

create index if not exists idx_translation_queue_status_priority
on translation_queue(status, priority, created_at);
```

- [ ] **Step 4: Run the targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_db_migrate.py::test_migrate_creates_core_tables tests/test_db_migrate.py::test_translation_queue_has_active_mod_unique_index -q
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add migrations/006_admin_settings_queue.sql tests/test_db_migrate.py
git commit -m "feat: add admin settings queue migration"
```

---

### Task 2: Repository Settings, Queue, and Branch URL Helpers

**Files:**
- Modify: `app/api/repositories.py`
- Modify: `app/api/schemas.py`
- Modify: `tests/test_translation_queue.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write repository queue tests**

Create `tests/test_translation_queue.py`:

```python
from pathlib import Path

from app.api.repositories import ApiRepository
from app.db.connection import connect
from app.db.migrate import migrate


def test_repository_adds_lists_reorders_and_cancels_queue_items(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)

    first = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )
    second = repo.enqueue_translation(
        mod_id="beta_mod",
        source_name="Beta Mod",
        repo_url="https://github.com/example/beta",
    )

    assert [item["id"] for item in repo.list_translation_queue(status="queued")] == [
        first["id"],
        second["id"],
    ]

    repo.reorder_translation_queue(second["id"], direction="up")
    assert repo.list_translation_queue(status="queued")[0]["id"] == second["id"]

    cancelled = repo.cancel_translation_queue_item(first["id"])
    assert cancelled["status"] == "cancelled"


def test_repository_rejects_duplicate_active_queue_item(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    try:
        repo.enqueue_translation(
            mod_id="alpha_mod",
            source_name="Alpha Mod",
            repo_url="https://github.com/example/alpha",
        )
    except ValueError as exc:
        assert "already queued" in str(exc)
    else:
        raise AssertionError("duplicate active queue item was accepted")


def test_repository_settings_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)

    settings = repo.get_admin_settings()
    assert settings["auto_translate_enabled"] is False
    assert settings["auto_translate_interval_hours"] == 5

    updated = repo.update_admin_settings(
        {
            "auto_translate_enabled": True,
            "auto_translate_interval_hours": 7,
        }
    )
    assert updated["auto_translate_enabled"] is True
    assert updated["auto_translate_interval_hours"] == 7
```

- [ ] **Step 2: Write branch URL test**

Add to `tests/test_api.py`:

```python
def test_mod_index_ai_repo_url_prefers_latest_fork_branch(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_workflows(
                mod_id, upstream_url, fork_slug, fork_status, workflow_status, next_action
            ) values (
                'Alpha Mod', 'https://github.com/example/alpha',
                'bot/alpha', 'already_exists', 'committed', 'pr'
            )
            """
        )
        db.execute(
            """
            insert into pull_requests(mod_id, repo_slug, branch, state, last_commit_sha)
            values ('alpha_mod', 'bot/alpha', 'bot/zh-cn/alpha_mod', 'fork_committed', 'new-sha')
            """
        )
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', '/repos/alpha', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.commit()

    client = TestClient(
        create_app(
            db_path=db_path,
            mod_index_path=mod_index_path,
            probe_report_path=probe_report_path,
        )
    )
    payload = client.get("/api/mod-index").json()
    alpha = next(item for item in payload["items"] if item["name"] == "Alpha Mod")

    assert alpha["ai_translation_repo_url"] == "https://github.com/bot/alpha/tree/bot/zh-cn/alpha_mod"
    assert alpha["ai_translation_status"] == "complete"
    assert alpha["workflow_status"] == "committed"
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py tests/test_api.py::test_mod_index_ai_repo_url_prefers_latest_fork_branch -q
```

Expected: fail because repository methods and branch URL behavior do not exist yet.

- [ ] **Step 4: Add schemas**

In `app/api/schemas.py`, add:

```python
class AdminSettingsOut(BaseModel):
    auto_translate_enabled: bool
    auto_translate_interval_hours: int = Field(ge=1)
    last_auto_translate_at: str | None = None


class AdminSettingsUpdate(BaseModel):
    auto_translate_enabled: bool | None = None
    auto_translate_interval_hours: int | None = Field(default=None, ge=1)


class TranslationQueueCreate(BaseModel):
    mod_id: str = Field(min_length=1)
    source_name: str | None = None
    repo_url: str | None = None


class TranslationQueueReorder(BaseModel):
    direction: Literal["up", "down"]


class TranslationQueueOut(BaseModel):
    id: int
    mod_id: str
    source_name: str | None
    repo_url: str | None
    priority: int
    status: str
    locked_job_id: int | None
    last_error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class TranslationQueueListResponse(BaseModel):
    items: list[TranslationQueueOut]
```

Extend `ModIndexItemOut` with:

```python
    ai_translation_branch_url: str | None = None
```

- [ ] **Step 5: Implement repository helpers**

Add methods to `ApiRepository`:

```python
    def get_admin_settings(self) -> dict[str, Any]:
        with connect(self._db_path) as db:
            rows = db.execute("select key, value_json from app_settings").fetchall()
        values = {}
        for row in rows:
            try:
                values[row["key"]] = json.loads(row["value_json"])
            except json.JSONDecodeError:
                values[row["key"]] = None
        return {
            "auto_translate_enabled": bool(values.get("auto_translate_enabled", False)),
            "auto_translate_interval_hours": int(values.get("auto_translate_interval_hours", 5)),
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
```

Add queue methods with concrete behavior:

```python
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
```

Also implement:

- `list_translation_queue(status: str | None = None, limit: int = 200)`.
- `get_translation_queue_item(queue_id: int)`.
- `next_queued_translation()`.
- `mark_translation_queue_running(queue_id: int, job_id: int)`.
- `mark_translation_queue_finished(queue_id: int, status: str, last_error: str | None = None)`.
- `cancel_translation_queue_item(queue_id: int)`.
- `retry_translation_queue_item(queue_id: int)`.
- `reorder_translation_queue(queue_id: int, direction: str)`.
- `has_active_translation()`.

- [ ] **Step 6: Implement branch URL selection**

Add latest fork commit helper in `ApiRepository`:

```python
    def _latest_fork_branch_by_mod(self) -> dict[str, dict[str, Any]]:
        with connect(self._db_path) as db:
            rows = db.execute(
                """
                select mod_id, repo_slug, branch, state, last_commit_sha, updated_at
                from pull_requests
                where state = 'fork_committed'
                order by updated_at asc, id asc
                """
            ).fetchall()
        return {row["mod_id"].casefold(): dict(row) for row in rows}
```

Pass this map into `_mod_index_item()` and set:

```python
            "ai_translation_branch_url": branch_url,
            "ai_translation_repo_url": branch_url or _github_repo_page_url(
                _verified_fork_slug(report=report, workflow=workflow)
            ),
```

where `branch_url` is `https://github.com/{repo_slug}/tree/{branch}` when a latest row exists for the matched local `mod_id`.

- [ ] **Step 7: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py tests/test_api.py::test_mod_index_ai_repo_url_prefers_latest_fork_branch -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add app/api/repositories.py app/api/schemas.py tests/test_translation_queue.py tests/test_api.py
git commit -m "feat: add translation queue repository"
```

---

### Task 3: Admin Authentication Guard

**Files:**
- Create: `app/api/admin_auth.py`
- Modify: `app/api/main.py`
- Modify: `.env.example`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write auth route/API tests**

Add to `tests/test_api.py`:

```python
def test_admin_route_requires_secret_when_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    client = TestClient(create_app(db_path=db_path))

    assert client.get("/admin").status_code == 404
    assert client.get("/admin-cnops").status_code == 401

    response = client.get("/admin-cnops?sk=secret-value")
    assert response.status_code == 200
    assert "balatro_cn_admin" in response.headers.get("set-cookie", "")
    assert client.get("/admin-cnops").status_code == 200


def test_protected_api_rejects_without_admin_cookie(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    client = TestClient(create_app(db_path=db_path))

    assert client.get("/api/mod-index").status_code == 200
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/github/probe", json={"limit": 1}).status_code == 401
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled tests/test_api.py::test_protected_api_rejects_without_admin_cookie -q
```

Expected: fail because auth guard is not implemented.

- [ ] **Step 3: Add admin auth module**

Create `app/api/admin_auth.py`:

```python
from __future__ import annotations

import hmac
import os

from fastapi import Cookie, HTTPException, Request, Response


ADMIN_COOKIE_NAME = "balatro_cn_admin"


def admin_auth_enabled() -> bool:
    return bool(os.environ.get("ADMIN_SECRET_KEY"))


def admin_path_suffix() -> str:
    return os.environ.get("ADMIN_PATH_SUFFIX", "").strip("/")


def admin_route_path() -> str:
    suffix = admin_path_suffix()
    return f"/admin-{suffix}" if suffix else "/admin"


def validate_admin_secret(value: str | None) -> None:
    secret = os.environ.get("ADMIN_SECRET_KEY") or ""
    if not secret:
        return
    if not value or not hmac.compare_digest(value, secret):
        raise HTTPException(status_code=401, detail="admin authorization required")


def set_admin_cookie(response: Response) -> None:
    secret = os.environ.get("ADMIN_SECRET_KEY") or ""
    if not secret:
        return
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        secret,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def require_admin(
    request: Request,
    balatro_cn_admin: str | None = Cookie(default=None),
) -> None:
    cookie_value = balatro_cn_admin or request.cookies.get(ADMIN_COOKIE_NAME)
    validate_admin_secret(cookie_value)
```

- [ ] **Step 4: Wire admin route and dependencies**

In `app/api/main.py`:

- Import `Request`, `Response`, `ADMIN_COOKIE_NAME`, and admin auth helpers.
- Keep `/admin` only when auth is disabled.
- Add dynamic route at `admin_route_path()`.
- Add `Depends(require_admin)` to protected route groups.

Use this shape for admin route:

```python
    @app.get(admin_route_path(), include_in_schema=False)
    def admin_page(request: Request, sk: str | None = None) -> FileResponse:
        validate_admin_secret(sk or request.cookies.get(ADMIN_COOKIE_NAME))
        page = index()
        set_admin_cookie(page)
        return page
```

Protect:

- `/api/jobs`
- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/events`
- `/api/github/probe`
- `/api/github/forks`
- `/api/github/localization-source`
- `/api/mods/{mod_id}/translate`
- `/api/mods/{mod_id}/apply-approved`
- `/api/mods/{mod_id}/publish-fork`
- `/api/review-items`
- `/api/review-groups`
- `/api/feedback`
- `/api/tm-entries`
- `/api/vector-outbox`
- `/api/pull-requests`

- [ ] **Step 5: Document env variables**

Append to `.env.example`:

```dotenv
# Production admin protection. Leave ADMIN_SECRET_KEY empty for local open mode.
ADMIN_PATH_SUFFIX=cnops
ADMIN_SECRET_KEY=
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled tests/test_api.py::test_protected_api_rejects_without_admin_cookie -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add app/api/admin_auth.py app/api/main.py .env.example tests/test_api.py
git commit -m "feat: protect production admin APIs"
```

---

### Task 4: Queue Execution and Scheduler Helpers

**Files:**
- Create: `app/api/queue_workflow.py`
- Modify: `app/api/main.py`
- Modify: `tests/test_translation_queue.py`

- [ ] **Step 1: Write runner helper tests**

Add to `tests/test_translation_queue.py`:

```python
def test_start_queue_item_creates_translation_job(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    item = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import start_translation_queue_item

    job = start_translation_queue_item(
        db_path=db_path,
        queue_id=item["id"],
        background_tasks=None,
        translation_runner=lambda db_path, job_id, payload: None,
    )

    assert job["type"] == "translate_entry_loop"
    assert repo.get_translation_queue_item(item["id"])["status"] == "running"
    assert repo.get_translation_queue_item(item["id"])["locked_job_id"] == job["id"]
```

Add:

```python
def test_scheduler_starts_one_due_item_when_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    repo.update_admin_settings(
        {
            "auto_translate_enabled": True,
            "last_auto_translate_at": None,
        }
    )
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import run_translation_queue_tick

    started = run_translation_queue_tick(
        db_path=db_path,
        translation_runner=lambda db_path, job_id, payload: None,
    )

    assert started is not None
    assert started["job"]["type"] == "translate_entry_loop"


def test_queue_item_syncs_to_succeeded_after_runner_finishes(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    item = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import start_translation_queue_item

    def finish_job(db_path: Path, job_id: int, payload: dict[str, object]) -> None:
        ApiRepository(db_path).update_job_status(job_id, "succeeded")

    start_translation_queue_item(
        db_path=db_path,
        queue_id=item["id"],
        background_tasks=None,
        translation_runner=finish_job,
    )

    assert repo.get_translation_queue_item(item["id"])["status"] == "succeeded"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py::test_start_queue_item_creates_translation_job tests/test_translation_queue.py::test_scheduler_starts_one_due_item_when_enabled tests/test_translation_queue.py::test_queue_item_syncs_to_succeeded_after_runner_finishes -q
```

Expected: fail because `queue_workflow.py` is missing.

- [ ] **Step 3: Implement queue workflow module**

Create `app/api/queue_workflow.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import BackgroundTasks

from app.api.github_workflow import materialize_github_localization_source
from app.api.repositories import ApiRepository
from app.api.schemas import TranslationStart
from app.api.translation_workflow import run_translation_job, translation_payload


TranslationRunner = Callable[[Path, int, dict[str, Any]], None]


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
    mod = repo.get_mod(item["mod_id"])
    if mod is None:
        if not item.get("repo_url"):
            raise ValueError("queued mod has no local source or repo URL")
        mod = materialize_github_localization_source(
            db_path=db_path,
            index_path=repo.mod_index_path,
            mod_name=item.get("source_name"),
            repo_url=item.get("repo_url"),
        )
    job, created = repo.create_translation_job(
        mod_id=mod["mod_id"],
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
```

Also add `run_translation_queue_tick()`:

```python
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
```

Add `_parse_time()` that accepts ISO strings and returns `None` for missing/invalid values.

- [ ] **Step 4: Add startup scheduler loop**

In `app/api/main.py`, register a lightweight startup task:

```python
    @app.on_event("startup")
    async def start_translation_queue_scheduler() -> None:
        if not load_settings().scheduler.enabled:
            return
        app.state.queue_scheduler_stop = False
        asyncio.create_task(_queue_scheduler_loop(app, resolved_db_path))
```

Implement `_queue_scheduler_loop()` in `main.py` or import from `queue_workflow.py`. It sleeps `60` seconds between checks and calls `run_translation_queue_tick()` with `app.state.translation_runner`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py::test_start_queue_item_creates_translation_job tests/test_translation_queue.py::test_scheduler_starts_one_due_item_when_enabled tests/test_translation_queue.py::test_queue_item_syncs_to_succeeded_after_runner_finishes -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/queue_workflow.py app/api/main.py tests/test_translation_queue.py
git commit -m "feat: add translation queue runner"
```

---

### Task 5: Protected Queue, Settings, and Admin Summary APIs

**Files:**
- Modify: `app/api/main.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/schemas.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write API tests**

Add to `tests/test_api.py`:

```python
def test_admin_settings_and_queue_endpoints_require_cookie_then_work(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    client = TestClient(create_app(db_path=db_path))

    assert client.get("/api/admin/settings").status_code == 401

    client.get("/admin-cnops?sk=secret-value")
    settings = client.get("/api/admin/settings")
    assert settings.status_code == 200
    assert settings.json()["auto_translate_interval_hours"] == 5

    updated = client.patch(
        "/api/admin/settings",
        json={"auto_translate_enabled": True, "auto_translate_interval_hours": 6},
    )
    assert updated.status_code == 200
    assert updated.json()["auto_translate_enabled"] is True

    queued = client.post(
        "/api/translation-queue",
        json={
            "mod_id": "alpha_mod",
            "source_name": "Alpha Mod",
            "repo_url": "https://github.com/example/alpha",
        },
    )
    assert queued.status_code == 201
    assert queued.json()["mod_id"] == "alpha_mod"
    assert client.get("/api/translation-queue").json()["items"][0]["mod_id"] == "alpha_mod"
```

Add admin mod summary test:

```python
def test_admin_mods_summary_includes_review_queue_and_fork_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    repo = ApiRepository(db_path, mod_index_path=mod_index_path, probe_report_path=probe_report_path)
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )
    with connect(db_path) as db:
        db.execute(
            """
            insert into review_items(mod_id, unit_key, source_text, status, reason)
            values ('alpha_mod', 'misc.dictionary.test', 'Test', 'pending', 'missing')
            """
        )
        db.execute(
            """
            insert into pull_requests(mod_id, repo_slug, branch, state, last_commit_sha)
            values ('alpha_mod', 'bot/alpha', 'bot/zh-cn/alpha_mod', 'fork_committed', 'sha')
            """
        )
        db.commit()

    client = TestClient(
        create_app(
            db_path=db_path,
            mod_index_path=mod_index_path,
            probe_report_path=probe_report_path,
        )
    )
    client.get("/admin-cnops?sk=secret-value")
    payload = client.get("/api/admin/mods").json()
    alpha = next(item for item in payload["items"] if item["name"] == "Alpha Mod")

    assert alpha["pending_review_items"] == 1
    assert alpha["queue_status"] == "queued"
    assert alpha["latest_fork_branch_url"] == "https://github.com/bot/alpha/tree/bot/zh-cn/alpha_mod"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py::test_admin_settings_and_queue_endpoints_require_cookie_then_work tests/test_api.py::test_admin_mods_summary_includes_review_queue_and_fork_state -q
```

Expected: fail because endpoints and admin summary are missing.

- [ ] **Step 3: Add admin summary schemas**

In `app/api/schemas.py`:

```python
class AdminModOut(BaseModel):
    name: str
    repo_url: str | None
    translation_mod_id: str | None
    translation_available: bool
    localization_status: LocalizationStatus
    localization_status_label: str
    ai_translation_status: AiTranslationStatus
    ai_translation_status_label: str
    workflow_status: str
    workflow_status_label: str
    next_action: str
    next_action_label: str
    pending_review_items: int
    approved_review_items: int
    queue_status: str | None
    queue_id: int | None
    latest_job_status: str | None
    fork_slug: str | None
    latest_fork_branch_url: str | None


class AdminModListResponse(BaseModel):
    items: list[AdminModOut]
```

- [ ] **Step 4: Implement `admin_mods()` repository helper**

In `ApiRepository`, combine `mod_index_items()`, review counts, queue rows, latest jobs, workflows, and pull requests:

```python
    def admin_mods(self) -> list[dict[str, Any]]:
        review_counts = self._review_counts_by_mod()
        queue_by_mod = {
            row["mod_id"].casefold(): row
            for row in self.list_translation_queue(limit=10_000)
            if row["status"] in {"queued", "running", "failed"}
        }
        fork_by_mod = self._latest_fork_branch_by_mod()
        latest_job_by_mod = self._latest_translation_job_by_mod()
        items = []
        for item in self.mod_index_items():
            local_mod_id = item.get("translation_mod_id")
            key = str(local_mod_id or item["name"]).casefold()
            reviews = review_counts.get(key, {"pending": 0, "approved": 0})
            queue = queue_by_mod.get(key)
            fork = fork_by_mod.get(key)
            items.append(
                {
                    **item,
                    "pending_review_items": reviews["pending"],
                    "approved_review_items": reviews["approved"],
                    "queue_status": queue["status"] if queue else None,
                    "queue_id": queue["id"] if queue else None,
                    "latest_job_status": latest_job_by_mod.get(key, {}).get("status"),
                    "fork_slug": fork["repo_slug"] if fork else None,
                    "latest_fork_branch_url": _github_branch_page_url(fork) if fork else None,
                }
            )
        return items
```

- [ ] **Step 5: Wire endpoints**

In `app/api/main.py`, add protected endpoints:

```python
    @app.get("/api/admin/settings", response_model=AdminSettingsOut, dependencies=[Depends(require_admin)])
    def get_admin_settings(repo: ApiRepository = Depends(get_repository)) -> AdminSettingsOut:
        return AdminSettingsOut(**repo.get_admin_settings())

    @app.patch("/api/admin/settings", response_model=AdminSettingsOut, dependencies=[Depends(require_admin)])
    def update_admin_settings(
        update: AdminSettingsUpdate,
        repo: ApiRepository = Depends(get_repository),
    ) -> AdminSettingsOut:
        return AdminSettingsOut(**repo.update_admin_settings(update.model_dump(exclude_none=True)))
```

Add queue endpoints:

- `GET /api/translation-queue`
- `POST /api/translation-queue`
- `PATCH /api/translation-queue/{queue_id}`
- `POST /api/translation-queue/{queue_id}/start`
- `POST /api/translation-queue/{queue_id}/retry`
- `DELETE /api/translation-queue/{queue_id}`

Return `404` for unknown queue ids and `422` for `ValueError`.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py::test_admin_settings_and_queue_endpoints_require_cookie_then_work tests/test_api.py::test_admin_mods_summary_includes_review_queue_and_fork_state -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add app/api/main.py app/api/repositories.py app/api/schemas.py tests/test_api.py
git commit -m "feat: expose admin queue APIs"
```

---

### Task 6: Frontend Admin Management UI and Branch Links

**Files:**
- Modify: `app/api/static/index.html`
- Modify: `app/api/static/app.js`
- Modify: `app/api/static/styles.css`

- [ ] **Step 1: Add admin management markup**

In `app/api/static/index.html`, inside `#page-admin` before `.workflow-toolbar`, add:

```html
        <div class="panel admin-settings">
          <label>
            <input id="auto-translate-enabled" type="checkbox" />
            <span data-i18n="admin.autoTranslate">自动翻译</span>
          </label>
          <label>
            <span data-i18n="admin.intervalHours">间隔小时</span>
            <input id="auto-translate-hours" type="number" min="1" step="1" value="5" />
          </label>
          <button type="button" id="save-admin-settings" data-i18n="admin.saveSettings">保存设置</button>
        </div>

        <div class="panel admin-management">
          <div class="admin-tabs" id="admin-mod-tabs"></div>
          <div class="admin-mod-list" id="admin-mod-list"></div>
        </div>
```

- [ ] **Step 2: Add i18n labels and state**

In `app/api/static/app.js`, add Chinese/English labels for:

- `admin.autoTranslate`
- `admin.intervalHours`
- `admin.saveSettings`
- `admin.tabTodo`
- `admin.tabQueue`
- `admin.tabRunning`
- `admin.tabReview`
- `admin.tabApplied`
- `admin.tabCommitted`
- `admin.queueAdd`
- `admin.queueStart`
- `admin.queueRetry`
- `admin.queueRemove`
- `admin.queueUp`
- `admin.queueDown`

Extend `state.workflow`:

```javascript
    adminMods: [],
    queueItems: [],
    adminFilter: "todo",
```

- [ ] **Step 3: Load settings and admin mods**

Add:

```javascript
async function loadAdminManagement() {
  const [settings, mods, queue] = await Promise.all([
    api("/api/admin/settings"),
    api("/api/admin/mods"),
    api("/api/translation-queue"),
  ]);
  renderAdminSettings(settings);
  state.workflow.adminMods = mods.items || [];
  state.workflow.queueItems = queue.items || [];
  renderAdminTabs();
  renderAdminModList();
}
```

Call `await loadAdminManagement()` inside `loadReviews()` before or after `loadWorkflowMods()`.

- [ ] **Step 4: Render admin tabs and rows**

Add:

```javascript
function adminModMatchesFilter(item) {
  if (state.workflow.adminFilter === "queue") return Boolean(item.queue_status);
  if (state.workflow.adminFilter === "running") return item.latest_job_status === "running" || item.queue_status === "running";
  if (state.workflow.adminFilter === "review") return item.pending_review_items > 0;
  if (state.workflow.adminFilter === "applied") return item.ai_translation_status === "complete" && item.workflow_status !== "committed";
  if (state.workflow.adminFilter === "committed") return item.workflow_status === "committed" || Boolean(item.latest_fork_branch_url);
  return item.next_action === "translate" || item.translation_available || Boolean(item.repo_url);
}
```

Render compact rows with action buttons using `data-admin-action`.

- [ ] **Step 5: Wire admin actions**

In the existing body click handler, before review action handling, add support for:

- `queue-add`: `POST /api/translation-queue`.
- `queue-start`: `POST /api/translation-queue/{id}/start`.
- `queue-retry`: `POST /api/translation-queue/{id}/retry`.
- `queue-remove`: `DELETE /api/translation-queue/{id}`.
- `queue-up/down`: `PATCH /api/translation-queue/{id}`.

After each action, reload admin management and current review state.

- [ ] **Step 6: Save admin settings**

Add listener:

```javascript
document.querySelector("#save-admin-settings").addEventListener("click", async () => {
  const enabled = document.querySelector("#auto-translate-enabled").checked;
  const hours = Number(document.querySelector("#auto-translate-hours").value || 5);
  const settings = await api("/api/admin/settings", {
    method: "PATCH",
    body: JSON.stringify({
      auto_translate_enabled: enabled,
      auto_translate_interval_hours: Math.max(1, hours),
    }),
  });
  renderAdminSettings(settings);
});
```

- [ ] **Step 7: Update route detection and version**

Change:

```javascript
function routeFromPath(pathname) {
  if (pathname === "/admin" || pathname.startsWith("/admin-")) return "admin";
```

Bump `app.js` and `styles.css` query strings in `index.html` to:

```html
?v=20260701-production-admin-queue
```

- [ ] **Step 8: Add CSS**

Add compact styles:

```css
.admin-settings,
.admin-management {
  display: grid;
  gap: 12px;
}

.admin-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.admin-mod-list {
  display: grid;
  gap: 8px;
}

.admin-mod-row {
  display: grid;
  grid-template-columns: minmax(160px, 1.4fr) repeat(3, minmax(90px, auto));
  gap: 8px;
  align-items: center;
}

.admin-mod-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

Ensure the mobile media query collapses `.admin-mod-row` to one column.

- [ ] **Step 9: Verify frontend syntax**

Run:

```bash
node --check app/api/static/app.js
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add app/api/static/index.html app/api/static/app.js app/api/static/styles.css
git commit -m "feat: add admin queue management UI"
```

---

### Task 7: Final Verification and Production Notes

**Files:**
- Modify: `README.md`
- Verify: touched Python/JS files

- [ ] **Step 1: Document production env**

Add to `README.md` under API/admin instructions:

Add this text:

```text
### Production admin protection

Set these environment variables before starting uvicorn:

ADMIN_PATH_SUFFIX=cnops
ADMIN_SECRET_KEY=replace_with_long_random_secret

Then open `/admin-cnops?sk=replace_with_long_random_secret` once. The server sets an HttpOnly cookie and subsequent admin API calls use that cookie. Public pages and `/api/mod-index` remain readable without the cookie.
```

- [ ] **Step 2: Run Python compile checks**

Run:

```bash
.venv/bin/python -m py_compile app/api/main.py app/api/repositories.py app/api/schemas.py app/api/admin_auth.py app/api/queue_workflow.py
```

Expected: no output.

- [ ] **Step 3: Run targeted backend tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_db_migrate.py tests/test_translation_queue.py tests/test_api.py::test_admin_route_requires_secret_when_enabled tests/test_api.py::test_protected_api_rejects_without_admin_cookie tests/test_api.py::test_admin_settings_and_queue_endpoints_require_cookie_then_work tests/test_api.py::test_admin_mods_summary_includes_review_queue_and_fork_state tests/test_api.py::test_mod_index_ai_repo_url_prefers_latest_fork_branch -q
```

Expected: pass.

- [ ] **Step 4: Run frontend syntax check**

Run:

```bash
node --check app/api/static/app.js
```

Expected: pass.

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit docs and final polish**

```bash
git add README.md
git commit -m "docs: document production admin setup"
```

---

## Self-Review

- Spec coverage: admin suffix/cookie security, protected APIs, settings, queue ordering, scheduler, admin management UI, status semantics, and branch links are each covered by a task.
- Placeholder scan: no placeholder directives remain.
- Type consistency: queue status values match the migration and schemas; settings keys match the design document; branch URL field is consistently named `ai_translation_branch_url` in the public index and `latest_fork_branch_url` in admin summaries.
- Scope: upstream PR creation, account systems, and distributed workers remain out of scope, matching the approved design.
