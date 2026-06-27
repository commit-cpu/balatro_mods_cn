from __future__ import annotations

import re
from pathlib import Path

from app.db.connection import connect
from app.rag.retriever import RetrievedReference


_STYLE_SPAN_RE = re.compile(r"\{[^}]*\}([^{}#]+?)\{\}")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'’-]*(?:\s+[A-Za-z][A-Za-z0-9_'’-]*)?")


def extract_glossary_terms(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for match in _STYLE_SPAN_RE.finditer(text):
        for term in _WORD_RE.findall(match.group(1)):
            normalized = term.strip()
            key = normalized.lower()
            if len(normalized) < 3 or key in seen:
                continue
            seen.add(key)
            terms.append(normalized)

    return terms


def retrieve_glossary_references(
    *,
    db_path: Path,
    query_text: str,
    limit_per_term: int = 2,
) -> list[RetrievedReference]:
    refs: list[RetrievedReference] = []
    seen_ids: set[int] = set()
    styled_terms = {term.lower() for term in extract_glossary_terms(query_text)}
    if not query_text.strip():
        return refs

    with connect(db_path) as db:
        rows = db.execute(
            """
            select id, mod_id, unit_key, context_type, source_text, target_text
            from tm_entries
            where context_type like '%_name' or context_type = 'misc_label'
            order by
                case when quality = 'imported_human' then 0 else 1 end,
                length(source_text),
                mod_id,
                id
            """
        ).fetchall()
        matches_by_term: dict[str, int] = {}
        for row in rows:
            source_text = row["source_text"]
            target_text = row["target_text"]
            if not source_text or len(source_text) < 3:
                continue
            if source_text.strip().lower() == target_text.strip().lower():
                continue
            if (
                source_text.lower() not in styled_terms
                and not _word_present(query_text, source_text)
            ):
                continue
            key = source_text.lower()
            count = matches_by_term.get(key, 0)
            if count >= limit_per_term:
                continue
            tm_entry_id = int(row["id"])
            if tm_entry_id in seen_ids:
                continue
            matches_by_term[key] = count + 1
            seen_ids.add(tm_entry_id)
            refs.append(
                RetrievedReference(
                    tm_entry_id=tm_entry_id,
                    mod_id=row["mod_id"],
                    unit_key=row["unit_key"],
                    context_type=row["context_type"],
                    source_text=source_text,
                    target_text=target_text,
                    score=1.0,
                )
            )

    return refs


def _word_present(text: str, term: str) -> bool:
    pattern = r"(?<![\w])" + re.escape(term) + r"(?![\w])"
    return re.search(pattern, text, re.IGNORECASE) is not None
