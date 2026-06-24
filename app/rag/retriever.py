from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.db.connection import connect
from app.lua.tokens import normalize_for_rag


@dataclass(frozen=True)
class RetrievedReference:
    tm_entry_id: int
    mod_id: str
    unit_key: str
    context_type: str
    source_text: str
    target_text: str
    score: float


@dataclass(frozen=True)
class RetrievalTrace:
    query_text: str
    normalized_query: str
    result_count: int
    hit_ids: list[int]


@dataclass(frozen=True)
class RetrievalResult:
    references: list[RetrievedReference]
    trace: RetrievalTrace


def retrieve_references(
    *,
    db_path: Path,
    query_text: str,
    embedder,
    store,
    top_k: int,
    filters: dict[str, str] | None = None,
) -> RetrievalResult:
    normalized_query = normalize_for_rag(query_text)
    query_vector = embedder.embed_texts([normalized_query])[0]
    hits = store.search(query_vector, top_k, filters=filters)
    hit_ids = [
        int(hit.payload["tm_entry_id"])
        for hit in hits
        if getattr(hit, "payload", None) and "tm_entry_id" in hit.payload
    ]
    scores = {int(hit.payload["tm_entry_id"]): float(hit.score) for hit in hits if hit.payload}

    rows_by_id = _load_tm_entries(db_path, hit_ids)
    references = [
        RetrievedReference(
            tm_entry_id=tm_entry_id,
            mod_id=rows_by_id[tm_entry_id]["mod_id"],
            unit_key=rows_by_id[tm_entry_id]["unit_key"],
            context_type=rows_by_id[tm_entry_id]["context_type"],
            source_text=rows_by_id[tm_entry_id]["source_text"],
            target_text=rows_by_id[tm_entry_id]["target_text"],
            score=scores[tm_entry_id],
        )
        for tm_entry_id in hit_ids
        if tm_entry_id in rows_by_id
    ]
    trace = RetrievalTrace(
        query_text=query_text,
        normalized_query=normalized_query,
        result_count=len(references),
        hit_ids=[ref.tm_entry_id for ref in references],
    )
    _insert_trace(db_path, trace, collection=getattr(store, "collection", ""), top_k=top_k)
    return RetrievalResult(references=references, trace=trace)


def _load_tm_entries(db_path: Path, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect(db_path) as db:
        rows = db.execute(
            f"""
            select id, mod_id, unit_key, context_type, source_text, target_text
            from tm_entries
            where id in ({placeholders})
            """,
            ids,
        ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def _insert_trace(db_path: Path, trace: RetrievalTrace, *, collection: str, top_k: int) -> None:
    with connect(db_path) as db:
        db.execute(
            """
            insert into rag_traces(
                query_text, normalized_query, collection, dense_top_k,
                result_count, trace_json
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                trace.query_text,
                trace.normalized_query,
                collection,
                top_k,
                trace.result_count,
                json.dumps(asdict(trace), ensure_ascii=False),
            ),
        )
        db.commit()
