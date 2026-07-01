# Developer Guide

This guide explains the codebase for contributors and coding agents.

## Architecture

Balatro CN is a Python 3.12 application with these main parts:

- FastAPI backend in `app/api/`.
- Static single-page frontend in `app/api/static/`.
- Typer CLI and translation loop in `app/cli/`.
- SQLite persistence in `app/db/` and `migrations/`.
- Public mod metadata from `data/repos/balatro-mod-index/mods/all.json`.
- GitHub probing and publishing in `app/github/` and `app/api/*_workflow.py`.
- Lua parsing/patching in `app/lua/`.
- RAG and translation memory in `app/rag/`.
- OpenAI-compatible LLM integration in `app/llm/`.

The backend is intentionally local-first. SQLite stores workflow state, review
items, jobs, queue rows, and translation memory metadata. Qdrant stores dense
vectors for translation memory retrieval.

## Backend Entry Points

`app/api/main.py` exports `app` for uvicorn and `create_app()` for tests. The
app factory:

- runs migrations,
- creates `ApiRepository`,
- mounts static files,
- wires public routes,
- wires protected admin/workflow APIs,
- starts a conservative translation queue scheduler.

`app/api/repositories.py` is the main persistence layer. Route handlers should
prefer repository methods instead of raw SQL.

## Mod Index Source

The default public mod index path is:

```text
data/repos/balatro-mod-index/mods/all.json
```

Clone it before running the app:

```bash
mkdir -p data/repos
git clone https://github.com/PIPIKAI/balatro-mod-index.git data/repos/balatro-mod-index
```

Source file: <https://github.com/PIPIKAI/balatro-mod-index/blob/main/mods/all.json>.

## Admin Security

Admin auth is controlled by `.env` or environment variables:

```dotenv
ADMIN_PATH_SUFFIX=cnops-balatro-aadmin
ADMIN_SECRET_KEY=replace_with_long_random_secret
```

With `ADMIN_SECRET_KEY` set:

- `/${ADMIN_PATH_SUFFIX}` is the only admin page route.
- unauthenticated GET returns a small `sk` form;
- successful verification sets an HttpOnly `balatro_cn_admin` cookie;
- `/admin` is not registered;
- protected APIs require `require_admin`.

With `ADMIN_SECRET_KEY` empty, local development mode keeps `/admin` open.

## Database Schema

Migrations live in `migrations/`:

- `001_init.sql`: core mod sources, translation memory, vector outbox, traces.
- `002_fts.sql`: FTS index for translation memory.
- `003_api_review_workflow.sql`: jobs, feedback, review items, pull request rows.
- `004_mod_workflows.sql`: GitHub probe/fork workflow state.
- `005_job_events.sql`: structured job event log.
- `006_admin_settings_queue.sql`: admin settings and translation queue.

Run migrations:

```bash
.venv/bin/python -m app.cli.main migrate
```

## Core Workflows

### GitHub Probe

`POST /api/github/probe` probes selected GitHub repos without full clones. The
probe report is merged into `data/artifacts/github_no_clone_l10n_probe/report.json`
and synced into `mod_workflows`.

`POST /api/github/forks` verifies or creates forks when configured with a valid
GitHub token.

### Localization Source Materialization

`POST /api/github/localization-source` downloads only recognized source/target
localization files for the selected mod and writes a `mod_sources` row. This is
what makes a public index item locally translatable.

### Translation Loop

`POST /api/mods/{mod_id}/translate` creates a `translate_entry_loop` job.
`app/api/translation_workflow.py` calls `app.cli.main.translate_entry_loop()`.

The loop:

- resumes from `data/artifacts/<safe_name>_entry_translate_loop/manifest.json`,
- pretranslates names,
- retrieves RAG references,
- runs LLM translation/review/revision,
- writes preview JSONL,
- applies safe patchable rows,
- validates Lua,
- imports pending review items.

Job progress is recorded in `job_events` and exposed through
`GET /api/jobs/{job_id}/events`.

### Review And Apply

Review rows live in `review_items`. The admin UI groups them by entry. After
approval, `POST /api/mods/{mod_id}/apply-approved` patches the current
translation candidate or source file and writes `zh_CN.lua`.

### Publish To Fork

`POST /api/mods/{mod_id}/publish-fork` commits the reviewed `zh_CN.lua` to the
verified fork branch:

```text
bot/zh-cn/{mod_id}
```

The resulting branch is stored in `pull_requests` with state `fork_committed`.
The public mod list links the AI repository button directly to the latest known
fork branch when available.

### Queue And Scheduler

`translation_queue` stores manually ordered translation work. Admin endpoints can
add, start, retry, remove, and reorder rows. The scheduler starts at most one
queued translation per configured interval and never starts a new translation
while another translation job or queue row is active.

Settings live in `app_settings`:

- `auto_translate_enabled`
- `auto_translate_interval_hours`
- `last_auto_translate_at`

## Frontend

The frontend is plain static HTML/CSS/JS:

- `app/api/static/index.html`
- `app/api/static/app.js`
- `app/api/static/styles.css`

Routes are handled client-side for `/`, `/mods`, `/about`, `/admin`, and hidden
production admin paths. When changing `app.js` or `styles.css`, bump query
strings in `index.html` if browser cache could otherwise hide changes.

Validate JS:

```bash
node --check app/api/static/app.js
```

## Testing

Run full tests:

```bash
.venv/bin/python -m pytest -q
```

Useful targeted tests:

```bash
.venv/bin/python -m pytest tests/test_db_migrate.py -q
.venv/bin/python -m pytest tests/test_translation_queue.py -q
.venv/bin/python -m pytest tests/test_publish_workflow.py -q
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled -q
```

Compile and static checks:

```bash
.venv/bin/python -m py_compile app/api/main.py app/api/repositories.py app/api/schemas.py
node --check app/api/static/app.js
git diff --check
```

## Configuration

Non-secret defaults live in `config/app.yml`. Secret/local overrides live in
`.env`.

Important environment variables:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_TRANSLATION_MODEL`
- `LLM_CONCURRENCY`
- `GITHUB_TOKEN`
- `QDRANT_API_KEY`
- `GIT_HTTP_PROXY`
- `GIT_HTTPS_PROXY`
- `GIT_NO_PROXY`
- `ADMIN_PATH_SUFFIX`
- `ADMIN_SECRET_KEY`

GitHub API calls use `GITHUB_TOKEN`, `GH_TOKEN`, or `GITHUB_PAT`.

## Contribution Boundaries

Keep refactors scoped. The translation loop, Lua patching, and RAG retrieval are
sensitive parts of the system. Add tests around behavioral changes and avoid
changing status semantics unless the UI and docs are updated together.
