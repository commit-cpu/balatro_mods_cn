# Contributing

Thanks for helping improve Balatro CN. This project is a self-hosted Python
service with a static admin frontend. The most useful contributions are focused
fixes to translation quality, workflow reliability, GitHub publishing, UI
ergonomics, and documentation.

## Development Setup

Requirements:

- Python 3.12
- Docker, for local Qdrant
- Node.js, only for static JavaScript syntax checks
- `uv`, recommended for Python environment management

```bash
uv venv --python 3.12
uv sync --extra dev
cp .env.example .env
docker compose up -d
.venv/bin/python -m app.cli.main migrate
```

Set secrets in `.env` as needed:

```dotenv
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
GITHUB_TOKEN=replace_me
```

For local admin development, leave `ADMIN_SECRET_KEY` empty and open `/admin`.
For production-like admin testing, set:

```dotenv
ADMIN_PATH_SUFFIX=cnops-balatro-aadmin
ADMIN_SECRET_KEY=replace_with_long_random_secret
```

Then open `http://127.0.0.1:8000/cnops-balatro-aadmin`.

## Run The App

```bash
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Useful pages:

- `/mods`: public mod index.
- `/admin`: local development admin when admin auth is disabled.
- `/${ADMIN_PATH_SUFFIX}`: production-style admin login.

## Common Commands

```bash
.venv/bin/python -m app.cli.main migrate
.venv/bin/python -m pytest -q
node --check app/api/static/app.js
git diff --check
```

Targeted tests are often better while iterating:

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py -q
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled -q
```

## Project Conventions

- Keep behavior covered by targeted tests when touching shared workflows.
- Prefer repository helpers in `app/api/repositories.py` over ad hoc SQL in
  route handlers.
- Use migrations for schema changes. Do not mutate old migrations after they
  have been shared.
- Keep static frontend changes in `app/api/static/`; validate JS with
  `node --check`.
- Do not commit `.env`, local databases, caches, or downloaded repos.
- Keep generated translation artifacts under `data/artifacts/`.

## Pull Request Checklist

Before opening a PR:

- [ ] Explain the user-facing behavior change.
- [ ] Add or update tests for backend behavior.
- [ ] Run relevant targeted tests.
- [ ] Run `node --check app/api/static/app.js` after frontend edits.
- [ ] Run `git diff --check`.
- [ ] Update docs if commands, environment variables, workflow steps, or status
      semantics changed.

## Security Notes

Never include real API keys, GitHub tokens, local database dumps, or private
proxy details in commits. If a token was committed by mistake, revoke it before
opening a PR.
