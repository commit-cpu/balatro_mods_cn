# RAG Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable translation-memory knowledge base from local mod repositories under `data/repos`, backed by SQLite facts, Ollama `qwen3-embedding:8b` embeddings, and Qdrant vector search.

**Architecture:** SQLite is the durable source of truth for imported translation memory, import runs, and Qdrant sync state. Qdrant stores only vector points plus small payload metadata and can be rebuilt from SQLite. The first RAG loop imports existing `en-us.lua` + `zh_CN.lua` pairs, embeds normalized English source text through Ollama, upserts formal TM entries into Qdrant, then searches Qdrant and hydrates full records from SQLite.

**Tech Stack:** Python 3.12, SQLite stdlib, `httpx`, `qdrant-client`, existing `app.lua` extractor/token helpers, Ollama `/api/embed`, Qdrant REST on `127.0.0.1:6333`.

---

## Current Context

- Local repos are present under `data/repos`, including `paperback`, `Partner-API`, `Brook`, `Balatro__Origin`, `SpectralPack__Cryptid`, and `All-In-Jest`.
- Existing Lua extraction/token/patch validation is in `app/lua/`.
- `config/app.yml` already points embedding to:

```yaml
embedding:
  provider: ollama
  base_url: http://127.0.0.1:11434
  model: qwen3-embedding:8b
  batch_size: 16
```

- `qdrant.collection` is `tm_qwen3_embedding_8b_v1`.
- No SQLite migrations or RAG modules exist yet.

## File Structure

- Create `migrations/001_init.sql`: SQLite schema for migration tracking, import runs, mod sources, TM entries, and vector outbox.
- Create `migrations/002_fts.sql`: FTS5 table and triggers for lexical recall.
- Create `app/db/connection.py`: SQLite connection factory with WAL, foreign keys, row factory, and busy timeout.
- Create `app/db/migrate.py`: migration runner callable as `uv run python -m app.db.migrate`.
- Create `app/rag/ollama_embeddings.py`: Ollama embedding client and vector dimension detection.
- Create `app/rag/qdrant_store.py`: Qdrant collection creation, payload indexes, upsert/search helpers.
- Create `app/rag/tm_importer.py`: import local `en-us.lua` + `zh_CN.lua` pairs into SQLite and vector outbox.
- Create `app/rag/vector_sync.py`: consume `vector_outbox`, call Ollama, and upsert Qdrant.
- Create `app/rag/retriever.py`: query embedding, Qdrant search, SQLite hydration, and trace object.
- Create `app/cli/main.py`: `typer` CLI for `migrate`, `import-local-tm`, `sync-vectors`, `qdrant-status`, and `search`.
- Create `tests/test_db_migrate.py`, `tests/test_tm_importer.py`, `tests/test_ollama_embeddings.py`, `tests/test_qdrant_store.py`, `tests/test_vector_sync.py`, `tests/test_retriever.py`.

---

### Task 1: SQLite Migration Foundation

**Files:**
- Create: `migrations/001_init.sql`
- Create: `app/db/connection.py`
- Create: `app/db/migrate.py`
- Test: `tests/test_db_migrate.py`

- [ ] **Step 1: Write failing migration test**

```python
from pathlib import Path

from app.db.connection import connect
from app.db.migrate import migrate


def test_migrate_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"

    migrate(db_path)

    with connect(db_path) as db:
        tables = {
            row["name"]
            for row in db.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert "schema_migrations" in tables
    assert "mod_sources" in tables
    assert "tm_entries" in tables
    assert "vector_outbox" in tables
    assert "rag_traces" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_db_migrate.py`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.connection'`.

- [ ] **Step 3: Add SQLite schema**

Create `migrations/001_init.sql`:

```sql
create table if not exists schema_migrations (
    version integer primary key,
    name text not null,
    applied_at text not null default current_timestamp
);

create table if not exists mod_sources (
    id integer primary key,
    mod_id text not null unique,
    repo_path text not null,
    source_locale_path text not null,
    target_locale_path text not null,
    import_enabled integer not null default 1,
    created_at text not null default current_timestamp
);

create table if not exists import_runs (
    id integer primary key,
    mod_id text not null,
    source_locale_path text not null,
    target_locale_path text not null,
    source_unit_count integer not null,
    imported_pair_count integer not null,
    skipped_count integer not null,
    created_at text not null default current_timestamp
);

create table if not exists tm_entries (
    id integer primary key,
    mod_id text not null,
    unit_key text not null,
    context_type text not null,
    source_text text not null,
    target_text text not null,
    normalized_source text not null,
    token_signature text not null,
    source_locale text not null default 'en-us',
    target_locale text not null default 'zh_CN',
    quality text not null default 'imported_human',
    qdrant_point_id text not null unique,
    source_hash text not null,
    target_hash text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(mod_id, unit_key, source_hash, target_hash)
);

create index if not exists idx_tm_entries_mod_id on tm_entries(mod_id);
create index if not exists idx_tm_entries_context on tm_entries(context_type);
create index if not exists idx_tm_entries_signature on tm_entries(token_signature);

create table if not exists vector_outbox (
    id integer primary key,
    tm_entry_id integer not null references tm_entries(id) on delete cascade,
    operation text not null check(operation in ('upsert', 'delete')),
    collection text not null,
    status text not null default 'pending' check(status in ('pending', 'processing', 'done', 'failed')),
    attempts integer not null default 0,
    last_error text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(tm_entry_id, collection, operation)
);

create index if not exists idx_vector_outbox_status on vector_outbox(status, id);

create table if not exists rag_traces (
    id integer primary key,
    query_text text not null,
    normalized_query text not null,
    collection text not null,
    dense_top_k integer not null,
    result_count integer not null,
    trace_json text not null,
    created_at text not null default current_timestamp
);
```

- [ ] **Step 4: Add connection and migration runner**

Implement `connect(path)` with `sqlite3.connect`, `row_factory = sqlite3.Row`, `pragma foreign_keys=on`, `journal_mode=WAL`, `busy_timeout=5000`.

Implement `migrate(db_path, migrations_dir=Path("migrations"))` that applies numbered `.sql` files once and inserts into `schema_migrations`.

- [ ] **Step 5: Run test**

Run: `.venv/bin/pytest -q tests/test_db_migrate.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add migrations/001_init.sql app/db/connection.py app/db/migrate.py tests/test_db_migrate.py
git commit -m "Add SQLite migration foundation"
```

---

### Task 2: FTS5 Lexical Recall

**Files:**
- Create: `migrations/002_fts.sql`
- Modify: `tests/test_db_migrate.py`

- [ ] **Step 1: Write failing FTS test**

```python
def test_migrate_creates_tm_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)

    with connect(db_path) as db:
        row = db.execute(
            "select name from sqlite_master where name = 'tm_entries_fts'"
        ).fetchone()

    assert row is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_db_migrate.py::test_migrate_creates_tm_fts`

Expected: FAIL because `tm_entries_fts` does not exist.

- [ ] **Step 3: Add FTS migration**

Create `migrations/002_fts.sql`:

```sql
create virtual table if not exists tm_entries_fts using fts5(
    source_text,
    target_text,
    normalized_source,
    content='tm_entries',
    content_rowid='id'
);

create trigger if not exists tm_entries_ai after insert on tm_entries begin
    insert into tm_entries_fts(rowid, source_text, target_text, normalized_source)
    values (new.id, new.source_text, new.target_text, new.normalized_source);
end;

create trigger if not exists tm_entries_ad after delete on tm_entries begin
    insert into tm_entries_fts(tm_entries_fts, rowid, source_text, target_text, normalized_source)
    values ('delete', old.id, old.source_text, old.target_text, old.normalized_source);
end;

create trigger if not exists tm_entries_au after update on tm_entries begin
    insert into tm_entries_fts(tm_entries_fts, rowid, source_text, target_text, normalized_source)
    values ('delete', old.id, old.source_text, old.target_text, old.normalized_source);
    insert into tm_entries_fts(rowid, source_text, target_text, normalized_source)
    values (new.id, new.source_text, new.target_text, new.normalized_source);
end;
```

- [ ] **Step 4: Run migration tests**

