from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.config import load_settings
from app.db.migrate import migrate as run_migrations
from app.llm.client import OpenAICompatibleClient
from app.llm.translator import TranslationReference, Translator
from app.lua.extractor import LuaExtractor
from app.lua.grouping import group_translation_units
from app.rag.ollama_embeddings import OllamaEmbeddingClient
from app.rag.glossary import retrieve_glossary_references
from app.rag.qdrant_store import QdrantTmStore
from app.rag.retriever import retrieve_references
from app.rag.tm_importer import import_locale_pair
from app.rag.vector_sync import sync_vector_outbox


app = typer.Typer(no_args_is_help=True)
console = Console()
_CREDIT_LINE_RE = re.compile(
    r"^\s*(Idea|Art|Code|Concept|Music|Sound|Credit|Credits)\s*:\s*.+$",
    re.IGNORECASE,
)


@app.command()
def migrate() -> None:
    settings = load_settings()
    run_migrations(settings.sqlite.database_path)
    console.print(f"Migrations applied: {settings.sqlite.database_path}")


@app.command("import-local-tm")
def import_local_tm(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    mod_id: str = typer.Option(...),
    source: str = typer.Option("localization/en-us.lua"),
    target: str = typer.Option("localization/zh_CN.lua"),
) -> None:
    settings = load_settings()
    result = import_locale_pair(
        db_path=Path(settings.sqlite.database_path),
        mod_id=mod_id,
        repo_path=repo,
        source_locale_path=source,
        target_locale_path=target,
        collection=settings.qdrant.collection,
    )
    console.print(
        f"Imported {result.imported_pair_count} TM entries for {result.mod_id}; "
        f"skipped {result.skipped_count}."
    )


@app.command("sync-vectors")
def sync_vectors(limit: int = typer.Option(100, min=1)) -> None:
    settings = load_settings()
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    store.ensure_collection(embedder.embedding_dimension())
    result = sync_vector_outbox(
        db_path=Path(settings.sqlite.database_path),
        embedder=embedder,
        store=store,
        batch_size=limit,
    )
    console.print(f"Synced {result.synced_count} vectors; failed {result.failed_count}.")


@app.command("qdrant-status")
def qdrant_status() -> None:
    settings = load_settings()
    store = _qdrant_store()
    info = store.collection_info()
    console.print(f"Collection: {settings.qdrant.collection}")
    console.print(info)


@app.command()
def search(query: str, top_k: int = typer.Option(5, min=1)) -> None:
    settings = load_settings()
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    result = retrieve_references(
        db_path=Path(settings.sqlite.database_path),
        query_text=query,
        embedder=embedder,
        store=store,
        top_k=top_k,
    )
    table = Table("score", "mod", "unit_key", "source", "target")
    for ref in result.references:
        table.add_row(
            f"{ref.score:.4f}",
            ref.mod_id,
            ref.unit_key,
            ref.source_text,
            ref.target_text,
        )
    console.print(table)


@app.command("rag-preview-mod")
def rag_preview_mod(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    limit: int = typer.Option(20, min=1),
    top_k: int = typer.Option(5, min=1),
) -> None:
    settings = load_settings()
    source_path = repo / source
    units = LuaExtractor().extract_file(source_path)[:limit]
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()

    console.print(f"Previewing {len(units)} units from {source_path}")
    for index, unit in enumerate(units, start=1):
        result = retrieve_references(
            db_path=Path(settings.sqlite.database_path),
            query_text=unit.source_text,
            embedder=embedder,
            store=store,
            top_k=top_k,
        )
        console.print(
            Panel(
                unit.source_text,
                title=f"{index}. {unit.unit_key}",
                expand=False,
            )
        )
        table = Table("score", "mod", "memory_unit", "source", "target")
        for ref in result.references:
            table.add_row(
                f"{ref.score:.4f}",
                ref.mod_id,
                ref.unit_key,
                ref.source_text,
                ref.target_text,
            )
        console.print(table)


