from pathlib import Path
from uuid import UUID

import pytest

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
    assert result.skipped_count == 0
    with connect(db_path) as db:
        tm_count = db.execute("select count(*) as c from tm_entries").fetchone()["c"]
        outbox_count = db.execute("select count(*) as c from vector_outbox").fetchone()["c"]
        row = db.execute(
            """
            select source_text, target_text, token_signature, qdrant_point_id
            from tm_entries
            where unit_key like '%text[0]'
            """
        ).fetchone()

    assert tm_count == 2
    assert outbox_count == 2
    assert row["source_text"] == "{C:mult}+#1#{} Mult"
    assert row["target_text"] == "{C:mult}+#1#{} 倍率"
    assert row["token_signature"] == "style_mult|var_1|style_reset"
    assert str(UUID(row["qdrant_point_id"])) == row["qdrant_point_id"]


def test_import_locale_pair_skips_token_mismatches(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)

    repo = tmp_path / "bad_tokens"
    loc = repo / "localization"
    loc.mkdir(parents=True)
    (loc / "en-us.lua").write_text(
        'return {descriptions={Joker={j_test={name="Test",text={"{C:mult}+#1#{} Mult"}}}}}',
        encoding="utf-8",
    )
    (loc / "zh_CN.lua").write_text(
        'return {descriptions={Joker={j_test={name="测试",text={"+#1#{} 倍率"}}}}}',
        encoding="utf-8",
    )

    result = import_locale_pair(
        db_path=db_path,
        mod_id="bad_tokens",
        repo_path=repo,
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        collection="tm_qwen3_embedding_8b_v1",
    )

    assert result.imported_pair_count == 1
    assert result.skipped_count == 1


def test_import_real_balatro_origin_if_available(tmp_path: Path) -> None:
    repo = Path("data/repos/Balatro__Origin")
    source = repo / "localization/en-us.lua"
    target = repo / "localization/zh_CN.lua"
    if not source.exists() or not target.exists():
        pytest.skip("Balatro origin localization files are not available")

    db_path = tmp_path / "real.db"
    migrate(db_path)

    result = import_locale_pair(
        db_path=db_path,
        mod_id="balatro_origin",
        repo_path=repo,
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        collection="tm_qwen3_embedding_8b_v1",
    )

    assert result.imported_pair_count > 1000
    with connect(db_path) as db:
        outbox_count = db.execute("select count(*) as c from vector_outbox").fetchone()["c"]

    assert outbox_count == result.imported_pair_count