Run: `.venv/bin/pytest -q tests/test_db_migrate.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/002_fts.sql tests/test_db_migrate.py
git commit -m "Add translation memory FTS index"
```

---

### Task 3: Import Local Mod Translation Memory

**Files:**
- Create: `app/rag/tm_importer.py`
- Test: `tests/test_tm_importer.py`

- [ ] **Step 1: Write failing importer test**

```python
from pathlib import Path

from app.db.connection import connect
from app.db.migrate import migrate
from app.rag.tm_importer import import_locale_pair


def test_import_locale_pair_writes_tm_entries_and_outbox(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)

    repo = tmp_path / "example_mod"
    loc = repo / "localization"
    loc.mkdir(parents=True)
    (loc / "en-us.lua").write_text(
        'return {descriptions={Joker={j_test={name="Test",text={"{C:mult}+#1#{} Mult"}}}}}',
        encoding="utf-8",
    )
    (loc / "zh_CN.lua").write_text(
        'return {descriptions={Joker={j_test={name="测试",text={"{C:mult}+#1#{} 倍率"}}}}}',
        encoding="utf-8",
    )

    result = import_locale_pair(
        db_path=db_path,
        mod_id="example_mod",
        repo_path=repo,
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        collection="tm_qwen3_embedding_8b_v1",
    )

    assert result.imported_pair_count == 2
    with connect(db_path) as db:
        tm_count = db.execute("select count(*) as c from tm_entries").fetchone()["c"]
        outbox_count = db.execute("select count(*) as c from vector_outbox").fetchone()["c"]
        row = db.execute("select source_text, target_text, token_signature from tm_entries where unit_key like '%text[0]'").fetchone()

    assert tm_count == 2
    assert outbox_count == 2
    assert row["source_text"] == "{C:mult}+#1#{} Mult"
    assert row["target_text"] == "{C:mult}+#1#{} 倍率"
    assert row["token_signature"] == "style_mult|var_1|style_reset"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_tm_importer.py`

Expected: FAIL because `app.rag.tm_importer` does not exist.

- [ ] **Step 3: Implement importer**

Implement:

```python
@dataclass(frozen=True)
class ImportResult:
    mod_id: str
    source_unit_count: int
    target_unit_count: int
    imported_pair_count: int
    skipped_count: int


def import_locale_pair(
    *,
    db_path: Path,
    mod_id: str,
    repo_path: Path,
    source_locale_path: str,
    target_locale_path: str,
    collection: str,
) -> ImportResult:
    ...
```

Rules:

- Extract both files with `LuaExtractor`.
- Align only exact matching `unit_key`.
- Skip rows where source or target is empty after `.strip()`.
- Skip rows where `validate_token_identity(source, target)` returns errors.
- Store `normalized_source = normalize_for_rag(source_text)`.
- Store `token_signature = TokenizedString.from_string(source_text).token_signature`.
- Compute `qdrant_point_id = sha256(f"{mod_id}:{unit_key}:{source_hash}:{target_hash}")`.
- Insert or ignore `tm_entries`.
- Insert or ignore `vector_outbox` operation `upsert`.
- Insert one `import_runs` row.

- [ ] **Step 4: Run importer test**

Run: `.venv/bin/pytest -q tests/test_tm_importer.py`

Expected: PASS.

- [ ] **Step 5: Add real repo smoke test**

Add a test that imports `data/repos/Balatro__Origin/localization/en-us.lua` and `zh_CN.lua` if present, expects `imported_pair_count > 1000`, and skips if the files are absent.

- [ ] **Step 6: Run RAG importer tests**

Run: `.venv/bin/pytest -q tests/test_tm_importer.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/rag/tm_importer.py tests/test_tm_importer.py
git commit -m "Import local translation memory into SQLite"
```

---

### Task 4: Ollama Embedding Client

**Files:**
- Create: `app/rag/ollama_embeddings.py`
- Test: `tests/test_ollama_embeddings.py`

- [ ] **Step 1: Write unit test using httpx mock transport**

```python
import httpx

from app.rag.ollama_embeddings import OllamaEmbeddingClient


def test_embed_texts_calls_ollama_embed_api() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        model="qwen3-embedding:8b",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    vectors = client.embed_texts(["one", "two"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert requests[0].url.path == "/api/embed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_ollama_embeddings.py`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement client**

