"""Mod-level name/label candidate term scanning.

Phase 1 quality work: before translating a mod, harvest its name and label
candidates plus styled-span terms so they can be locked into a glossary and
checked for consistency. See ``docs/translation-quality-context-strategy.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.lua.extractor import LuaExtractor, TranslationUnit
from app.rag.glossary import extract_glossary_terms


@dataclass(frozen=True, slots=True)
class TermCandidate:
    """One harvested name/label candidate."""

    unit_key: str
    source: str


@dataclass(frozen=True, slots=True)
class ModTermCandidates:
    """Aggregated term candidates for one mod source file."""

    mod_id: str
    name_candidates: list[TermCandidate]
    label_candidates: list[TermCandidate]
    styled_terms: list[str]

    def to_dict(self) -> dict:
        return {
            "mod_id": self.mod_id,
            "name_candidates": [
                {"unit_key": c.unit_key, "source": c.source} for c in self.name_candidates
            ],
            "label_candidates": [
                {"unit_key": c.unit_key, "source": c.source} for c in self.label_candidates
            ],
            "styled_terms": self.styled_terms,
        }


def scan_mod_term_candidates(
    *,
    repo: Path,
    source: str,
    mod_id: str,
    extractor: LuaExtractor | None = None,
) -> ModTermCandidates:
    """Scan a mod's source Lua and return name/label/styled term candidates.

    * ``name_candidates`` – every ``descriptions.*.*.name`` unit.
    * ``label_candidates`` – every ``misc.<section>.<key>`` unit (labels +
      dictionary, both short UI strings usable as locked terms).
    * ``styled_terms`` – de-duplicated styled-span terms pulled from
      description lines and quip lines via :func:`extract_glossary_terms`.
    """
    extractor = extractor or LuaExtractor()
    units = extractor.extract_file(repo / source)

    name_candidates: list[TermCandidate] = []
    label_candidates: list[TermCandidate] = []
    styled: list[str] = []
    seen_styled: set[str] = set()

    for unit in units:
        if unit.unit_key.endswith(".name"):
            name_candidates.append(TermCandidate(unit.unit_key, unit.source_text))
            _harvest_styled(unit, styled, seen_styled)
        elif unit.context_type in ("misc_label", "misc_dictionary"):
            label_candidates.append(TermCandidate(unit.unit_key, unit.source_text))
        elif unit.context_type == "quip_line" or unit.context_type.endswith(
            "_description_line"
        ):
            _harvest_styled(unit, styled, seen_styled)

    return ModTermCandidates(
        mod_id=mod_id,
        name_candidates=name_candidates,
        label_candidates=label_candidates,
        styled_terms=styled,
    )


def _harvest_styled(
    unit: TranslationUnit, styled: list[str], seen: set[str]
) -> None:
    for term in extract_glossary_terms(unit.source_text):
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        styled.append(term)
