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
    assert "jobs" in tables
    assert "feedback" in tables
    assert "review_items" in tables
    assert "pull_requests" in tables


def test_migrate_creates_tm_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"

    migrate(db_path)

    with connect(db_path) as db:
        row = db.execute(
            "select name from sqlite_master where name = 'tm_entries_fts'"
        ).fetchone()

    assert row is not None


def test_tm_entries_are_indexed_in_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)

    with connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (
                'mod', 'descriptions.Joker.j_test.name', 'joker_name',
                'Test Joker', '测试小丑', 'test joker', '',
                'imported_human', 'point-id', 'source-hash', 'target-hash'
            )
            """
        )
        db.commit()
        row = db.execute(
            "select rowid from tm_entries_fts where tm_entries_fts match 'joker'"
        ).fetchone()

    assert row is not None