Implement:

```python
class OllamaEmbeddingClient:
    def __init__(self, base_url: str, model: str, http_client: httpx.Client | None = None) -> None:
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embedding_dimension(self) -> int:
        return len(self.embed_texts(["dimension probe"])[0])
```

Request body:

```json
{"model": "qwen3-embedding:8b", "input": ["one", "two"]}
```

Validate response contains `embeddings` and every embedding is a non-empty list of numbers.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/test_ollama_embeddings.py`

Expected: PASS.

- [ ] **Step 5: Add manual check command to README**

Add:

```bash
curl http://127.0.0.1:11434/api/embed -d '{"model":"qwen3-embedding:8b","input":"test"}'
```

- [ ] **Step 6: Commit**

```bash
git add app/rag/ollama_embeddings.py tests/test_ollama_embeddings.py README.md
git commit -m "Add Ollama embedding client"
```

---

### Task 5: Qdrant Collection and Upsert Store

**Files:**
- Create: `app/rag/qdrant_store.py`
- Test: `tests/test_qdrant_store.py`

- [ ] **Step 1: Write Qdrant store construction test**

```python
from app.rag.qdrant_store import build_tm_point


def test_build_tm_point_uses_minimal_payload() -> None:
    point = build_tm_point(
        point_id="abc123",
        vector=[0.1, 0.2],
        tm_entry_id=7,
        mod_id="example_mod",
        unit_key="descriptions.Joker.j_test.text[0]",
        context_type="joker_description_line",
        token_signature="style_mult|var_1|style_reset",
        quality="imported_human",
    )

    assert point.id == "abc123"
    assert point.vector == [0.1, 0.2]
    assert point.payload["tm_entry_id"] == 7
    assert "target_text" not in point.payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_qdrant_store.py`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement point builder and store**

Implement:

```python
def build_tm_point(...) -> models.PointStruct:
    ...


class QdrantTmStore:
    def __init__(self, url: str, api_key: str | None, collection: str) -> None:
        ...

    def ensure_collection(self, vector_size: int) -> None:
        ...

    def upsert_points(self, points: list[models.PointStruct]) -> None:
        ...

    def search(self, vector: list[float], top_k: int, filters: dict[str, str] | None = None) -> list[ScoredPoint]:
        ...
```

Collection config:

- vector size from `OllamaEmbeddingClient.embedding_dimension()`
- distance `COSINE`
- payload indexes: `tm_entry_id`, `mod_id`, `context_type`, `token_signature`, `quality`

- [ ] **Step 4: Run unit tests**

Run: `.venv/bin/pytest -q tests/test_qdrant_store.py`

Expected: PASS.

- [ ] **Step 5: Add optional integration test marker**

Add a test skipped unless `QDRANT_API_KEY` is set and `http://127.0.0.1:6333` responds. It should create or ensure `tm_qwen3_embedding_8b_v1` with dimension 2 in a test collection named `test_tm_qwen3_embedding_8b_v1`, upsert one point, search it, then delete the test collection.

- [ ] **Step 6: Commit**

```bash
git add app/rag/qdrant_store.py tests/test_qdrant_store.py
git commit -m "Add Qdrant translation memory store"
```

---

### Task 6: Vector Outbox Sync

**Files:**
- Create: `app/rag/vector_sync.py`
- Test: `tests/test_vector_sync.py`

- [ ] **Step 1: Write failing sync test with fake embedder/store**

