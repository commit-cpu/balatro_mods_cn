# Balatro Mods CN

Balatro Mods CN is a self-hosted Simplified Chinese localization workbench for
Balatro mods. It tracks mod repositories, probes localization coverage, runs
LLM-assisted translation, imports human review items, writes reviewed text back
to `zh_CN.lua`, and publishes the result to a GitHub fork branch.

The project is not a mod manager. Its focus is a repeatable localization
pipeline for Balatro mod translation collaboration.

## Current Capabilities

- Reads mod metadata from `balatro-mod-index`.
- Probes GitHub repositories for localization files without cloning full repos.
- Downloads only the selected mod's localization files before translation.
- Translates missing or incomplete entries with an OpenAI-compatible LLM.
- Uses RAG references, name pretranslation, Lua validation, retry loops,
  resumable artifacts, and review import.
- Provides an admin UI for per-mod management, queue ordering, scheduled
  translation, human review, applying approved text, and fork publishing.
- Links the AI repository button directly to the published fork branch when a
  fork commit exists.

## Documentation

- User guide: [docs/user-guide.md](docs/user-guide.md)
- Developer guide: [docs/developer-guide.md](docs/developer-guide.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Coding agent guide: [AGENTS.md](AGENTS.md)
- Translation pipeline details:
  [docs/current-translation-pipeline.md](docs/current-translation-pipeline.md)
- Translation quality/context strategy:
  [docs/translation-quality-context-strategy.md](docs/translation-quality-context-strategy.md)

## Translation Workflow

Typical admin flow:

1. Open the admin page.
2. Select a mod.
3. Click `探测 GitHub` to inspect upstream localization files and coverage.
4. Click `验证/创建 Fork` to verify or create the bot fork.
5. Click `启动翻译`.
6. The backend downloads only that mod's localization files, creates a local
   `mod_sources` row, and starts a translation job.
7. The translation loop reads source Lua, groups entries, prepares RAG references
   and name glossary context, calls the LLM, and writes preview artifacts.
8. The loop safely applies auto-patchable rows and imports rows that need human
   judgment into the review list.
9. Reviewers edit or approve groups in the admin UI.
10. Click `应用已通过` to write approved text into local `zh_CN.lua`.
11. Click `提交到 Fork` to commit to `bot/zh-cn/{mod_id}` on the verified fork.

Refreshing the browser during translation does not stop the backend job. Job
state and events are stored in SQLite (`jobs` / `job_events`). Translation
artifacts are stored under `data/artifacts/`.

## Requirements

Recommended runtime:

- Python 3.12
- Docker / Docker Compose
- Node.js, only for frontend JavaScript syntax checks
- `uv`, recommended for Python environment management
- Ollama or another embedding service
- OpenAI-compatible LLM API
- GitHub token for probe/fork/publish operations

## Quick Start

```bash
uv venv --python 3.12
uv sync --extra dev
cp .env.example .env
docker compose up -d
.venv/bin/python -m app.cli.main migrate
```

Start the API:

```bash
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Common pages:

- Public mod list: `http://127.0.0.1:8000/mods`
- Development admin: `http://127.0.0.1:8000/admin`
- Production admin: `http://127.0.0.1:8000/${ADMIN_PATH_SUFFIX}`

## Environment Variables

Copy `.env.example` to `.env` and configure at least:

```dotenv
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
LLM_CONCURRENCY=1

GITHUB_TOKEN=replace_me

QDRANT_API_KEY=replace_me
QDRANT_READ_ONLY_API_KEY=replace_me
```

Git/GitHub proxy settings:

```dotenv
GIT_HTTP_PROXY=http://127.0.0.1:7890
GIT_HTTPS_PROXY=http://127.0.0.1:7890
GIT_NO_PROXY=127.0.0.1,localhost
```

Production admin protection:

```dotenv
ADMIN_PATH_SUFFIX=cnops-balatro-aadmin
ADMIN_SECRET_KEY=replace_with_long_random_secret
```

When `ADMIN_SECRET_KEY` is empty, the project runs in local development mode and
`/admin` is available.

When `ADMIN_SECRET_KEY` is set:

- `/admin` is not registered and should return 404.
- The admin entry point is `/${ADMIN_PATH_SUFFIX}`.
- Unauthenticated access shows an `sk` input page.
- Successful verification sets an HttpOnly cookie.
- Workflow, review, queue, and publish APIs require that cookie.

## Qdrant And Knowledge Base

Start Qdrant:

```bash
docker compose up -d
```

Check Qdrant:

```bash
source .env
curl -H "api-key: ${QDRANT_API_KEY}" http://127.0.0.1:6333/collections
```

Check Ollama embedding:

```bash
curl http://127.0.0.1:11434/api/embed \
  -d '{"model":"qwen3-embedding:8b","input":"test"}'
```

Import existing human translations as translation memory:

```bash
.venv/bin/python -m app.cli.main import-local-tm \
  --repo data/repos/Balatro__Origin \
  --mod-id balatro_origin \
  --source localization/en-us.lua \
  --target localization/zh_CN.lua
```

Sync vectors:

```bash
.venv/bin/python -m app.cli.main sync-vectors --limit 100
```

## Admin UI

The admin page includes:

- Searchable mod selector.
- Management views: to translate, queue, running, review, applied, fork committed.
- Queue controls: enqueue, start now, move up, move down, retry, remove.
- Automatic translation settings: enabled/disabled and interval hours.
- Review list grouped by entry.
- Workflow buttons: probe GitHub, verify/create fork, start translation, apply
  approved text, publish to fork.

Automatic translation takes the next queued mod only. It does not start a new
translation while another translation job is active.

## Status Semantics

The public mod list separates upstream state from AI workflow state:

- `当前汉化状态`: localization coverage in the upstream/original repository.
- `AI 翻译状态`: this system's translation/review/fork-publish status.
- `流程`: the next suggested workflow action.

A mod can be partially localized upstream while already committed to a fork by
this system. That means the result is published to the fork, not necessarily
merged upstream.

## CLI Translation Preview

The admin UI uses the API workflow. For debugging a single repository, use the
CLI preview:

```bash
bash -lc 'set -a; source .env; set +a; .venv/bin/python -m app.cli.main translate-entry-preview-mod \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --limit 20 \
  --top-k 5 \
  --max-width 25 \
  --concurrency 1 \
  --output data/artifacts/fortlatro_entry_translate_preview.jsonl'
```

Apply preview rows:

```bash
.venv/bin/python -m app.cli.main apply-entry-preview \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --input data/artifacts/fortlatro_entry_translate_preview.jsonl \
  --output localization/zh_CN.lua
```

Allow table-level write-back when reviewed rows need it:

```bash
.venv/bin/python -m app.cli.main apply-entry-preview \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --input data/artifacts/fortlatro_entry_translate_preview.jsonl \
  --output localization/zh_CN.lua \
  --table-level
```

## Code Layout

- `app/api/`: FastAPI app, admin APIs, GitHub workflow, translation queue.
- `app/api/static/`: static frontend.
- `app/cli/`: CLI commands and core translation loop.
- `app/db/`: SQLite connection and migration runner.
- `app/github/`: GitHub probe, fork, publish, PR helpers.
- `app/lua/`: Lua parsing, extraction, patching, validation.
- `app/llm/`: LLM client and translation/review prompts.
- `app/rag/`: translation memory, Qdrant, retrieval, term checks.
- `migrations/`: SQLite schema migrations.
- `tests/`: pytest coverage.

## Tests And Checks

Common checks:

```bash
.venv/bin/python -m pytest -q
node --check app/api/static/app.js
git diff --check
```

Recommended targeted tests while developing:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py -q
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled -q
.venv/bin/python -m pytest tests/test_publish_workflow.py -q
```

Some full FastAPI `TestClient` combinations can be slow in this environment.
Prefer repository-level or targeted unit tests while iterating, then run the
full suite before submitting changes.

## Before Publishing Or Deploying

- Do not commit `.env`, real tokens, local databases, `data/repos/`, or
  `data/artifacts/`.
- Set `ADMIN_SECRET_KEY` in production.
- Ensure the GitHub token can fork and write repository contents.
- If using a proxy, verify both GitHub API and git clone/fetch access.
- For automatic translation, start with a small queue and confirm LLM, Ollama,
  Qdrant, and GitHub access are stable before increasing throughput.