@app.command("translate-preview-mod")
def translate_preview_mod(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    output: Path = typer.Option(...),
    limit: int = typer.Option(20, min=1),
    top_k: int = typer.Option(5, min=1),
) -> None:
    load_dotenv()
    settings = load_settings()
    source_path = repo / source
    units = LuaExtractor().extract_file(source_path)[:limit]
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    llm_base_url, llm_model = _llm_config()
    translator = Translator(client=_llm_client(), model=llm_model)

    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    console.print(
        "Translation preview: "
        f"repo={repo} source={source} units={len(units)} top_k={top_k} "
        f"model={llm_model} base_url={llm_base_url} output={output}"
    )
    with output.open("w", encoding="utf-8") as file:
        for index, unit in enumerate(units, start=1):
            console.print(f"[{index}/{len(units)}] {unit.unit_key}")
            retrieval = retrieve_references(
                db_path=Path(settings.sqlite.database_path),
                query_text=unit.source_text,
                embedder=embedder,
                store=store,
                top_k=top_k,
            )
            console.print(
                f"  RAG refs={len(retrieval.references)} "
                f"best_score={_best_score(retrieval.references)}"
            )
            references = _translation_references(retrieval.references)
            translated = translator.translate(
                source_text=unit.source_text,
                references=references,
            )
            console.print(f"  LLM ok token_errors={len(translated.token_errors)}")
            row = {
                "unit_key": unit.unit_key,
                "source_text": unit.source_text,
                "candidate_zh": translated.candidate_text,
                "token_errors": translated.token_errors,
                "rag_refs": _rag_ref_rows(retrieval.references),
            }
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            written += 1

    console.print(f"Wrote {written} translation preview rows to {output}")


@app.command("translate-entry-preview-mod")
def translate_entry_preview_mod(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    output: Path = typer.Option(...),
    limit: int = typer.Option(20, min=1),
    top_k: int = typer.Option(5, min=1),
    max_width: int = typer.Option(18, min=4),
    concurrency: int | None = typer.Option(None, min=1),
) -> None:
    load_dotenv()
    settings = load_settings()
    llm_concurrency = _llm_concurrency(concurrency)
    source_path = repo / source
    units = LuaExtractor().extract_file(source_path)
    entries = [
        entry
        for entry in group_translation_units(units)
        if entry.name is not None or entry.text or entry.unlock
    ][:limit]
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    llm_base_url, llm_model = _llm_config()

    output.parent.mkdir(parents=True, exist_ok=True)
    console.print(
        "Entry translation preview: "
        f"repo={repo} source={source} entries={len(entries)} top_k={top_k} "
        f"max_width={max_width} concurrency={llm_concurrency} model={llm_model} "
        f"base_url={llm_base_url} output={output}"
    )

    work_items = []
    for index, entry in enumerate(entries, start=1):
        body_text = _entry_translatable_body(entry)
        console.print(f"[{index}/{len(entries)}] {entry.entry_key}")
        dense_refs = _retrieve_entry_dense_references(
            db_path=Path(settings.sqlite.database_path),
            embedder=embedder,
            store=store,
            queries=_entry_rag_queries(entry, body_text),
            top_k=top_k,
        )
        console.print(
            f"  RAG refs={len(dense_refs)} "
            f"best_score={_best_score(dense_refs)}"
        )
        glossary_refs = retrieve_glossary_references(
            db_path=Path(settings.sqlite.database_path),
            query_text=body_text,
        )
        references = _merge_references(glossary_refs, dense_refs)
        work_items.append(
            (index, entry, references, body_text, _entry_credit_lines(entry))
        )

    written = 0
    with output.open("w", encoding="utf-8") as file:
        with ThreadPoolExecutor(max_workers=llm_concurrency) as executor:
            futures = {
                executor.submit(
                    _translate_entry_preview_row,
                    client_factory=_llm_client,
                    model=llm_model,
                    entry=entry,
                    references=references,
                    body_text=body_text,
                    credit_lines=credit_lines,
                    max_width=max_width,
                ): (index, entry, references)
                for index, entry, references, body_text, credit_lines in work_items
            }
            pending_rows: dict[int, dict[str, object]] = {}
            next_to_write = 1
            for future in as_completed(futures):
                index, entry, references = futures[future]
                try:
                    row = future.result()
                    console.print(
                        f"  LLM done [{index}/{len(entries)}] {entry.entry_key} "
                        f"token_errors={len(row['token_errors'])}"
                    )
                except Exception as exc:
                    row = _entry_error_row(entry=entry, references=references, error=exc)
                    console.print(
                        f"  LLM failed [{index}/{len(entries)}] {entry.entry_key}: {exc}"
                    )
                pending_rows[index] = row
                while next_to_write in pending_rows:
                    file.write(
                        json.dumps(pending_rows.pop(next_to_write), ensure_ascii=False)
                        + "\n"
                    )
                    file.flush()
                    written += 1
                    next_to_write += 1

    console.print(f"Wrote {written} entry translation preview rows to {output}")


