from pathlib import Path

from typer.testing import CliRunner

from app.cli.main import app
from app.cli.incremental_translation import (
    apply_missing_preview_to_source,
    build_incremental_context,
)
from app.lua.extractor import LuaExtractor


def test_build_incremental_context_uses_existing_name_and_lists_missing_units(
    tmp_path: Path,
) -> None:
    source = tmp_path / "en-us.lua"
    source.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "Alpha",
                text = {
                    "Gain {C:chips}#1#{} Chips",
                    "After scoring",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "阿尔法",
                text = {
                    "获得{C:chips}#1#{}筹码",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )

    result = build_incremental_context(source, target)

    assert result.missing_unit_keys == ["descriptions.Joker.j_alpha.text[1]"]
    assert result.missing_entry_keys == ["descriptions.Joker.j_alpha"]
    assert len(result.context_rows) == 1
    row = result.context_rows[0]
    assert row["ok"] is True
    assert row["needs_review"] is False
    assert row["name"] == "阿尔法"
    assert row["text"] == []
    assert row["source"]["name"] == "Alpha"


def test_build_incremental_context_excludes_existing_residual_english(
    tmp_path: Path,
) -> None:
    source = tmp_path / "en-us.lua"
    source.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "Alpha",
                text = {
                    "Gain Chips",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "阿尔法",
                text = {
                    "获得 Chips",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )

    result = build_incremental_context(source, target)

    assert len(result.context_rows) == 1
    assert result.context_rows[0]["name"] == "阿尔法"
    assert result.context_rows[0]["text"] == []


def test_apply_missing_preview_preserves_existing_values_and_fills_missing_unit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "en-us.lua"
    source.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "Alpha",
                text = {
                    "Gain {C:chips}#1#{} Chips",
                    "After scoring",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "阿尔法",
                text = {
                    "获得{C:chips}#1#{}筹码",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    preview_rows = [
        {
            "entry_key": "descriptions.Joker.j_alpha",
            "ok": True,
            "needs_review": False,
            "target_units": {
                "name": "descriptions.Joker.j_alpha.name",
                "text": [
                    "descriptions.Joker.j_alpha.text[0]",
                    "descriptions.Joker.j_alpha.text[1]",
                ],
                "unlock": [],
            },
            "name": "不应覆盖",
            "text": ["不应覆盖", "计分后"],
            "unlock": [],
        }
    ]

    patched, stats = apply_missing_preview_to_source(
        source_path=source,
        target_path=target,
        preview_rows=preview_rows,
        missing_unit_keys={"descriptions.Joker.j_alpha.text[1]"},
    )

    output = tmp_path / "merged.lua"
    output.write_bytes(patched)
    units = {unit.unit_key: unit.source_text for unit in LuaExtractor().extract_file(output)}
    assert units["descriptions.Joker.j_alpha.name"] == "阿尔法"
    assert units["descriptions.Joker.j_alpha.text[0]"] == "获得{C:chips}#1#{}筹码"
    assert units["descriptions.Joker.j_alpha.text[1]"] == "计分后"
    assert stats == {
        "source_units": 3,
        "existing_units": 2,
        "missing_units": 1,
        "filled_missing_units": 1,
    }


def test_incremental_cli_builds_context_and_applies_missing_preview(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    loc = repo / "localization"
    loc.mkdir(parents=True)
    (loc / "en-us.lua").write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "Alpha",
                text = {
                    "Gain {C:chips}#1#{} Chips",
                    "After scoring",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    (loc / "zh_CN.lua").write_text(
        """return {
    descriptions = {
        Joker = {
            j_alpha = {
                name = "阿尔法",
                text = {
                    "获得{C:chips}#1#{}筹码",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts"
    context = artifacts / "existing_context.jsonl"
    entries = artifacts / "missing_entries.txt"
    units = artifacts / "missing_units.txt"

    runner = CliRunner()
    build = runner.invoke(
        app,
        [
            "build-incremental-entry-context",
            "--repo",
            str(repo),
            "--source",
            "localization/en-us.lua",
            "--target",
            "localization/zh_CN.lua",
            "--context-preview",
            str(context),
            "--entry-keys-output",
            str(entries),
            "--unit-keys-output",
            str(units),
        ],
    )

    assert build.exit_code == 0, build.output
    assert entries.read_text(encoding="utf-8") == "descriptions.Joker.j_alpha\n"
    assert units.read_text(encoding="utf-8") == "descriptions.Joker.j_alpha.text[1]\n"
    assert '"name": "阿尔法"' in context.read_text(encoding="utf-8")

    preview = artifacts / "missing_preview.jsonl"
    preview.write_text(
        """{"entry_key":"descriptions.Joker.j_alpha","ok":true,"needs_review":false,"target_units":{"name":"descriptions.Joker.j_alpha.name","text":["descriptions.Joker.j_alpha.text[0]","descriptions.Joker.j_alpha.text[1]"],"unlock":[]},"name":"不应覆盖","text":["不应覆盖","计分后"],"unlock":[]}
""",
        encoding="utf-8",
    )
    output = repo / "localization" / "zh_CN.merged.lua"
    apply = runner.invoke(
        app,
        [
            "apply-missing-entry-preview",
            "--repo",
            str(repo),
            "--source",
            "localization/en-us.lua",
            "--target",
            "localization/zh_CN.lua",
            "--input",
            str(preview),
            "--missing-unit-keys",
            str(units),
            "--output",
            str(output),
        ],
    )

    assert apply.exit_code == 0, apply.output
    merged_units = {
        unit.unit_key: unit.source_text for unit in LuaExtractor().extract_file(output)
    }
    assert merged_units["descriptions.Joker.j_alpha.name"] == "阿尔法"
    assert merged_units["descriptions.Joker.j_alpha.text[0]"] == "获得{C:chips}#1#{}筹码"
    assert merged_units["descriptions.Joker.j_alpha.text[1]"] == "计分后"