```python
from pathlib import Path

from app.db.connection import connect
from app.db.migrate import migrate
from app.rag.tm_importer import import_locale_pair
from app.rag.vector_sync import sync_vector_outbox


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(i), 0.0] for i, _ in enumerate(texts, start=1)]


class FakeStore:
    def __init__(self) -> None:
        self.points = []

    def upsert_points(self, points):
        self.points.extend(points)


def test_sync_vector_outbox_marks_rows_done(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    repo = tmp_path / "mod"
    (repo / "localization").mkdir(parents=True)
    (repo / "localization/en-us.lua").write_text('return {descriptions={Joker={j={name="Test"}}}}', encoding="utf-8")
    (repo / "localization/zh_CN.lua").write_text('return {descriptions={Joker={j={name="测试"}}}}', encoding="utf-8")
    import_locale_pair(
        db_path=db_path,
        mod_id="mod",
        repo_path=repo,
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        collection="tm_qwen3_embedding_8b_v1",
    )
    store = FakeStore()

    result = sync_vector_outbox(db_path=db_path, embedder=FakeEmbedder(), store=store, batch_size=16)

    assert result.synced_count == 1
    assert len(store.points) == 1
    with connect(db_path) as db:
        status = db.execute("select status from vector_outbox").fetchone()["status"]
    assert status == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_vector_sync.py`

Expected: FAIL because `app.rag.vector_sync` does not exist.

- [ ] **Step 3: Implement sync**

Implement:

```python
@dataclass(frozen=True)
class VectorSyncResult:
    synced_count: int
    failed_count: int


def sync_vector_outbox(db_path: Path, embedder, store, batch_size: int) -> VectorSyncResult:
    ...
```

Rules:

- Select pending rows joined with `tm_entries`.
- Mark selected rows `processing` before embedding.
- Embed `normalized_source` in batches.
- Build Qdrant points with minimal payload.
- Upsert to Qdrant.
- Mark rows `done` on success.
- On exception, increment `attempts`, set `status='failed'`, store `last_error`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/test_vector_sync.py tests/test_tm_importer.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/rag/vector_sync.py tests/test_vector_sync.py
git commit -m "Sync translation memory vectors to Qdrant"
```

---

### Task 7: Dense Retriever with SQLite Hydration

**Files:**
- Create: `app/rag/retriever.py`
- Test: `tests/test_retriever.py`

- [ ] **Step 1: Write failing retriever test**

```python
from pathlib import Path

from app.db.connection import connect
from app.db.migrate import migrate
from app.rag.retriever import retrieve_references


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]]


class FakeHit:
    def __init__(self, tm_entry_id: int, score: float) -> None:
        self.payload = {"tm_entry_id": tm_entry_id}
        self.score = score


class FakeStore:
    def search(self, vector, top_k, filters=None):
        return [FakeHit(1, 0.93)]


