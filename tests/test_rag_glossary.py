from pathlib import Path

from app.db.migrate import migrate
from app.rag.glossary import extract_glossary_terms, retrieve_glossary_references


def test_extract_glossary_terms_from_styled_spans() -> None:
    assert extract_glossary_terms(
        "Creates a {C:dark_edition}Negative{} copy of a random {C:attention}consumable{}"
    ) == ["Negative", "consumable"]


def test_retrieve_glossary_references_prefers_exact_term(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "balatro_origin",
                "descriptions.Edition.e_negative.name",
                "edition_name",
                "Negative",
                "负片",
                "negative",
                "",
                "imported_human",
                "point-negative",
                "source-negative",
                "target-negative",
            ),
        )
        db.commit()

    refs = retrieve_glossary_references(
        db_path=db_path,
        query_text="{C:dark_edition}Negative{} copy",
    )

    assert refs[0].source_text == "Negative"
    assert refs[0].target_text == "负片"


def test_retrieve_glossary_references_matches_plain_name_terms(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "balatro_origin",
                "descriptions.Joker.j_perkeo.name",
                "joker_name",
                "Perkeo",
                "帕奇欧",
                "perkeo",
                "",
                "imported_human",
                "point-perkeo",
                "source-perkeo",
                "target-perkeo",
            ),
        )
        db.commit()

    refs = retrieve_glossary_references(
        db_path=db_path,
        query_text="Perkeo creates a copy",
    )

    assert [(ref.source_text, ref.target_text) for ref in refs] == [("Perkeo", "帕奇欧")]


def test_retrieve_glossary_references_does_not_promote_description_substrings(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "balatro_origin",
                "descriptions.Blind.bl_tooth.text[1]",
                "blind_description_line",
                "card played",
                "损失$1",
                "card played",
                "",
                "imported_human",
                "point-card-played",
                "source-card-played",
                "target-card-played",
            ),
        )
        db.commit()

    refs = retrieve_glossary_references(
        db_path=db_path,
        query_text="{C:attention}+2{} hand size when {C:attention}played{}",
    )

    assert refs == []


def test_retrieve_glossary_references_skips_identity_name_mappings(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "balatro_origin",
                "descriptions.Joker.j_cry_the.name",
                "joker_name",
                "The",
                "The",
                "the",
                "",
                "imported_human",
                "point-the",
                "source-the",
                "target-the",
            ),
        )
        db.commit()

    refs = retrieve_glossary_references(
        db_path=db_path,
        query_text="at the end of the shop",
    )

    assert refs == []
