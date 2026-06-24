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
