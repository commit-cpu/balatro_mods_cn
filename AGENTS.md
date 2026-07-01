# Agent Guide

This file gives coding agents the minimum context needed to work safely in this
repository.

## Mission

Balatro CN is a FastAPI + SQLite + static frontend workbench for Chinese
localizing Balatro mods. It probes GitHub localization files, downloads selected
localization sources, runs resumable LLM translation loops, imports review
items, applies approved review edits to `zh_CN.lua`, and publishes to a fork
branch.

## Read These First

- `README.md`: human-facing project overview and commands.
- `CONTRIBUTING.md`: development workflow and PR checklist.
- `docs/developer-guide.md`: architecture and data flow.
- `docs/user-guide.md`: admin workflow from a user's perspective.
- `docs/current-translation-pipeline.md`: detailed translation JSONL and loop
  behavior.

## Important Paths

- `app/api/main.py`: FastAPI app factory, route wiring, scheduler startup.
- `app/api/admin_auth.py`: production admin suffix, cookie, and secret handling.
- `app/api/repositories.py`: SQLite-backed API repository helpers.
- `app/api/translation_workflow.py`: background translation job runner, review
  import, apply-approved behavior.
- `app/api/github_workflow.py`: selected GitHub probe and localization source
  materialization.
- `app/api/publish_workflow.py`: commit reviewed `zh_CN.lua` to fork branch.
- `app/api/queue_workflow.py`: translation queue start and scheduler tick.
- `app/api/static/app.js`: single-page frontend behavior.
- `app/cli/main.py`: translation CLI and core entry translation loop.
- `app/lua/`: Lua extraction, patching, validation, and table rewrite helpers.
- `app/rag/`: translation memory import, vector sync, retrieval, glossary.
- `migrations/`: SQLite schema migrations.
- `tests/`: targeted pytest coverage.

## Runtime Modes

Development admin:

- `ADMIN_SECRET_KEY` empty.
- Admin route is `/admin`.

Production admin:

- `ADMIN_PATH_SUFFIX` set, for example `cnops-balatro-aadmin`.
- `ADMIN_SECRET_KEY` set.
- Admin route is `/${ADMIN_PATH_SUFFIX}`.
- Unauthenticated access shows an `sk` verification form.
- Protected workflow APIs require the HttpOnly admin cookie.

## Data Flow

Typical selected-mod workflow:

1. `/api/mod-index` lists public mod metadata and workflow status.
2. Admin selects a mod and probes GitHub if needed.
3. `POST /api/github/localization-source` downloads only recognized localization
   files into `data/repos/github-localization/...` and registers a `mod_sources`
   row.
4. `POST /api/mods/{mod_id}/translate` starts `translate_entry_loop`.
5. Translation artifacts are stored in `data/artifacts/<safe_name>_entry_translate_loop`.
6. Latest preview rows become `review_items`.
7. Reviewers approve/edit items in `/admin`.
8. `POST /api/mods/{mod_id}/apply-approved` writes reviewed text into `zh_CN.lua`.
9. `POST /api/mods/{mod_id}/publish-fork` commits to
   `bot/zh-cn/{mod_id}` on the verified fork.

## Testing Guidance

Prefer targeted tests while changing code:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py -q
.venv/bin/python -m pytest tests/test_api.py::test_mod_index_ai_repo_url_prefers_latest_fork_branch -q
node --check app/api/static/app.js
git diff --check
```

Before claiming completion, run the most relevant targeted tests plus compile
checks:

```bash
.venv/bin/python -m py_compile app/api/main.py app/api/repositories.py app/api/schemas.py
node --check app/api/static/app.js
git diff --check
```

Some broad FastAPI `TestClient` combinations can hang in this environment.
Prefer repository-level tests or route-table dependency tests unless a real ASGI
request is specifically required.

## Editing Rules

- Do not revert user changes in a dirty worktree.
- Use migrations for schema changes.
- Keep route handlers thin; put database behavior in `ApiRepository`.
- Protect mutating/admin APIs with `require_admin`.
- If frontend JS changes, bump static query strings in `index.html` when browser
  cache may matter.
- Do not commit `.env`, `data/balatro_cn.db`, `data/repos/`, `data/artifacts/`,
  caches, or real tokens.

## Common Pitfalls

- `ADMIN_PATH_SUFFIX` is the full path segment, not an `admin-` suffix. If it is
  `cnops-balatro-aadmin`, the admin URL is `/cnops-balatro-aadmin`.
- Fork existence is not implied by a planned fork slug. Treat only
  `fork_status in {'created', 'already_exists'}` as verified.
- The public `当前汉化状态` reflects upstream/original localization coverage.
  AI/fork progress is separate workflow state.
- Translation jobs continue after page refresh, but the frontend may need to
  rediscover running jobs to resume polling.
- Ollama embeddings should not use external HTTP proxy for localhost calls.
