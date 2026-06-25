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
    terms = extract_glossary_terms(query_text)
    if not terms:
        return refs

    with connect(db_path) as db:
        for term in terms:
            rows = db.execute(
                """
                select id, mod_id, unit_key, context_type, source_text, target_text
                from tm_entries
                where lower(source_text) = lower(?)
                   or lower(source_text) like lower(?)
                order by
                    case when lower(source_text) = lower(?) then 0 else 1 end,
                    case when quality = 'imported_human' then 0 else 1 end,
                    length(source_text)
                limit ?
                """,
                (term, f"%{term}%", term, limit_per_term),
            ).fetchall()
            for row in rows:
                tm_entry_id = int(row["id"])
                if tm_entry_id in seen_ids:
                    continue
                seen_ids.add(tm_entry_id)
                refs.append(
                    RetrievedReference(
                        tm_entry_id=tm_entry_id,
                        mod_id=row["mod_id"],
                        unit_key=row["unit_key"],
                        context_type=row["context_type"],
                        source_text=row["source_text"],
                        target_text=row["target_text"],
                        score=1.0,
                    )
                )

    return refs
