# Balatro Mods CN Self-hosted Worker

Worker-first scaffold for the self-hosted Balatro mod Chinese localization MVP.

## Layout

- `app/worker.py` - Python worker entrypoint.
- `app/config.py` - YAML settings loader and git proxy environment helper.
- `config/app.yml` - non-secret runtime configuration.
- `.env.example` - secret and local override template.
- `docker-compose.yml` - local Qdrant service bound to `127.0.0.1`.
- `data/repos/` - git clone/fetch working directory.

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
