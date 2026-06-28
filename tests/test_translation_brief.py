from pathlib import Path

from app.cli.translation_brief import (
    TranslationBrief,
    brief_version,
    default_brief_path,
    load_translation_brief,
    save_translation_brief,
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
