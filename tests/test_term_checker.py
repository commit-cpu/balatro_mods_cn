"""Tests for app.rag.term_checker – locked-term consistency checks."""

from __future__ import annotations

from pathlib import Path

from app.db.migrate import migrate
from app.rag.term_checker import (
    TermViolation,
    build_locked_term_map,
    check_entry_terms,
    check_term_consistency,
)

TERM_MAP = {
    "Negative": "负片",
    "Mythic": "神话",
    "hand size": "手牌上限",
    "Buy": "购买",
}


def test_styled_term_present_no_violation() -> None:
    source = "{C:dark_edition}Negative{} copy of a consumable"
    target = "{C:dark_edition}负片{}复制一张消耗牌"
    assert check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    ) == []


def test_styled_term_violation_when_translation_missing() -> None:
    source = "{C:dark_edition}Negative{} copy of a consumable"
    target = "{C:dark_edition}负面{}复制一张消耗牌"  # wrong term
    violations = check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    )
    assert len(violations) == 1
    assert violations[0].kind == "styled"
    assert violations[0].term == "Negative"
    assert violations[0].expected == "负片"


def test_exact_term_violation() -> None:
    source = "Gain +1 hand size"
    target = "获得 +1 手牌"  # missing full locked translation 手牌上限
    violations = check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    )
    kinds = [v.kind for v in violations]
    assert "exact" in kinds
    exact = next(v for v in violations if v.kind == "exact")
    assert exact.term == "hand size"
    assert exact.expected == "手牌上限"


def test_single_word_exact_term_only_checked_when_field_is_that_term() -> None:
    source = "Start with 52 copies of a random card"
    target = "开局时拥有52张同一随机卡牌"

    assert (
        check_term_consistency(
            source_text=source,
            target_text=target,
            term_map={"Copies": "多重复制"},
        )
        == []
    )


def test_exact_term_not_in_source_no_violation() -> None:
    source = "Gain +1 Mult"
    target = "获得 +1 倍数"
    assert check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    ) == []


def test_short_terms_skipped_in_exact_check() -> None:
    # "Buy" is 3 chars so it is checked; a 2-char term would not be
    source = "Press Buy to continue"
    target = "按 购买 继续"
    assert check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    ) == []


def test_styled_and_exact_not_double_reported() -> None:
    source = "{C:dark_edition}Negative{} copy"
    target = "{C:dark_edition}负面{}复制"
    violations = check_term_consistency(
        source_text=source, target_text=target, term_map=TERM_MAP
    )
    # styled span handles Negative; exact pass must not duplicate it
    assert len(violations) == 1
    assert violations[0].kind == "styled"


def test_check_entry_terms_across_fields() -> None:
    source = {
        "name": "Mythic",
        "text": ["{C:dark_edition}Negative{} copy"],
        "unlock": ["Reach hand size 5"],
    }
    target = {
        "name": "神话",
        "text": ["{C:dark_edition}负面{}复制"],
        "unlock": ["达到 手牌 5"],
    }
    violations = check_entry_terms(source=source, target=target, term_map=TERM_MAP)
    messages = [v.message for v in violations]
    assert any("[name]" not in m and "[text]" in m and "Negative" in m for m in messages)
    assert any("[unlock]" in m and "hand size" in m for m in messages)
    # name correctly translated -> no name violation
    assert not any(m.startswith("[name]") for m in messages)


def test_check_entry_terms_checks_reflowed_text_as_one_field() -> None:
    source = {
        "name": None,
        "text": ["Creates a {C:dark_edition}Negative{} copy", "of a card"],
        "unlock": [],
    }
    target = {
        "name": None,
        "text": ["创建一张复制牌", "{C:dark_edition}负片{}"],
        "unlock": [],
    }

    assert check_entry_terms(source=source, target=target, term_map=TERM_MAP) == []


def test_build_locked_term_map_mod_filter_applies_to_names(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.executemany(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "other_mod",
                    "descriptions.Edition.e_mythic.name",
                    "edition_name",
                    "Mythic",
                    "外部神话",
                    "mythic",
                    "",
                    "imported_human",
                    "point-other",
                    "source-other",
                    "target-other",
                ),
                (
                    "wanted_mod",
                    "misc.labels.fn_Nitro",
                    "misc_label",
                    "Nitro",
                    "氮气",
                    "nitro",
                    "",
                    "imported_human",
                    "point-wanted",
                    "source-wanted",
                    "target-wanted",
                ),
            ],
        )
        db.commit()

    assert build_locked_term_map(db_path, mod_id="wanted_mod") == {"Nitro": "氮气"}


def test_violation_to_dict() -> None:
    v = TermViolation(kind="exact", term="X", expected="Y", message="m")
    assert v.to_dict() == {"kind": "exact", "term": "X", "expected": "Y", "message": "m"}
