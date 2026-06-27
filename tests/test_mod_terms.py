"""Tests for app.rag.mod_terms – mod-level term candidate scanning."""

from __future__ import annotations

from pathlib import Path

from app.rag.mod_terms import scan_mod_term_candidates

SOURCE = b"""return {
    descriptions={
        Joker={
            j_perkeo={
                name="Perkeo",
                text={
                    "{C:dark_edition}Negative{} copy of a random consumable",
                },
            },
        },
        Edition={
            e_fn_Mythic={
                name="Mythic",
            },
        },
    },
    misc={
        labels={
            fn_Mythic="Mythic",
            fn_Nitro="Nitro",
        },
        dictionary={
            b_buy="BUY",
        },
        quips={
            dq_1={
                "{C:attention}Watch out{} for the shop",
            },
        },
    },
}
}
"""


def _write(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "default.lua").write_bytes(SOURCE)
    return repo


def test_name_candidates_collected(tmp_path: Path) -> None:
    repo = _write(tmp_path)
    result = scan_mod_term_candidates(
        repo=repo, source="default.lua", mod_id="fortlatro"
    )
    names = {c.source for c in result.name_candidates}
    assert "Perkeo" in names
    assert "Mythic" in names
    assert all(c.unit_key.endswith(".name") for c in result.name_candidates)


def test_label_candidates_collected(tmp_path: Path) -> None:
    repo = _write(tmp_path)
    result = scan_mod_term_candidates(
        repo=repo, source="default.lua", mod_id="fortlatro"
    )
    labels = {c.source for c in result.label_candidates}
    assert "Mythic" in labels
    assert "Nitro" in labels
    assert "BUY" in labels  # dictionary entries count as label candidates
    assert all(c.unit_key.startswith("misc.") for c in result.label_candidates)


def test_styled_terms_harvested(tmp_path: Path) -> None:
    repo = _write(tmp_path)
    result = scan_mod_term_candidates(
        repo=repo, source="default.lua", mod_id="fortlatro"
    )
    assert "Negative" in result.styled_terms
    assert "Watch out" in result.styled_terms
    # de-duplicated case-insensitively
    assert len([t for t in result.styled_terms if t.lower() == "negative"]) == 1


def test_mod_id_preserved(tmp_path: Path) -> None:
    repo = _write(tmp_path)
    result = scan_mod_term_candidates(
        repo=repo, source="default.lua", mod_id="fortlatro"
    )
    assert result.mod_id == "fortlatro"
    assert result.to_dict()["mod_id"] == "fortlatro"
