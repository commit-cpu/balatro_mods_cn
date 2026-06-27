"""Term consistency checker.

Advisory check that a translation respects locked English→Chinese term
mappings harvested from the translation memory (names + labels). Covers two
cases per ``docs/translation-quality-context-strategy.md`` Phase 1:

* **styled** – a styled span ``{C:...}Term{}`` whose ``Term`` is locked must
  reappear in the target as the locked Chinese translation.
* **exact** – a locked English term appearing as a whole word in the source
  must have its locked Chinese translation present in the target.

This is advisory only: violations surface as ``needs_review`` in the preview
JSONL, they do not block translation.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import connect
from app.rag.glossary import extract_glossary_terms


@dataclass(frozen=True, slots=True)
class TermViolation:
    """One locked-term violation found in a translation."""

    kind: str  # "styled" | "exact"
    term: str  # locked English term
    expected: str  # locked Chinese translation
    message: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "term": self.term,
            "expected": self.expected,
            "message": self.message,
        }


def build_locked_term_map(db_path: Path, mod_id: str | None = None) -> dict[str, str]:
    """Return ``{english: chinese}`` locked terms from TM name/label rows.

    Only unambiguous mappings are kept: if an English term maps to more than
    one distinct Chinese target across the selected rows, it is dropped (the
    checker cannot pick between conflicting translations). Rows are ordered by
    ``mod_id, id`` so the result is deterministic.
    """
    where = "where (context_type like '%_name' or context_type = 'misc_label')"
    params: tuple = ()
    if mod_id is not None:
        where += " and mod_id = ?"
        params = (mod_id,)
    query = (
        "select source_text, target_text from tm_entries "
        + where
        + " order by mod_id, id"
    )

    targets_by_term: dict[str, set[str]] = {}
    with connect(db_path) as db:
        try:
            rows = db.execute(query, params).fetchall()
        except sqlite3.OperationalError:
            # tm_entries not created yet (migrate not run) – no locked terms.
            return {}
        for row in rows:
            source = row["source_text"]
            target = row["target_text"]
            if not source or not target:
                continue
            targets_by_term.setdefault(source, set()).add(target)

    return {
        term: sorted(targets)[0]
        for term, targets in targets_by_term.items()
        if len(targets) == 1
    }


def check_term_consistency(
    *,
    source_text: str,
    target_text: str,
    term_map: dict[str, str],
) -> list[TermViolation]:
    """Return locked-term violations for one source/target string pair."""
    if not source_text or not target_text or not term_map:
        return []

    violations: list[TermViolation] = []
    styled_terms_found: set[str] = set()

    # --- styled spans: {C:...}Term{} ---
    for term in extract_glossary_terms(source_text):
        expected = term_map.get(term)
        if expected is None:
            continue
        styled_terms_found.add(term.lower())
        if expected not in target_text:
            violations.append(
                TermViolation(
                    kind="styled",
                    term=term,
                    expected=expected,
                    message=(
                        f"styled term {term!r} should translate to {expected!r}"
                    ),
                )
            )

    # --- exact whole-word matches ---
    for term, expected in term_map.items():
        if len(term) < 3:
            continue
        if expected.strip().lower() == term.strip().lower():
            continue  # identity mapping – TM never actually translated it
        if term.lower() in styled_terms_found:
            continue  # already handled as a styled span
        if _is_single_word(term) and source_text.strip().lower() != term.lower():
            continue
        if not _word_present(source_text, term):
            continue
        if expected not in target_text:
            violations.append(
                TermViolation(
                    kind="exact",
                    term=term,
                    expected=expected,
                    message=(
                        f"term {term!r} should translate to {expected!r}"
                    ),
                )
            )

    return violations


def check_entry_terms(
    *,
    source: dict,
    target: dict,
    term_map: dict[str, str],
) -> list[TermViolation]:
    """Run :func:`check_term_consistency` across the name/text/unlock fields
    of a preview row's ``source`` and translated ``target`` dicts."""
    violations: list[TermViolation] = []

    src_name = source.get("name")
    tgt_name = target.get("name")
    if isinstance(src_name, str) and isinstance(tgt_name, str):
        violations.extend(
            _prefix(violation, "name") for violation in check_term_consistency(
                source_text=src_name, target_text=tgt_name, term_map=term_map
            )
        )

    src_text = _join_lines(source.get("text"))
    tgt_text = _join_lines(target.get("text"))
    if src_text and tgt_text:
        violations.extend(
            _prefix(v, "text")
            for v in check_term_consistency(
                source_text=src_text, target_text=tgt_text, term_map=term_map
            )
        )

    src_unlock = _join_lines(source.get("unlock"))
    tgt_unlock = _join_lines(target.get("unlock"))
    if src_unlock and tgt_unlock:
        violations.extend(
            _prefix(v, "unlock")
            for v in check_term_consistency(
                source_text=src_unlock, target_text=tgt_unlock, term_map=term_map
            )
        )

    return violations


def _prefix(violation: TermViolation, field: str) -> TermViolation:
    return TermViolation(
        kind=violation.kind,
        term=violation.term,
        expected=violation.expected,
        message=f"[{field}] {violation.message}",
    )


def _join_lines(value) -> str:
    if not isinstance(value, list):
        return ""
    return " ".join(line for line in value if isinstance(line, str))


def _word_present(text: str, term: str) -> bool:
    pattern = r"(?<![\w])" + re.escape(term) + r"(?![\w])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _is_single_word(term: str) -> bool:
    return re.fullmatch(r"[A-Za-z][A-Za-z0-9_'-]*", term.strip()) is not None
