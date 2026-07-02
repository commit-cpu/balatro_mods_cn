# User Guide

This guide covers running and using Balatro CN as a local or self-hosted admin.

## Setup

```bash
uv venv --python 3.12
uv sync --extra dev
cp .env.example .env
mkdir -p data/repos
git clone https://github.com/PIPIKAI/balatro-mod-index.git data/repos/balatro-mod-index
docker compose up -d
.venv/bin/python -m app.cli.main migrate
```

The public mod list comes from `data/repos/balatro-mod-index/mods/all.json`.
Clone source: <https://github.com/PIPIKAI/balatro-mod-index/blob/main/mods/all.json>.

Configure `.env`:

```dotenv
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
LLM_CONCURRENCY=1
GITHUB_TOKEN=replace_me
```

Start the API:

```bash
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Open the public list:

```text
http://127.0.0.1:8000/mods
```

## Admin Access

For local development, leave `ADMIN_SECRET_KEY` empty and open:

```text
http://127.0.0.1:8000/admin
```

For production-like access, set:

```dotenv
ADMIN_PATH_SUFFIX=cnops-balatro-aadmin
ADMIN_SECRET_KEY=replace_with_long_random_secret
```

Restart uvicorn, then open:

```text
http://127.0.0.1:8000/cnops-balatro-aadmin
```

The page asks for `sk`. Enter `ADMIN_SECRET_KEY`. The server sets an HttpOnly
cookie and loads the admin UI. `/admin` is not available in this mode.

## Typical Translation Workflow

1. Open the admin page.
2. Select a mod from the searchable mod selector or admin management list.
3. Click `探测 GitHub` to inspect localization status.
4. Click `验证/创建 Fork` when you are ready to use the bot fork.
5. Click `启动翻译`.
6. Wait for the translation job to finish. Job status and recent events appear
   in the workflow status area.
7. Review pending entries.
8. Approve or edit review groups.
9. Click `应用已通过` to write approved text into `zh_CN.lua`.
10. Click `提交到 Fork` to commit the final file to the fork branch.

## Queue And Automatic Translation

The admin page includes queue controls:

- `加入队列`: add a mod to the translation queue.
- `立即启动`: start a queued item now.
- `上移` / `下移`: adjust queue order.
- `重试`: move a failed queue item back to queued.
- `移除`: cancel a queued or failed item.

Automatic translation settings:

- `自动翻译`: enable scheduler-driven queue execution.
- `间隔小时`: minimum interval between scheduler-started translations.

The scheduler starts at most one queued item per interval. It will not start a
new translation while another translation job is running.

## Refreshing The Page During Translation

Refreshing the browser does not stop backend translation. The job continues in
the server process. Review items are imported when the job finishes. If the page
does not automatically resume the progress display, check `/api/jobs` through
the admin UI state or wait for the review list to update.

## Status Columns

The public mod table separates upstream and AI workflow states:

- `当前汉化状态`: localization coverage detected in the original/upstream repo.
- `AI 翻译状态`: this system's translation/review/fork state.
- `流程`: next operational step for this system.

After publishing to a fork, the AI repository button links to the latest known
fork branch instead of the fork's default branch.

## Proxy Notes

Git clone/fetch proxy settings are in `.env`:

```dotenv
GIT_HTTP_PROXY=http://127.0.0.1:7890
GIT_HTTPS_PROXY=http://127.0.0.1:7890
GIT_NO_PROXY=127.0.0.1,localhost
```

GitHub API calls use normal `httpx` environment/proxy behavior. Ollama embedding
calls to localhost ignore external proxy settings. If `embedding.provider` is
`openai-compatible`, embedding requests go to the configured `base_url` and use
the API key from the env var named by `embedding.api_key_env`.

## Troubleshooting

`/cnops-balatro-aadmin` returns 404:

- Confirm `ADMIN_PATH_SUFFIX=cnops-balatro-aadmin` is in `.env` or exported.
- Restart uvicorn after changing `.env`.
- Confirm `ADMIN_SECRET_KEY` is non-empty.

`/admin` still opens in production:

- The server did not load `ADMIN_SECRET_KEY`. Check `.env`, shell exports, and
  restart uvicorn.

Translation fails on embeddings:

- For `embedding.provider=ollama`, confirm Ollama is running at the configured
  embedding base URL and the model exists locally.
- For `embedding.provider=openai-compatible`, confirm `embedding.base_url`,
  `embedding.model`, `embedding.dimensions`, and the env var named by
  `embedding.api_key_env` match your provider.

GitHub actions are slow or fail:

- Confirm `GITHUB_TOKEN` is set.
- Confirm your proxy can reach GitHub.
- Use selected-mod probe/fork operations instead of full-list operations.