def test_retrieve_references_hydrates_qdrant_hits_from_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                id, mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (
                1, 'mod', 'k', 'joker_description_line', 'Gain +#1# Mult',
                '获得 +#1# 倍率', 'gain +<var_1> mult', 'var_1',
                'imported_human', 'p1', 's', 't'
            )
            """
        )
        db.commit()

    result = retrieve_references(
        db_path=db_path,
        query_text="Gain more Mult",
        embedder=FakeEmbedder(),
        store=FakeStore(),
        top_k=8,
    )

    assert result.references[0].target_text == "获得 +#1# 倍率"
    assert result.references[0].score == 0.93
    assert result.trace.result_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_retriever.py`

Expected: FAIL because `app.rag.retriever` does not exist.

- [ ] **Step 3: Implement retriever**

Implement:

```python
@dataclass(frozen=True)
class RetrievedReference:
    tm_entry_id: int
    mod_id: str
    unit_key: str
    context_type: str
    source_text: str
    target_text: str
    score: float


@dataclass(frozen=True)
class RetrievalTrace:
    query_text: str
    normalized_query: str
    result_count: int
    hit_ids: list[int]


@dataclass(frozen=True)
class RetrievalResult:
    references: list[RetrievedReference]
    trace: RetrievalTrace
```

Function:

```python
def retrieve_references(db_path: Path, query_text: str, embedder, store, top_k: int) -> RetrievalResult:
    ...
```

Rules:

- Normalize query with `normalize_for_rag`.
- Embed normalized query.
- Search Qdrant.
- Read full `tm_entries` rows by `tm_entry_id`.
- Preserve Qdrant score order.
- Insert one `rag_traces` row.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -q tests/test_retriever.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/rag/retriever.py tests/test_retriever.py
git commit -m "Retrieve RAG references from Qdrant and SQLite"
```

---

### Task 8: CLI for Knowledge Base Operations

**Files:**
- Create: `app/cli/main.py`
- Test: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write CLI smoke test**

```python
from typer.testing import CliRunner

from app.cli.main import app


def test_cli_has_rag_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "import-local-tm" in result.output
    assert "sync-vectors" in result.output
    assert "search" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest -q tests/test_cli.py`

Expected: FAIL because `app.cli.main` does not define commands.

- [ ] **Step 3: Implement CLI commands**

Commands:

```bash
uv run python -m app.cli.main migrate
uv run python -m app.cli.main import-local-tm --repo data/repos/Balatro__Origin --mod-id balatro_origin --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main sync-vectors --limit 100
uv run python -m app.cli.main search "Gain +#1# Mult" --top-k 5
```

Implementation should load `config/app.yml`, call `migrate`, importer, vector sync, and retriever.

- [ ] **Step 4: Update README**

Add a "Build Knowledge Base" section with:

```bash
cp .env.example .env
docker compose up -d qdrant
curl http://127.0.0.1:11434/api/embed -d '{"model":"qwen3-embedding:8b","input":"test"}'
uv run python -m app.cli.main migrate
uv run python -m app.cli.main import-local-tm --repo data/repos/Balatro__Origin --mod-id balatro_origin --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main sync-vectors --limit 100
uv run python -m app.cli.main search "Gain +#1# Mult" --top-k 5
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest -q tests/test_cli.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/cli/main.py tests/test_cli.py README.md
git commit -m "Add RAG knowledge base CLI"
```

---

### Task 9: First Local Knowledge Base Build

**Files:**
- No code changes required unless previous tasks expose bugs.

- [ ] **Step 1: Ensure services are reachable**

Run:

```bash
docker compose up -d qdrant
curl -s http://127.0.0.1:11434/api/embed -d '{"model":"qwen3-embedding:8b","input":"test"}' | jq '.embeddings[0] | length'
source .env
curl -s -H "api-key: ${QDRANT_API_KEY}" http://127.0.0.1:6333/collections
```

Expected:

- Ollama returns a positive integer vector dimension.
- Qdrant returns JSON with `collections`.

- [ ] **Step 2: Initialize SQLite**

Run:

```bash
uv run python -m app.cli.main migrate
```

Expected: `data/balatro_cn.db` exists and migrations are applied.

- [ ] **Step 3: Import local repos**

Run one command per repo with both locale files:

```bash
uv run python -m app.cli.main import-local-tm --repo data/repos/Balatro__Origin --mod-id balatro_origin --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main import-local-tm --repo data/repos/SpectralPack__Cryptid --mod-id cryptid --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main import-local-tm --repo data/repos/paperback --mod-id paperback --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main import-local-tm --repo data/repos/Partner-API --mod-id partner_api --source localization/en-us.lua --target localization/zh_CN.lua
uv run python -m app.cli.main import-local-tm --repo data/repos/Brook --mod-id brook --source localization/en-us.lua --target localization/zh_CN.lua
```

Expected: each command reports imported and skipped counts.

- [ ] **Step 4: Sync vectors**

Run:

```bash
uv run python -m app.cli.main sync-vectors --limit 500
```

Expected: pending `vector_outbox` rows move to `done`; Qdrant collection point count increases.

- [ ] **Step 5: Search smoke test**

Run:

```bash
uv run python -m app.cli.main search "Gain +#1# Mult" --top-k 5
```

Expected: output includes English source, Chinese target, score, mod id, and unit key.

---

## Self-Review

- Spec coverage: This plan covers SQLite fact storage, FTS lexical storage, local TM import, Ollama embedding, Qdrant collection/upsert/search, SQLite hydration, and CLI operations needed to build the first knowledge base.
- Deliberate gaps: Reranker and LLM translation are excluded. They should come after dense retrieval works and has trace output.
- Type consistency: `tm_entries.id` is the SQLite hydration key; Qdrant payload uses `tm_entry_id`; Qdrant point id uses `qdrant_point_id`.
- Scope check: This is one coherent subsystem: build and query the RAG knowledge base. Feedback loops, scheduler, PR publishing, and translation generation remain separate plans.
