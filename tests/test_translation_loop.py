import json
from pathlib import Path

from app.cli.translation_loop import (
    LoopRoundArtifacts,
    audit_has_rerunnable_issues,
    default_loop_brief_path,
    default_loop_work_dir,
    loop_round_artifacts,
    write_loop_manifest,
)


def test_loop_round_artifacts_use_stable_traceable_names(tmp_path) -> None:
    work_dir = tmp_path / "familiar_loop"

    round0 = loop_round_artifacts(work_dir, 0)
    round1 = loop_round_artifacts(work_dir, 1)

    assert round0 == LoopRoundArtifacts(
        round_index=0,
        preview=work_dir / "round_00_preview.jsonl",
        rerun=work_dir / "round_00_rerun.jsonl",
        target=work_dir / "round_00_zh_CN.lua",
        audit=work_dir / "round_00_audit.json",
        rerun_keys=work_dir / "round_00_rerun_keys.txt",
    )
    assert round1.preview == work_dir / "round_01_preview.jsonl"
    assert round1.rerun == work_dir / "round_01_rerun.jsonl"
    assert round1.target == work_dir / "round_01_zh_CN.lua"
    assert round1.audit == work_dir / "round_01_audit.json"
    assert round1.rerun_keys == work_dir / "round_01_rerun_keys.txt"


def test_default_loop_brief_path_lives_under_work_dir(tmp_path) -> None:
    assert default_loop_brief_path(tmp_path / "loop") == (
        tmp_path / "loop" / "mod_translation_brief.json"
    )


def test_audit_has_rerunnable_issues_ignores_review_only_residuals() -> None:
    assert (
        audit_has_rerunnable_issues(
            {
                "failed_rows": [],
                "needs_review_rows": [],
                "residual_english": [
                    {"unit_key": "descriptions.Joker.j_rna.name", "severity": "review"}
                ],
                "untranslated_units": [],
                "label_name_mismatches": [],
                "name_inconsistencies": [],
            }
        )
        is False
    )

    assert (
        audit_has_rerunnable_issues(
            {
                "failed_rows": [],
                "needs_review_rows": [],
                "residual_english": [
                    {"unit_key": "descriptions.Joker.j_bad.text[0]", "severity": "rerun"}
                ],
                "untranslated_units": [],
                "label_name_mismatches": [],
                "name_inconsistencies": [],
            }
        )
        is True
    )


def test_write_loop_manifest_records_round_files_and_final_summary(tmp_path) -> None:
    work_dir = tmp_path / "loop"
    artifacts = [loop_round_artifacts(work_dir, 0), loop_round_artifacts(work_dir, 1)]
    final_output = tmp_path / "repo" / "localization" / "zh_CN.lua"

    write_loop_manifest(
        path=work_dir / "manifest.json",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
        output=final_output,
        work_dir=work_dir,
        max_rounds=3,
        completed_rounds=2,
        stopped_reason="no_rerun_keys",
        rounds=artifacts,
        final_audit_summary={"needs_review": 0, "residual_english": 2},
        brief_path=work_dir / "mod_translation_brief.json",
        brief_version="sha256:abc",
    )

    payload = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
    assert payload["repo"] == "data/repos/Familiar"
    assert payload["source"] == "localization/en-us.lua"
    assert payload["output"] == str(final_output)
    assert payload["work_dir"] == str(work_dir)
    assert payload["max_rounds"] == 3
    assert payload["completed_rounds"] == 2
    assert payload["stopped_reason"] == "no_rerun_keys"
    assert payload["brief_path"] == str(work_dir / "mod_translation_brief.json")
    assert payload["brief_version"] == "sha256:abc"
    assert payload["final_audit_summary"] == {
        "needs_review": 0,
        "residual_english": 2,
    }
    assert payload["rounds"][1]["preview"] == str(work_dir / "round_01_preview.jsonl")
    assert payload["rounds"][1]["rerun_keys"] == str(work_dir / "round_01_rerun_keys.txt")


def test_default_loop_work_dir_sanitizes_repo_name() -> None:
    assert default_loop_work_dir(Path("data/repos/Familiar")) == Path(
        "data/artifacts/familiar_entry_translate_loop"
    )
    assert default_loop_work_dir(Path("data/repos/EricTheToon__Fortlatro/Fortlatro")) == Path(
        "data/artifacts/fortlatro_entry_translate_loop"
    )
