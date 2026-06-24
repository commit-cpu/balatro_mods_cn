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

    def upsert_points(self, points) -> None:
        self.points.extend(points)


class FailingStore:
    def upsert_points(self, points) -> None:
        raise RuntimeError("qdrant down")


def test_sync_vector_outbox_marks_rows_done(tmp_path: Path) -> None:
    db_path = _import_one_entry(tmp_path)
    store = FakeStore()

    result = sync_vector_outbox(
        db_path=db_path,
        embedder=FakeEmbedder(),
        store=store,
        batch_size=16,
    )

    assert result.synced_count == 1
    assert result.failed_count == 0
    assert len(store.points) == 1
    assert store.points[0].payload["tm_entry_id"] == 1
    with connect(db_path) as db:
        status = db.execute("select status from vector_outbox").fetchone()["status"]
    assert status == "done"


def test_sync_vector_outbox_marks_failures(tmp_path: Path) -> None:
    db_path = _import_one_entry(tmp_path)

    result = sync_vector_outbox(
        db_path=db_path,
        embedder=FakeEmbedder(),
        store=FailingStore(),
        batch_size=16,
    )

    assert result.synced_count == 0
    assert result.failed_count == 1
    with connect(db_path) as db:
        row = db.execute(
            "select status, attempts, last_error from vector_outbox"
        ).fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert "qdrant down" in row["last_error"]


def _import_one_entry(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    repo = tmp_path / "mod"
    (repo / "localization").mkdir(parents=True)
    (repo / "localization/en-us.lua").write_text(
        'return {descriptions={Joker={j={name="Test"}}}}',
        encoding="utf-8",
    )
    (repo / "localization/zh_CN.lua").write_text(
        'return {descriptions={Joker={j={name="测试"}}}}',
        encoding="utf-8",
    )
    import_locale_pair(
        db_path=db_path,
        mod_id="mod",
        repo_path=repo,
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        collection="tm_qwen3_embedding_8b_v1",
    )
    return db_path