def _qdrant_store() -> QdrantTmStore:
    load_dotenv()
    settings = load_settings()
    return QdrantTmStore(
        url=settings.qdrant.url,
        api_key=os.environ.get("QDRANT_API_KEY"),
        collection=settings.qdrant.collection,
        timeout=settings.qdrant.timeout_seconds,
    )


def _llm_client() -> OpenAICompatibleClient:
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise typer.BadParameter("LLM_API_KEY is required in .env or environment")
    base_url, model = _llm_config()
    return OpenAICompatibleClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


def _llm_config() -> tuple[str, str]:
    load_dotenv()
    settings = load_settings()
    base_url = os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
    model = os.environ.get("LLM_TRANSLATION_MODEL") or settings.llm.translation_model
    return base_url.rstrip("/"), model


def _llm_concurrency(override: int | None = None) -> int:
    if override is not None:
        return override
    raw = os.environ.get("LLM_CONCURRENCY")
    if not raw:
        return 1
    try:
        value = int(raw)
    except ValueError as exc:
        raise typer.BadParameter("LLM_CONCURRENCY must be an integer >= 1") from exc
    if value < 1:
        raise typer.BadParameter("LLM_CONCURRENCY must be an integer >= 1")
    return value


def _entry_rag_queries(entry, body_text: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    for unit in entry.text:
        if _is_credit_line(unit.source_text):
            continue
        _append_query(queries, seen, unit.source_text)

    _append_query(queries, seen, body_text)
    if not queries:
        _append_query(queries, seen, entry.combined_unlock)
    if not queries and entry.name is not None:
        _append_query(queries, seen, entry.name.source_text)
    if not queries:
        queries.append(entry.entry_key)

    return queries


def _append_query(queries: list[str], seen: set[str], query: str) -> None:
    normalized = " ".join(query.split())
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    queries.append(normalized)


def _retrieve_entry_dense_references(
    *,
    db_path: Path,
    embedder,
    store,
    queries: list[str],
    top_k: int,
) -> list:
    reference_groups = [
        retrieve_references(
            db_path=db_path,
            query_text=query,
            embedder=embedder,
            store=store,
            top_k=top_k,
        ).references
        for query in queries
    ]
    return _round_robin_references(reference_groups, limit=top_k)


def _round_robin_references(reference_groups: list[list], *, limit: int) -> list:
    merged = []
    seen: set[object] = set()
    max_len = max((len(group) for group in reference_groups), default=0)

    for index in range(max_len):
        for group in reference_groups:
            if index >= len(group):
                continue
            ref = group[index]
            key = _reference_key(ref)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
            if len(merged) >= limit:
                return merged
    return merged


def _translate_entry_preview_row(
    *,
    client_factory,
    model: str,
    entry,
    references,
    body_text: str,
    credit_lines: list[str],
    max_width: int,
) -> dict[str, object]:
    client = client_factory()
    try:
        translator = Translator(client=client, model=model)
        translated = translator.translate_entry(
            name_text=entry.name.source_text if entry.name is not None else None,
            body_text=body_text,
            unlock_text=entry.combined_unlock,
            references=_translation_references(references),
            max_width=max_width,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    ok = not translated.token_errors
    text = translated.text + credit_lines if ok else translated.text
    patchable, patch_warnings = _entry_patchability(
        entry=entry,
        name=translated.name,
        text=text,
        unlock=translated.unlock,
        ok=ok,
    )
    return {
        "entry_key": entry.entry_key,
        "ok": ok,
        "patchable": patchable,
        "patch_warnings": patch_warnings,
        "target_units": _entry_target_units(entry),
        "name": translated.name,
        "text": text,
        "unlock": translated.unlock,
        "token_errors": translated.token_errors,
        "source": _entry_source_row(entry),
        "rag_refs": _rag_ref_rows(references),
    }


def _entry_error_row(*, entry, references, error: Exception) -> dict[str, object]:
    return {
        "entry_key": entry.entry_key,
        "ok": False,
        "patchable": False,
        "patch_warnings": ["entry translation failed"],
        "target_units": _entry_target_units(entry),
        "name": None,
        "text": [],
        "unlock": [],
        "token_errors": [],
        "error": str(error),
        "source": _entry_source_row(entry),
        "rag_refs": _rag_ref_rows(references),
    }


def _entry_source_row(entry) -> dict[str, object]:
    return {
        "name": entry.name.source_text if entry.name is not None else None,
        "text": [unit.source_text for unit in entry.text],
        "unlock": [unit.source_text for unit in entry.unlock],
    }


def _entry_target_units(entry) -> dict[str, object]:
    return {
        "name": entry.name.unit_key if entry.name is not None else None,
        "text": [unit.unit_key for unit in entry.text],
        "unlock": [unit.unit_key for unit in entry.unlock],
    }


def _entry_patchability(
    *,
    entry,
    name: str | None,
    text: list[str],
    unlock: list[str],
    ok: bool,
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    if not ok:
        warnings.append("entry translation failed")
    if entry.name is not None and name is None:
        warnings.append("missing name translation")
    if len(text) != len(entry.text):
        warnings.append(
            f"text line count mismatch: source={len(entry.text)}, target={len(text)}"
        )
    if len(unlock) != len(entry.unlock):
        warnings.append(
            f"unlock line count mismatch: source={len(entry.unlock)}, target={len(unlock)}"
        )
    return ok and not warnings, warnings


def _entry_translatable_body(entry) -> str:
    return " ".join(
        unit.source_text for unit in entry.text if not _is_credit_line(unit.source_text)
    )


def _entry_credit_lines(entry) -> list[str]:
    return [unit.source_text for unit in entry.text if _is_credit_line(unit.source_text)]


def _is_credit_line(text: str) -> bool:
    return bool(_CREDIT_LINE_RE.match(text))


def _translation_references(references) -> list[TranslationReference]:
    return [
        TranslationReference(
            source_text=ref.source_text,
            target_text=ref.target_text,
            score=ref.score,
        )
        for ref in references
    ]


def _merge_references(glossary_refs, dense_refs) -> list:
    merged = []
    seen: set[object] = set()
    for ref in [*glossary_refs, *dense_refs]:
        key = _reference_key(ref)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged


def _reference_key(ref) -> object:
    ref_id = getattr(ref, "tm_entry_id", None)
    if ref_id is not None:
        return ("id", ref_id)
    return (
        "text",
        getattr(ref, "mod_id", ""),
        getattr(ref, "unit_key", ""),
        getattr(ref, "source_text", ""),
        getattr(ref, "target_text", ""),
    )


def _rag_ref_rows(references) -> list[dict[str, object]]:
    return [
        {
            "score": ref.score,
            "mod": ref.mod_id,
            "unit_key": ref.unit_key,
            "source": ref.source_text,
            "target": ref.target_text,
        }
        for ref in references
    ]


def _best_score(references) -> str:
    if not references:
        return "none"
    return f"{max(ref.score for ref in references):.4f}"


if __name__ == "__main__":
    app()
