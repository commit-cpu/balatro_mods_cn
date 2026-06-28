from pathlib import Path

from app.cli.translation_brief import (
    TranslationBrief,
    apply_brief_name_seeds,
    brief_version,
    default_brief_path,
    load_translation_brief,
    render_brief_context,
    save_translation_brief,
    update_brief_from_preview,
)


def test_default_brief_path_lives_under_work_dir(tmp_path: Path) -> None:
    assert default_brief_path(tmp_path / "loop") == (
        tmp_path / "loop" / "mod_translation_brief.json"
    )


def test_load_missing_brief_returns_empty_brief(tmp_path: Path) -> None:
    brief = load_translation_brief(
        tmp_path / "missing.json",
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )

    assert brief == TranslationBrief(
        schema_version=1,
        mod_id="Familiar",
        locale="zh_CN",
        source={"repo": "data/repos/Familiar", "source": "localization/en-us.lua"},
        name_map={},
        label_map={},
        term_map={},
        forbidden_terms={},
        open_questions=[],
        proposed_updates=[],
        last_preview="",
        last_audit="",
        updated_at="",
    )


def test_save_and_load_brief_round_trips_json(tmp_path: Path) -> None:
    path = tmp_path / "brief.json"
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"

    save_translation_brief(path, brief)
    loaded = load_translation_brief(
        path,
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )

    assert loaded.name_map == {"Seal": "蜡封"}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_brief_version_changes_when_content_changes() -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    first = brief_version(brief)
    brief.name_map["Seal"] = "蜡封"
    second = brief_version(brief)

    assert first.startswith("sha256:")
    assert second.startswith("sha256:")
    assert first != second


def test_apply_brief_name_seeds_overrides_existing_seed() -> None:
    seeds = {"descriptions.Edition.e_seal": "封印"}
    source_names = {"descriptions.Edition.e_seal": "Seal"}
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"

    apply_brief_name_seeds(seeds, source_names, brief)

    assert seeds == {"descriptions.Edition.e_seal": "蜡封"}


def test_render_brief_context_lists_confirmed_names_and_terms() -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"
    brief.term_map["hand size"] = "手牌上限"

    assert render_brief_context(brief) == (
        "Confirmed mod translation brief:\n"
        "- Seal => 蜡封\n"
        "- hand size => 手牌上限"
    )


def test_update_brief_from_preview_promotes_accepted_names(tmp_path: Path) -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    rows = [
        {
            "entry_key": "descriptions.Edition.e_seal",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "蜡封",
            "source": {"name": "Seal"},
        }
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=0,
    )

    assert brief.name_map == {"Seal": "蜡封"}
    assert brief.last_preview == str(tmp_path / "preview.jsonl")
    assert brief.last_audit == str(tmp_path / "audit.json")


def test_update_brief_from_preview_skips_misc_dictionary_sentences(
    tmp_path: Path,
) -> None:
    brief = TranslationBrief.empty(
        mod_id="Mayhem",
        repo=Path("data/repos/Mayhem"),
        source="localization/default.lua",
    )
    rows = [
        {
            "entry_key": "misc.dictionary.may_notif_welcome_d2",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "在添加合适的教程之前，您应该查阅wiki",
            "source": {
                "name": "Until a proper tutorial is added, you should consult the wiki"
            },
        },
        {
            "entry_key": "misc.labels.fn_Mythic",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "神话",
            "source": {"name": "Mythic"},
        },
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=0,
    )

    assert brief.name_map == {"Mythic": "神话"}


def test_update_brief_from_preview_removes_existing_misc_dictionary_pollution(
    tmp_path: Path,
) -> None:
    brief = TranslationBrief.empty(
        mod_id="Mayhem",
        repo=Path("data/repos/Mayhem"),
        source="localization/default.lua",
    )
    brief.name_map[
        "Until a proper tutorial is added, you should consult the wiki"
    ] = "在添加合适的教程之前，您应该查阅wiki"
    rows = [
        {
            "entry_key": "misc.dictionary.may_notif_welcome_d2",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "在添加合适的教程之前，您应该查阅wiki",
            "source": {
                "name": "Until a proper tutorial is added, you should consult the wiki"
            },
        }
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=1,
    )

    assert brief.name_map == {}


def test_update_brief_from_preview_records_conflict_without_overwrite(
    tmp_path: Path,
) -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Speckled"] = "斑点"
    rows = [
        {
            "entry_key": "descriptions.Edition.e_speckle",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "斑纹",
            "source": {"name": "Speckled"},
        }
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=2,
    )
    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=2,
    )

    assert brief.name_map["Speckled"] == "斑点"
    assert brief.open_questions == [
        {
            "kind": "name_conflict",
            "source": "Speckled",
            "existing": "斑点",
            "candidate": "斑纹",
            "entry_key": "descriptions.Edition.e_speckle",
            "round": 2,
        }
    ]
