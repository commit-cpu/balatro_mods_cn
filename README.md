# Balatro Mods CN Self-hosted Worker

Worker-first scaffold for the self-hosted Balatro mod Chinese localization MVP.

Current implementation notes are maintained in
[`docs/current-translation-pipeline.md`](docs/current-translation-pipeline.md).

## Layout

- `app/worker.py` - Python worker entrypoint.
- `app/config.py` - YAML settings loader and git proxy environment helper.
- `config/app.yml` - non-secret runtime configuration.
- `.env.example` - secret and local override template.
- `docker-compose.yml` - local Qdrant service bound to `127.0.0.1`.
- `data/repos/` - git clone/fetch working directory.
- `docs/current-translation-pipeline.md` - current RAG translation preview flow,
  JSONL contract, patchability rules, and project progress.

## Start Qdrant

```bash
cp .env.example .env
docker compose up -d
```

Qdrant REST and gRPC ports are bound locally:

- REST: `127.0.0.1:6333`
- gRPC: `127.0.0.1:6334`

## Run Worker

```bash
uv run python -m app.worker
```

## Build Knowledge Base

Check Ollama embedding and Qdrant first:

```bash
curl http://127.0.0.1:11434/api/embed \
  -d '{"model":"qwen3-embedding:8b","input":"test"}'

source .env
curl -H "api-key: ${QDRANT_API_KEY}" http://127.0.0.1:6333/collections
```

Initialize SQLite and import existing translated mods:

```bash
uv run python -m app.cli.main migrate

uv run python -m app.cli.main import-local-tm \
  --repo data/repos/Balatro__Origin \
  --mod-id balatro_origin \
  --source localization/en-us.lua \
  --target localization/zh_CN.lua
```

Sync pending vectors to Qdrant and run a search:

```bash
uv run python -m app.cli.main sync-vectors --limit 100
uv run python -m app.cli.main search "Gain +#1# Mult" --top-k 5
```

## Translation Preview

`translate-preview-mod` and `translate-entry-preview-mod` use an
OpenAI-compatible chat API. Configure it in `.env`:

```bash
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
LLM_CONCURRENCY=1
```

Run a dry-run entry preview without writing back to Lua:

```bash
bash -lc 'set -a; source .env; set +a; uv run --frozen python -m app.cli.main translate-entry-preview-mod \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --limit 20 \
  --top-k 5 \
  --max-width 18 \
  --concurrency 1 \
  --output data/artifacts/fortlatro_entry_translate_preview.jsonl'
```

The entry preview uses multi-query dense RAG plus deterministic glossary
references. It writes `ok`, `patchable`, `patch_warnings`, and `target_units`
for the future Lua write-back step. See
[`docs/current-translation-pipeline.md`](docs/current-translation-pipeline.md)
for the full JSONL contract and design details.

The older line-by-line preview is still available for debugging individual
strings:

```bash
bash -lc 'set -a; source .env; set +a; uv run --frozen python -m app.cli.main translate-preview-mod \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --limit 20 \
  --top-k 5 \
  --output data/artifacts/fortlatro_translate_preview.jsonl'
```

## Git Proxy

Git clone/fetch proxy defaults live in `config/app.yml`:

```yaml
git:
  http_proxy: ${GIT_HTTP_PROXY:-http://127.0.0.1:7890}
  https_proxy: ${GIT_HTTPS_PROXY:-http://127.0.0.1:7890}
  no_proxy: ${GIT_NO_PROXY:-127.0.0.1,localhost}
```

Override them in `.env` or the shell before starting the worker.

## Tests

```bash
uv run pytest -q
```
