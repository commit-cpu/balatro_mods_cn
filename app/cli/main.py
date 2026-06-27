from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
from app.llm.style_pack import (
    DEFAULT_STYLE_PACK_PATH,
    build_style_pack,
    load_style_pack,
    render_style_examples,
    save_style_pack,
    select_style_examples,
    select_tm_style_examples,
)
from app.lua.extractor import LuaExtractor, _context_label
from app.lua.grouping import group_translation_units
from app.lua.patcher import LuaPatcher, PatchInstruction
from app.lua.string_literals import escape_lua_string_content
from app.lua.table_writer import EntryTableTranslation, build_entry_table_patches
from app.lua.validator import validate_file
from app.rag.ollama_embeddings import OllamaEmbeddingClient
from app.rag.glossary import retrieve_glossary_references
from app.rag.mod_terms import scan_mod_term_candidates
from app.rag.qdrant_store import QdrantTmStore
from app.rag.retriever import retrieve_references
from app.rag.term_checker import build_locked_term_map, check_entry_terms
from app.rag.tm_importer import import_locale_pair
from app.rag.vector_sync import sync_vector_outbox


app = typer.Typer(no_args_is_help=True)
console = Console()
_CREDIT_LINE_RE = re.compile(
    r"^\s*(Idea|Art|Code|Concept|Music|Sound|Credit|Credits)\s*:\s*.+$",
    re.IGNORECASE,
)
_STYLED_CARD_TARGET_RE = re.compile(r"(\{[^}]*\})([^{}]*牌)(\{\})")


@dataclass(frozen=True)
class EntryWorkItem:
    index: int
    entry: object
    references: list[object]
    body_text: str
    credit_lines: list[str]
    tier_by_id: dict[int, str]
    style_examples: str


@dataclass(frozen=True)
class EntryWorkGroup:
    items: list[EntryWorkItem]


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


@app.command("scan-mod-terms")
def scan_mod_terms(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    mod_id: str = typer.Option(...),
    output: Path | None = typer.Option(None),
) -> None:
    """Harvest name/label/styled term candidates for a mod source file."""
    candidates = scan_mod_term_candidates(repo=repo, source=source, mod_id=mod_id)
    payload = json.dumps(candidates.to_dict(), ensure_ascii=False, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        console.print(
            f"Wrote {len(candidates.name_candidates)} name candidates, "
            f"{len(candidates.label_candidates)} label candidates, "
            f"{len(candidates.styled_terms)} styled terms to {output}"
        )
    else:
        console.print(payload)


@app.command("build-style-pack")
def build_style_pack_command(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option("localization/en-us.lua"),
    target: str = typer.Option("localization/zh_CN.lua"),
    output: Path = typer.Option(DEFAULT_STYLE_PACK_PATH),
    min_per_category: int = typer.Option(10, min=1),
    max_per_category: int = typer.Option(1000, min=1),
) -> None:
    """Prebuild original Balatro EN/ZH style examples for prompt use."""
    pack = build_style_pack(
        repo=repo,
        source=source,
        target=target,
        min_per_category=min_per_category,
        max_per_category=max_per_category,
    )
    save_style_pack(pack, output)
    missing = [
        key
        for key, category in sorted(pack.categories.items())
        if not category.minimum_met
    ]
    console.print(
        f"Style pack categories={len(pack.categories)} output={output} "
        f"below_minimum={len(missing)}"
    )
    if missing:
        console.print(f"Below minimum: {', '.join(missing)}")


@app.command("check-terms")
def check_terms(
    input: Path = typer.Option(..., exists=True, dir_okay=False),
    mod_id: str | None = typer.Option(None),
) -> None:
    """Audit a preview JSONL for locked-term violations without re-running the LLM."""
    settings = load_settings()
    db_path = Path(settings.sqlite.database_path)
    term_map = build_locked_term_map(db_path, mod_id=mod_id)
    console.print(
        f"Locked terms: {len(term_map)} "
        f"(mod_id filter={mod_id or 'none'})"
    )

    total_violations = 0
    flagged_entries = 0
    table = Table("entry_key", "field/kind", "term", "expected", "message")
    with input.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            source = row.get("source") or {}
            target = {
                "name": row.get("name"),
                "text": row.get("text") or [],
                "unlock": row.get("unlock") or [],
            }
            violations = check_entry_terms(
                source=source, target=target, term_map=term_map
            )
            if violations:
                flagged_entries += 1
            for v in violations:
                total_violations += 1
                table.add_row(
                    row.get("entry_key", "?"),
                    v.kind,
                    v.term,
                    v.expected,
                    v.message,
                )
    console.print(table)
    console.print(
        f"Summary: {total_violations} violations across {flagged_entries} entries"
    )


@app.command("audit-entry-output")
def audit_entry_output(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    target: Path = typer.Option(...),
    preview: Path | None = typer.Option(None, exists=True, dir_okay=False),
    json_output: Path | None = typer.Option(None, dir_okay=False),
) -> None:
    """Audit a generated Lua translation output after applying entry preview."""
    source_path = repo / source
    target_path = target if target.is_absolute() else repo / target
    rows = _read_preview_rows(preview) if preview is not None else []
    report = _audit_entry_output(source_path, target_path, rows)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = report["summary"]
    console.print(
        "Entry output audit: "
        + " ".join(f"{key}={value}" for key, value in summary.items())
    )
    _print_audit_items("Failed preview rows", report["failed_rows"], "entry_key")
    _print_audit_items("Needs-review preview rows", report["needs_review_rows"], "entry_key")
    _print_audit_items("Residual English", report["residual_english"], "unit_key")
    _print_audit_items("Untranslated units", report["untranslated_units"], "unit_key")
    _print_audit_items("Label/name mismatches", report["label_name_mismatches"], "entry_key")
    _print_audit_items("Name inconsistencies", report["name_inconsistencies"], "source")


@app.command("audit-rerun-keys")
def audit_rerun_keys(
    audit: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(...),
) -> None:
    """Write entry keys that should be retranslated from an audit JSON report."""
    report = json.loads(audit.read_text(encoding="utf-8"))
    keys = _audit_rerun_keys(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")
    console.print(f"Wrote {len(keys)} rerun entry keys to {output}")


@app.command("merge-entry-preview")
def merge_entry_preview(
    base: Path = typer.Option(..., exists=True, dir_okay=False),
    updates: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(...),
) -> None:
    """Merge updated entry preview rows into a base preview JSONL file."""
    base_rows = _read_preview_rows(base)
    update_rows = _read_preview_rows(updates)
    merged_rows, replaced, appended = _merge_preview_rows(base_rows, update_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for row in merged_rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    console.print(
        f"Merged entry preview: base={len(base_rows)} updates={len(update_rows)} "
        f"replaced={replaced} appended={appended} output={output}"
    )


@app.command("apply-entry-preview")
def apply_entry_preview(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    source: str = typer.Option(...),
    input: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(Path("localization/zh_CN.lua")),
    include_needs_review: bool = typer.Option(False),
    table_level: bool = typer.Option(False),
    validate_lua: bool = typer.Option(True),
) -> None:
    """Apply safe entry preview rows to a new Lua localization file."""
    source_path = repo / source
    output_path = output if output.is_absolute() else repo / output
    if source_path.resolve() == output_path.resolve():
        console.print("Refusing to overwrite source file; choose a different --output.")
        raise typer.Exit(1)

    source_bytes = source_path.read_bytes()
    units = LuaExtractor().extract_file(source_path)
    unit_by_key = {unit.unit_key: unit for unit in units}
    rows = _read_preview_rows(input)
    _apply_preview_consistency(rows)
    translations: dict[str, str] = {}
    table_entries: list[EntryTableTranslation] = []
    stats = {
        "total_entries": len(rows),
        "applied_entries": 0,
        "applied_unit": 0,
        "applied_table": 0,
        "applied_units": 0,
        "skipped_failed": 0,
        "skipped_needs_review": 0,
        "skipped_requires_table_level": 0,
        "skipped_blocked": 0,
        "skipped_invalid": 0,
    }

    for row in rows:
        if not row.get("ok"):
            stats["skipped_failed"] += 1
            continue
        if row.get("needs_review") and not include_needs_review:
            stats["skipped_needs_review"] += 1
            continue
        apply_mode = _row_apply_mode(row)
        if apply_mode == "table" and not table_level:
            stats["skipped_requires_table_level"] += 1
            continue
        if apply_mode == "blocked":
            stats["skipped_blocked"] += 1
            continue

        if apply_mode == "unit":
            row_translations, errors = _preview_row_translations(row)
            if errors or any(key not in unit_by_key for key in row_translations):
                stats["skipped_invalid"] += 1
                continue
            translations.update(row_translations)
            stats["applied_units"] += len(row_translations)
            stats["applied_unit"] += 1
        else:
            table_entry, errors = _preview_row_table_translation(row)
            if errors:
                stats["skipped_invalid"] += 1
                continue
            table_entries.append(table_entry)
            stats["applied_units"] += (
                (1 if table_entry.name is not None else 0)
                + len(table_entry.text)
                + len(table_entry.unlock)
            )
            stats["applied_table"] += 1
        stats["applied_entries"] += 1

    instructions = [
        PatchInstruction(
            unit_key=key,
            byte_start=unit_by_key[key].byte_start,
            byte_end=unit_by_key[key].byte_end,
            new_text=escape_lua_string_content(value),
        )
        for key, value in sorted(translations.items())
    ]
    table_instructions, table_errors = build_entry_table_patches(source_bytes, table_entries)
    if table_errors:
        console.print("Table-level patch errors: " + "; ".join(table_errors))
        raise typer.Exit(1)
    instructions.extend(table_instructions)
    patched = LuaPatcher().patch(source_bytes, instructions)
    diff_ok, diff_msg = _diff_matches_patch_instructions(
        source_bytes, patched, instructions
    )
    if not diff_ok:
        console.print(diff_msg)
        raise typer.Exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    tmp_path.write_bytes(patched)
    if validate_lua:
        valid, error = validate_file(tmp_path)
        if not valid:
            tmp_path.unlink(missing_ok=True)
            console.print(f"Lua validation failed: {error}")
            raise typer.Exit(1)
    os.replace(tmp_path, output_path)
    console.print(
        "Applied entry preview: "
        + " ".join(f"{key}={value}" for key, value in stats.items())
        + f" output={output_path}"
    )


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
    entry_keys_file: Path | None = typer.Option(None, exists=True, dir_okay=False),
    context_preview: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    load_dotenv()
    settings = load_settings()
    llm_concurrency = _llm_concurrency(concurrency)
    source_path = repo / source
    units = LuaExtractor().extract_file(source_path)
    all_entries = [
        entry
        for entry in group_translation_units(units)
        if entry.name is not None or entry.text or entry.unlock
    ]
    entry_filter = _read_entry_key_filter(entry_keys_file)
    if entry_filter is not None:
        entries = [entry for entry in all_entries if entry.entry_key in entry_filter]
    else:
        entries = all_entries[:limit]
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    llm_base_url, llm_model = _llm_config()
    db_path = Path(settings.sqlite.database_path)

    # Frozen locked-term map for the whole batch: one brief_version, one
    # glossary used by every entry's term-consistency review.
    term_map = build_locked_term_map(db_path)
    brief_version = _brief_version(term_map)
    style_pack = load_style_pack(DEFAULT_STYLE_PACK_PATH)

    output.parent.mkdir(parents=True, exist_ok=True)
    console.print(
        "Entry translation preview: "
        f"repo={repo} source={source} entries={len(entries)} top_k={top_k} "
        f"max_width={max_width} concurrency={llm_concurrency} model={llm_model} "
        f"base_url={llm_base_url} locked_terms={len(term_map)} "
        f"brief_version={brief_version} entry_filter={len(entry_filter) if entry_filter is not None else 0} "
        f"output={output}"
    )

    work_items: list[EntryWorkItem] = []
    for index, entry in enumerate(entries, start=1):
        body_text = _entry_translatable_body(entry)
        console.print(f"[{index}/{len(entries)}] {entry.entry_key}")
        dense_refs = _retrieve_entry_dense_references(
            db_path=db_path,
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
            db_path=db_path,
            query_text=_entry_glossary_query(entry, body_text),
        )
        references = _merge_references(glossary_refs, dense_refs)
        tier_by_id = _build_tier_by_id(
            glossary_refs, dense_refs, _entry_expected_context_types(entry.entry_key)
        )
        style_examples = _entry_style_examples(
            style_pack=style_pack,
            db_path=db_path,
            entry_key=entry.entry_key,
            query_text=_entry_glossary_query(entry, body_text),
            limit=8,
        )
        tier_counts = _reference_tier_counts(references, tier_by_id=tier_by_id)
        console.print(
            f"  LLM queued [{index}/{len(entries)}] {entry.entry_key} "
            f"refs locked={tier_counts['locked']} "
            f"same_context={tier_counts['same_context']} "
            f"loose={tier_counts['loose']} "
            f"style_refs={_style_reference_count(style_examples)} "
            f"credit_lines={len(_entry_credit_lines(entry))}"
        )
        work_items.append(
            EntryWorkItem(
                index=index,
                entry=entry,
                references=references,
                body_text=body_text,
                credit_lines=_entry_credit_lines(entry),
                tier_by_id=tier_by_id,
                style_examples=style_examples,
            )
        )

    context_rows = _read_preview_rows(context_preview) if context_preview is not None else []
    seeded_names = _seed_pretranslated_names(work_items, context_rows)
    pretranslated_names, name_failures = _translate_mod_entry_names(
        client_factory=_llm_client,
        model=llm_model,
        work_items=work_items,
        term_map=term_map,
        max_workers=llm_concurrency,
        seed_names=seeded_names,
    )
    name_context = _join_prompt_contexts(
        _render_mod_name_glossary(work_items, pretranslated_names),
        _render_preview_translation_context(context_rows),
    )
    console.print(
        f"Name glossary entries={len(pretranslated_names)} "
        f"failed={name_failures} seeded={len(seeded_names)} "
        f"context_rows={len(context_rows)}"
    )

    stats = _empty_preview_stats()
    work_groups = _build_entry_work_groups(work_items)
    with output.open("w", encoding="utf-8") as file:
        with ThreadPoolExecutor(max_workers=llm_concurrency) as executor:
            futures = {
                executor.submit(
                    _translate_entry_work_group,
                    client_factory=_llm_client,
                    model=llm_model,
                    max_width=max_width,
                    term_map=term_map,
                    brief_version=brief_version,
                    group=group,
                    name_context=name_context,
                    pretranslated_names=pretranslated_names,
                ): group
                for group in work_groups
            }
            rows_by_index: dict[int, dict[str, object]] = {}
            for future in as_completed(futures):
                group = futures[future]
                group_rows, group_logs = future.result()
                for log_kind, item, row, exc in group_logs:
                    if log_kind == "done":
                        console.print(
                            f"  LLM done [{item.index}/{len(entries)}] "
                            f"{item.entry.entry_key} "
                            f"token_errors={len(row['token_errors'])} "
                            f"needs_review={row['needs_review']} "
                            f"apply_mode={row.get('apply_mode')} "
                            f"{_preview_review_log(row)}"
                        )
                    else:
                        console.print(
                            f"  LLM failed [{item.index}/{len(entries)}] "
                            f"{item.entry.entry_key}: {exc}"
                        )
                rows_by_index.update(group_rows)
                missing_indexes = [
                    item.index for item in group.items if item.index not in group_rows
                ]
                if missing_indexes:
                    raise RuntimeError(
                        f"translation group returned no rows for indexes {missing_indexes}"
                    )

        ordered_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
        _apply_preview_consistency(ordered_rows)
        for row in ordered_rows:
            _update_preview_stats(stats, row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()

    console.print(f"Wrote {len(ordered_rows)} entry translation preview rows to {output}")
    console.print(_preview_summary_log(stats))


def _read_preview_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _read_entry_key_filter(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        key = line.strip()
        if not key or key.startswith("#"):
            continue
        keys.add(key)
    return keys


def _merge_preview_rows(
    base_rows: list[dict[str, object]],
    update_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int, int]:
    updates_by_key: dict[str, dict[str, object]] = {}
    update_order: list[str] = []
    for row in update_rows:
        key = row.get("entry_key")
        if not isinstance(key, str):
            continue
        if key not in updates_by_key:
            update_order.append(key)
        updates_by_key[key] = row

    replaced = 0
    seen: set[str] = set()
    merged: list[dict[str, object]] = []
    for row in base_rows:
        key = row.get("entry_key")
        if isinstance(key, str) and key in updates_by_key:
            merged.append(updates_by_key[key])
            seen.add(key)
            replaced += 1
        else:
            merged.append(row)

    appended = 0
    for key in update_order:
        if key in seen:
            continue
        merged.append(updates_by_key[key])
        appended += 1
    return merged, replaced, appended


def _audit_rerun_keys(report: dict[str, object]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        if not isinstance(value, str) or not value:
            return
        if value in seen:
            return
        seen.add(value)
        keys.append(value)

    for section in ("failed_rows", "needs_review_rows"):
        for item in _dict_items(report.get(section)):
            add(item.get("entry_key"))

    for section in ("residual_english", "untranslated_units"):
        for item in _dict_items(report.get(section)):
            if item.get("severity") == "review":
                continue
            add(_entry_key_from_unit_key(item.get("unit_key")))

    for item in _dict_items(report.get("label_name_mismatches")):
        add(item.get("description_entry_key"))
        add(item.get("label_unit_key"))

    for item in _dict_items(report.get("name_inconsistencies")):
        entry_keys = item.get("entry_keys")
        if isinstance(entry_keys, list):
            for key in entry_keys:
                add(key)

    return keys


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _entry_key_from_unit_key(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("descriptions."):
        match = re.match(r"^(descriptions\.[^.]+\.[^.]+)(?:\.(?:name|text|unlock)(?:\[\d+\])?)?$", value)
        if match:
            return match.group(1)
    misc_match = re.match(r"^(misc\.[^.]+\.[^\[]+)(?:\[\d+\])?$", value)
    if misc_match:
        return misc_match.group(1)
    return value


def _audit_entry_output(
    source_path: Path,
    target_path: Path,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    lua_valid, lua_error = validate_file(target_path)
    source_units = LuaExtractor().extract_file(source_path)
    target_units = LuaExtractor().extract_file(target_path)
    source_by_key = {unit.unit_key: unit.source_text for unit in source_units}
    target_by_key = {unit.unit_key: unit.source_text for unit in target_units}

    failed_rows = [
        {
            "entry_key": str(row.get("entry_key", "?")),
            "error": str(row.get("error") or row.get("message") or ""),
        }
        for row in rows
        if not row.get("ok")
    ]
    needs_review_rows = [
        {
            "entry_key": str(row.get("entry_key", "?")),
            "apply_mode": _row_apply_mode(row),
        }
        for row in rows
        if row.get("ok") and row.get("needs_review")
    ]

    residual_english = _residual_english_items(target_units)
    untranslated_units = _untranslated_unit_items(source_by_key, target_by_key)
    label_name_mismatches = _label_name_mismatches(target_units)
    name_inconsistencies = _name_inconsistencies(source_by_key, target_by_key)

    summary = {
        "lua_valid": int(lua_valid),
        "preview_rows": len(rows),
        "failed": len(failed_rows),
        "needs_review": len(needs_review_rows),
        "source_units": len(source_units),
        "target_units": len(target_units),
        "residual_english": len(residual_english),
        "untranslated": len(untranslated_units),
        "label_name_mismatches": len(label_name_mismatches),
        "name_inconsistencies": len(name_inconsistencies),
    }
    return {
        "summary": summary,
        "lua_error": lua_error,
        "failed_rows": failed_rows,
        "needs_review_rows": needs_review_rows,
        "residual_english": residual_english,
        "untranslated_units": untranslated_units,
        "label_name_mismatches": label_name_mismatches,
        "name_inconsistencies": name_inconsistencies,
    }


def _residual_english_items(units: list) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for unit in units:
        severity = _residual_english_severity_for_unit(unit.unit_key, unit.source_text)
        if severity is None:
            continue
        items.append(
            {
                "unit_key": unit.unit_key,
                "text": unit.source_text,
                "severity": severity,
            }
        )
    return items


def _residual_english_severity_for_unit(unit_key: str, text: str) -> str | None:
    severity = _residual_english_severity(text)
    if (
        severity == "rerun"
        and unit_key.endswith(".name")
        and _looks_like_acronym_text(text)
    ):
        return "review"
    return severity


def _untranslated_unit_items(
    source_by_key: dict[str, str],
    target_by_key: dict[str, str],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, target_text in sorted(target_by_key.items()):
        if source_by_key.get(key) != target_text:
            continue
        severity = _untranslated_unit_severity(key, target_text)
        if severity is None:
            continue
        items.append({"unit_key": key, "text": target_text, "severity": severity})
    return items


def _untranslated_unit_severity(unit_key: str, text: str) -> str | None:
    if _residual_english_severity(text) is None:
        return None
    if unit_key.endswith(".name") and _looks_like_acronym_text(text):
        return "review"
    return "rerun"


def _has_residual_english(text: str) -> bool:
    return _residual_english_severity(text) is not None


def _residual_english_severity(text: str) -> str | None:
    stripped = re.sub(r"\{[^{}]*\}", " ", text)
    stripped = re.sub(r"#\d+#", " ", stripped)
    stripped = re.sub(r"\bX(?=\d|\s*$)", " ", stripped)
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.?'-]{2,}", stripped)
    if not words:
        return None
    if not re.search(r"[\u3400-\u9fff]", stripped):
        return "rerun"
    if any(_is_gameplay_english_word(word) for word in words):
        return "rerun"
    if all(_looks_like_proper_english_fragment(word) for word in words):
        return "review"
    return "rerun"


def _is_gameplay_english_word(word: str) -> bool:
    normalized = word.strip(".,!?;:()[]{}'\"").casefold()
    return normalized in {
        "add",
        "adds",
        "after",
        "and",
        "becomes",
        "card",
        "cards",
        "chip",
        "chips",
        "creates",
        "discard",
        "edition",
        "every",
        "gain",
        "gains",
        "hand",
        "held",
        "level",
        "mult",
        "played",
        "rank",
        "round",
        "score",
        "selected",
        "until",
        "use",
        "uses",
        "when",
    }


def _looks_like_proper_english_fragment(word: str) -> bool:
    cleaned = word.strip(".,!?;:()[]{}'\"")
    if not cleaned:
        return False
    letters = re.sub(r"[^A-Za-z]", "", cleaned)
    if len(letters) >= 2 and letters.upper() == letters:
        return True
    return cleaned[0].isupper() and cleaned[1:].lower() == cleaned[1:]


def _looks_like_acronym_text(text: str) -> bool:
    stripped = re.sub(r"\{[^{}]*\}", " ", text)
    stripped = re.sub(r"#\d+#", " ", stripped).strip()
    if not stripped:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.?'-]*", stripped)
    if not words:
        return False
    non_words = re.sub(r"[A-Za-z0-9_.?'\-\s]", "", stripped)
    if non_words:
        return False
    return all(_looks_like_acronym_word(word) for word in words)


def _looks_like_acronym_word(word: str) -> bool:
    cleaned = word.strip(".,!?;:()[]{}'\"")
    letters = re.sub(r"[^A-Za-z]", "", cleaned)
    return len(letters) >= 2 and letters.upper() == letters


def _label_name_mismatches(units: list) -> list[dict[str, str]]:
    names: dict[str, tuple[str, str]] = {}
    labels: dict[str, tuple[str, str]] = {}
    for unit in units:
        match = re.match(r"^descriptions\.[^.]+\.([^.]+)\.name$", unit.unit_key)
        if match:
            entry_key = unit.unit_key.removesuffix(".name")
            names[match.group(1)] = (entry_key, unit.source_text)
            continue
        match = re.match(r"^misc\.labels\.([^.]+)$", unit.unit_key)
        if match:
            labels[match.group(1)] = (unit.unit_key, unit.source_text)

    mismatches: list[dict[str, str]] = []
    for key in sorted(set(names) & set(labels)):
        description_entry_key, description_name = names[key]
        label_unit_key, label = labels[key]
        if description_name != label:
            mismatches.append(
                {
                    "entry_key": key,
                    "description_entry_key": description_entry_key,
                    "label_unit_key": label_unit_key,
                    "description_name": description_name,
                    "label": label,
                }
            )
    return mismatches


def _name_inconsistencies(
    source_by_key: dict[str, str],
    target_by_key: dict[str, str],
) -> list[dict[str, object]]:
    by_source: dict[str, set[str]] = {}
    keys_by_source: dict[str, set[str]] = {}
    display_source: dict[str, str] = {}
    for key, source_text in source_by_key.items():
        if not _is_name_like_unit(key):
            continue
        target_text = target_by_key.get(key)
        if target_text is None:
            continue
        norm = _normalize_audit_term(source_text)
        if not norm:
            continue
        display_source.setdefault(norm, source_text)
        by_source.setdefault(norm, set()).add(target_text)
        keys_by_source.setdefault(norm, set()).add(_entry_key_from_unit_key(key) or key)

    result: list[dict[str, object]] = []
    for norm, targets in sorted(by_source.items()):
        if len(targets) > 1:
            result.append(
                {
                    "source": display_source[norm],
                    "targets": sorted(targets),
                    "entry_keys": sorted(keys_by_source.get(norm, set())),
                }
            )
    return result


def _is_name_like_unit(unit_key: str) -> bool:
    return unit_key.endswith(".name") or unit_key.startswith("misc.labels.")


def _normalize_audit_term(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _print_audit_items(title: str, items: object, key_field: str) -> None:
    if not isinstance(items, list) or not items:
        return
    preview_items = []
    for item in items[:10]:
        if isinstance(item, dict):
            preview_items.append(str(item.get(key_field, "?")))
    console.print(f"{title}: {len(items)} ({', '.join(preview_items)})")


def _diff_matches_patch_instructions(
    original: bytes,
    patched: bytes,
    instructions: list[PatchInstruction],
) -> tuple[bool, str]:
    orig_pos = 0
    patched_pos = 0
    for instruction in sorted(instructions, key=lambda item: item.byte_start):
        unchanged_len = instruction.byte_start - orig_pos
        if unchanged_len < 0:
            return False, f"overlapping patch instruction: {instruction.unit_key}"
        original_chunk = original[orig_pos:instruction.byte_start]
        patched_chunk = patched[patched_pos : patched_pos + unchanged_len]
        if original_chunk != patched_chunk:
            return False, f"unexpected byte change before {instruction.unit_key}"
        patched_pos += unchanged_len + len(instruction.new_text.encode("utf-8"))
        orig_pos = instruction.byte_end

    if original[orig_pos:] != patched[patched_pos:]:
        return False, "unexpected trailing byte change"
    return True, ""


def _preview_row_translations(
    row: dict[str, object],
) -> tuple[dict[str, str], list[str]]:
    target_units = row.get("target_units")
    if not isinstance(target_units, dict):
        return {}, ["missing target_units"]

    translations: dict[str, str] = {}
    errors: list[str] = []
    name_key = target_units.get("name")
    name_value = row.get("name")
    if isinstance(name_key, str):
        if isinstance(name_value, str):
            translations[name_key] = name_value
        else:
            errors.append("missing name translation")

    _extend_indexed_translations(
        translations=translations,
        errors=errors,
        unit_keys=target_units.get("text"),
        values=row.get("text"),
        field="text",
    )
    _extend_indexed_translations(
        translations=translations,
        errors=errors,
        unit_keys=target_units.get("unlock"),
        values=row.get("unlock"),
        field="unlock",
    )
    return translations, errors


def _table_level_can_apply(row: dict[str, object]) -> bool:
    warnings = row.get("patch_warnings") or []
    if isinstance(warnings, list) and warnings:
        return all(
            isinstance(warning, str)
            and _is_table_level_apply_warning(warning)
            for warning in warnings
        )
    return _row_has_line_count_delta(row)


def _row_apply_mode(row: dict[str, object]) -> str:
    if row.get("patchable") is True:
        return "unit"
    mode = row.get("apply_mode")
    if mode in {"unit", "table", "blocked"}:
        return str(mode)
    if _table_level_can_apply(row):
        return "table"
    return "blocked"


def _is_table_level_apply_warning(warning: str) -> bool:
    return warning.startswith("text line count mismatch:") or warning.startswith(
        "unlock line count mismatch:"
    )


def _row_has_line_count_delta(row: dict[str, object]) -> bool:
    target_units = row.get("target_units")
    if not isinstance(target_units, dict):
        return False
    return any(
        _list_len(row.get(field)) != _list_len(target_units.get(field))
        for field in ("text", "unlock")
    )


def _preview_row_table_translation(
    row: dict[str, object],
) -> tuple[EntryTableTranslation, list[str]]:
    errors: list[str] = []
    entry_key = row.get("entry_key")
    if not isinstance(entry_key, str):
        errors.append("missing entry_key")
        entry_key = ""
    name_value = row.get("name")
    name = name_value if isinstance(name_value, str) else None
    text = _string_list_or_error(row.get("text"), "text", errors)
    unlock = _string_list_or_error(row.get("unlock"), "unlock", errors)
    return EntryTableTranslation(entry_key=entry_key, name=name, text=text, unlock=unlock), errors


def _string_list_or_error(value: object, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"invalid {field}")
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            errors.append(f"invalid {field} item")
            return []
        result.append(item)
    return result


def _extend_indexed_translations(
    *,
    translations: dict[str, str],
    errors: list[str],
    unit_keys: object,
    values: object,
    field: str,
) -> None:
    if unit_keys is None:
        return
    if not isinstance(unit_keys, list) or not isinstance(values, list):
        errors.append(f"invalid {field} translations")
        return
    if len(unit_keys) != len(values):
        errors.append(
            f"{field} line count mismatch: units={len(unit_keys)}, values={len(values)}"
        )
        return
    for key, value in zip(unit_keys, values, strict=True):
        if not isinstance(key, str) or not isinstance(value, str):
            errors.append(f"invalid {field} item")
            return
        translations[key] = value


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


def _entry_glossary_query(entry, body_text: str) -> str:
    parts = []
    if entry.name is not None:
        parts.append(entry.name.source_text)
    if body_text:
        parts.append(body_text)
    if entry.combined_unlock:
        parts.append(entry.combined_unlock)
    return " ".join(parts)


def _entry_style_examples(
    *,
    style_pack,
    db_path: Path,
    entry_key: str,
    query_text: str,
    limit: int,
) -> str:
    examples = []
    examples.extend(
        select_style_examples(
            style_pack,
            entry_key=entry_key,
            query_text=query_text,
            limit=limit,
            allow_fallback=False,
        )
    )
    if len(examples) < limit:
        examples.extend(
            select_tm_style_examples(
                db_path,
                entry_key=entry_key,
                query_text=query_text,
                limit=limit - len(examples),
            )
        )
    if len(examples) < limit:
        examples.extend(
            select_style_examples(
                style_pack,
                entry_key=entry_key,
                query_text=query_text,
                limit=limit - len(examples),
                allow_fallback=True,
            )
        )
    return render_style_examples(_dedupe_style_examples(examples)[:limit])


def _dedupe_style_examples(examples) -> list:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for example in examples:
        key = (getattr(example, "source_mod_id", ""), example.unit_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(example)
    return deduped


def _style_reference_count(style_examples: str) -> int:
    return sum(1 for line in style_examples.splitlines() if line.startswith("- "))


def _reference_tier_counts(
    references, *, tier_by_id: dict[int, str] | None = None
) -> dict[str, int]:
    counts = {"locked": 0, "same_context": 0, "loose": 0}
    for ref in references:
        tier = "loose"
        ref_id = getattr(ref, "tm_entry_id", None)
        if tier_by_id is not None and ref_id in tier_by_id:
            tier = tier_by_id[ref_id]
        if tier not in counts:
            tier = "loose"
        counts[tier] += 1
    return counts


def _preview_review_log(row: dict[str, object]) -> str:
    review = row.get("review")
    if not isinstance(review, dict):
        review = {}
    term_violations = _list_len(review.get("term_violations"))
    naturalness = _list_len(review.get("naturalness_warnings"))
    meaning = _list_len(review.get("meaning_warnings"))
    retry_history = review.get("retry_history")
    quality_retries = _list_len(retry_history)
    retry_token_errors = 0
    if isinstance(retry_history, list):
        retry_token_errors = sum(
            1
            for item in retry_history
            if isinstance(item, dict) and item.get("retry_token_errors")
        )
    return (
        f"term_violations={term_violations} "
        f"review_warnings={naturalness + meaning} "
        f"quality_retries={quality_retries} "
        f"retry_token_error={retry_token_errors > 0}"
    )


def _empty_preview_stats() -> dict[str, int]:
    return {
        "ok": 0,
        "failed": 0,
        "token_error_entries": 0,
        "needs_review": 0,
        "term_violation_entries": 0,
        "quality_retry_entries": 0,
        "retry_token_error_entries": 0,
        "apply_unit": 0,
        "apply_table": 0,
        "apply_blocked": 0,
    }


def _update_preview_stats(stats: dict[str, int], row: dict[str, object]) -> None:
    if row.get("ok") is True:
        stats["ok"] += 1
    if row.get("error"):
        stats["failed"] += 1
    if row.get("token_errors"):
        stats["token_error_entries"] += 1
    if row.get("needs_review") is True:
        stats["needs_review"] += 1
    apply_mode = _row_apply_mode(row)
    if apply_mode == "unit":
        stats["apply_unit"] += 1
    elif apply_mode == "table":
        stats["apply_table"] += 1
    else:
        stats["apply_blocked"] += 1

    review = row.get("review")
    if not isinstance(review, dict):
        return
    if review.get("term_violations"):
        stats["term_violation_entries"] += 1
    retry_history = review.get("retry_history")
    if isinstance(retry_history, list) and retry_history:
        stats["quality_retry_entries"] += 1
        if any(
            isinstance(item, dict) and item.get("retry_token_errors")
            for item in retry_history
        ):
            stats["retry_token_error_entries"] += 1


def _preview_summary_log(stats: dict[str, int]) -> str:
    return (
        "Preview summary: "
        f"ok={stats['ok']} "
        f"failed={stats['failed']} "
        f"token_error_entries={stats['token_error_entries']} "
        f"needs_review={stats['needs_review']} "
        f"term_violation_entries={stats['term_violation_entries']} "
        f"quality_retry_entries={stats['quality_retry_entries']} "
        f"retry_token_error_entries={stats['retry_token_error_entries']} "
        f"apply_unit={stats['apply_unit']} "
        f"apply_table={stats['apply_table']} "
        f"apply_blocked={stats['apply_blocked']}"
    )


def _list_len(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


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


def _build_entry_work_groups(work_items: list[EntryWorkItem]) -> list[EntryWorkGroup]:
    by_key = {item.entry.entry_key: item for item in work_items}
    adjacency: dict[str, set[str]] = {item.entry.entry_key: set() for item in work_items}
    referenced_name_entries: set[str] = set()
    name_terms = _entry_source_name_terms(work_items)

    for item in work_items:
        haystack = _entry_glossary_query(item.entry, item.body_text)
        for source_name, owner_key in name_terms:
            if owner_key == item.entry.entry_key:
                continue
            if not _source_name_referenced(haystack, source_name):
                continue
            adjacency[item.entry.entry_key].add(owner_key)
            adjacency[owner_key].add(item.entry.entry_key)
            referenced_name_entries.add(owner_key)

    groups: list[EntryWorkGroup] = []
    seen: set[str] = set()
    for item in work_items:
        entry_key = item.entry.entry_key
        if entry_key in seen:
            continue
        component: list[str] = []
        stack = [entry_key]
        seen.add(entry_key)
        while stack:
            key = stack.pop()
            component.append(key)
            for neighbor in sorted(adjacency[key]):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                stack.append(neighbor)
        items = [by_key[key] for key in component]
        items.sort(
            key=lambda group_item: (
                0 if group_item.entry.entry_key in referenced_name_entries else 1,
                group_item.index,
            )
        )
        groups.append(EntryWorkGroup(items=items))

    groups.sort(key=lambda group: min(item.index for item in group.items))
    return groups


def _translate_mod_entry_names(
    *,
    client_factory,
    model: str,
    work_items: list[EntryWorkItem],
    term_map: dict[str, str],
    max_workers: int,
    seed_names: dict[str, str] | None = None,
) -> tuple[dict[str, str], int]:
    seed_names = seed_names or {}
    name_items = [
        item
        for item in work_items
        if item.entry.name is not None
        and _is_specific_source_name(item.entry.name.source_text)
        and item.entry.entry_key not in seed_names
    ]
    if not name_items:
        return dict(seed_names), 0

    def translate_name(item: EntryWorkItem) -> tuple[str, str | None]:
        client = client_factory()
        try:
            translator = Translator(client=client, model=model)
            translate_method = getattr(translator, "translate", None)
            if not callable(translate_method):
                return item.entry.entry_key, None
            translation_refs = _name_translation_references(item, term_map=term_map)
            translated = translate_method(
                source_text=item.entry.name.source_text,
                references=translation_refs,
            )
            candidate = getattr(translated, "candidate_text", None)
            token_errors = getattr(translated, "token_errors", [])
            if token_errors or not isinstance(candidate, str) or not candidate.strip():
                return item.entry.entry_key, None
            return item.entry.entry_key, candidate.strip()
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    names: dict[str, str] = dict(seed_names)
    failures = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(translate_name, item) for item in name_items]
        for future in as_completed(futures):
            try:
                entry_key, target_name = future.result()
            except Exception:
                failures += 1
                continue
            if target_name is None:
                failures += 1
                continue
            names[entry_key] = target_name
    return names, failures


def _name_translation_references(
    item: EntryWorkItem,
    *,
    term_map: dict[str, str],
) -> list[TranslationReference]:
    source_name = item.entry.name.source_text if item.entry.name is not None else ""
    pattern_refs = _name_pattern_references(source_name, term_map=term_map)
    raw_refs = [
        ref
        for ref in item.references
        if _name_prepass_allows_reference(source_name, ref)
    ]
    retrieval_refs = _translation_references(raw_refs, tier_by_id=item.tier_by_id)
    return _dedupe_translation_references(pattern_refs + retrieval_refs)


def _name_prepass_allows_reference(source_name: str, ref: object) -> bool:
    ref_source = getattr(ref, "source_text", "")
    if not isinstance(ref_source, str) or not ref_source.strip():
        return False
    if ref_source.casefold() == source_name.casefold():
        return True

    source_words = source_name.split()
    ref_words = ref_source.split()
    if len(source_words) > 1 and len(ref_words) == 1:
        ref_mod = getattr(ref, "mod_id", "")
        if ref_mod != "balatro_origin" and _source_name_referenced(
            source_name, ref_source
        ):
            return False
    return True


def _name_pattern_references(
    source_name: str,
    *,
    term_map: dict[str, str],
) -> list[TranslationReference]:
    words = source_name.split()
    if len(words) < 2:
        return []

    suffix = words[-1]
    suffix_pattern = f" {suffix.casefold()}"
    candidates = [
        (term, target)
        for term, target in term_map.items()
        if term.casefold().endswith(suffix_pattern)
        and term.casefold() != source_name.casefold()
        and target
    ]
    if len(candidates) < 2:
        return []

    target_suffix = _common_nonempty_suffix([target for _, target in candidates])
    target_suffix = _normalize_name_pattern_suffix(target_suffix)
    refs: list[TranslationReference] = []
    if len(target_suffix) >= 2:
        refs.append(
            TranslationReference(
                source_text=suffix,
                target_text=target_suffix,
                score=1.0,
                tier="locked",
            )
        )
    for term, target in sorted(candidates, key=lambda item: item[0])[:8]:
        refs.append(
            TranslationReference(
                source_text=term,
                target_text=target,
                score=1.0,
                tier="same_context",
            )
        )
    return refs


def _common_nonempty_suffix(values: list[str]) -> str:
    if not values:
        return ""
    shortest = min(values, key=len)
    for index in range(len(shortest)):
        candidate = shortest[index:]
        if all(value.endswith(candidate) for value in values):
            return candidate
    return ""


def _normalize_name_pattern_suffix(suffix: str) -> str:
    for canonical in ("蜡封", "牌组", "牌套"):
        if suffix.endswith(canonical):
            return canonical
    return suffix


def _dedupe_translation_references(
    references: list[TranslationReference],
) -> list[TranslationReference]:
    seen: set[tuple[str, str]] = set()
    deduped: list[TranslationReference] = []
    for ref in references:
        key = (ref.source_text, ref.target_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _render_mod_name_glossary(
    work_items: list[EntryWorkItem],
    pretranslated_names: dict[str, str],
) -> str:
    lines = [
        "Mod-wide translated name glossary:",
        "Use these name translations consistently across this mod.",
    ]
    for item in work_items:
        source_name = (
            item.entry.name.source_text
            if item.entry.name is not None
            else None
        )
        target_name = pretranslated_names.get(item.entry.entry_key)
        if not isinstance(source_name, str) or not isinstance(target_name, str):
            continue
        if source_name == target_name:
            continue
        lines.append(f"- {source_name} -> {target_name} ({item.entry.entry_key})")
        lines.append(f"  If source says {source_name} Card, use {target_name}牌.")
    return "\n".join(lines) if len(lines) > 2 else ""


def _seed_pretranslated_names(
    work_items: list[EntryWorkItem],
    context_rows: list[dict[str, object]],
) -> dict[str, str]:
    if not context_rows:
        return {}
    by_source = _accepted_preview_name_targets(context_rows)
    seeds: dict[str, str] = {}
    for item in work_items:
        name_unit = getattr(item.entry, "name", None)
        source_name = getattr(name_unit, "source_text", None)
        if not isinstance(source_name, str):
            continue
        targets = by_source.get(_normalize_audit_term(source_name))
        if targets is None or len(targets) != 1:
            continue
        seeds[item.entry.entry_key] = next(iter(targets))
    return seeds


def _accepted_preview_name_targets(
    rows: list[dict[str, object]],
) -> dict[str, set[str]]:
    by_source: dict[str, set[str]] = {}
    for row in rows:
        if row.get("ok") is not True or row.get("needs_review") is True:
            continue
        source = row.get("source")
        target_name = row.get("name")
        if not isinstance(source, dict) or not isinstance(target_name, str):
            continue
        source_name = source.get("name")
        if not isinstance(source_name, str) or not source_name.strip():
            continue
        if source_name == target_name:
            continue
        by_source.setdefault(_normalize_audit_term(source_name), set()).add(target_name)
    return by_source


def _entry_source_name_terms(work_items: list[EntryWorkItem]) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    for item in work_items:
        name_unit = getattr(item.entry, "name", None)
        source_name = getattr(name_unit, "source_text", None)
        if not isinstance(source_name, str) or not _is_specific_source_name(source_name):
            continue
        terms.append((source_name, item.entry.entry_key))
    return sorted(terms, key=lambda item: len(item[0]), reverse=True)


def _is_specific_source_name(source_name: str) -> bool:
    normalized = source_name.strip().casefold()
    if len(normalized) < 4:
        return False
    return normalized not in {
        "card",
        "cards",
        "the",
        "locked",
        "sample",
        "static",
    }


def _source_name_referenced(haystack: str, source_name: str) -> bool:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(source_name)}(?:\s+Card)?(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    return bool(pattern.search(haystack))


def _translate_entry_work_group(
    *,
    client_factory,
    model: str,
    max_width: int,
    term_map: dict[str, str],
    brief_version: str,
    group: EntryWorkGroup,
    name_context: str = "",
    pretranslated_names: dict[str, str] | None = None,
) -> tuple[
    dict[int, dict[str, object]],
    list[tuple[str, EntryWorkItem, dict[str, object], Exception | None]],
]:
    rows: dict[int, dict[str, object]] = {}
    logs: list[tuple[str, EntryWorkItem, dict[str, object], Exception | None]] = []
    prior_rows: list[dict[str, object]] = []
    pretranslated_names = pretranslated_names or {}

    for item in group.items:
        group_context = _render_group_translation_context(prior_rows)
        try:
            row = _translate_entry_preview_row(
                client_factory=client_factory,
                model=model,
                entry=item.entry,
                references=item.references,
                body_text=item.body_text,
                credit_lines=item.credit_lines,
                max_width=max_width,
                tier_by_id=item.tier_by_id,
                term_map=term_map,
                brief_version=brief_version,
                style_examples=_append_translation_contexts(
                    item.style_examples,
                    name_context,
                    group_context,
                ),
                pretranslated_name=pretranslated_names.get(item.entry.entry_key),
            )
            logs.append(("done", item, row, None))
        except Exception as exc:
            row = _entry_error_row(
                entry=item.entry,
                references=item.references,
                error=exc,
                tier_by_id=item.tier_by_id,
                brief_version=brief_version,
            )
            logs.append(("failed", item, row, exc))
        rows[item.index] = row
        if row.get("ok") is True:
            prior_rows.append(row)
    return rows, logs


def _append_translation_contexts(style_examples: str, *contexts: str) -> str:
    extra_contexts = [context for context in contexts if context]
    if not extra_contexts:
        return style_examples
    context = "\n\n".join(extra_contexts)
    if not style_examples or style_examples == "(none)":
        return context
    return f"{style_examples}\n\n{context}"


def _join_prompt_contexts(*contexts: str) -> str:
    return "\n\n".join(context for context in contexts if context)


def _render_preview_translation_context(rows: list[dict[str, object]]) -> str:
    accepted_rows = [
        row
        for row in rows
        if row.get("ok") is True and row.get("needs_review") is not True
    ]
    if not accepted_rows:
        return ""
    lines = [
        "Mod-local accepted translations from previous preview:",
        "Use these translations consistently for names, labels, and derived terms.",
    ]
    for row in accepted_rows:
        source = row.get("source")
        if not isinstance(source, dict):
            continue
        entry_key = row.get("entry_key")
        source_name = source.get("name")
        target_name = row.get("name")
        if isinstance(source_name, str) and isinstance(target_name, str):
            lines.append(f"- {source_name} -> {target_name} ({entry_key})")
            lines.append(f"  If source says {source_name} Card, use {target_name}牌.")
        source_text = " ".join(_source_field_strings(source.get("text")))
        target_text = " ".join(_source_field_strings(row.get("text")))
        if source_text and target_text:
            lines.append(f"  EN text: {source_text}")
            lines.append(f"  ZH text: {target_text}")
    return "\n".join(lines) if len(lines) > 2 else ""


def _render_group_translation_context(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    lines = [
        "Mod-local related entries already translated in this group:",
        "Use these translations consistently for names and derived card terms.",
    ]
    for row in rows:
        source = row.get("source")
        if not isinstance(source, dict):
            continue
        source_name = source.get("name")
        target_name = row.get("name")
        entry_key = row.get("entry_key")
        if isinstance(source_name, str) and isinstance(target_name, str):
            lines.append(f"- {source_name} -> {target_name} ({entry_key})")
            lines.append(f"  If source says {source_name} Card, use {target_name}牌.")
        source_text = " ".join(_source_field_strings(source.get("text")))
        target_text = " ".join(_source_field_strings(row.get("text")))
        if source_text and target_text:
            lines.append(f"  EN text: {source_text}")
            lines.append(f"  ZH text: {target_text}")
    return "\n".join(lines)


def _translate_entry_preview_row(
    *,
    client_factory,
    model: str,
    entry,
    references,
    body_text: str,
    credit_lines: list[str],
    max_width: int,
    tier_by_id: dict[int, str] | None = None,
    term_map: dict[str, str] | None = None,
    brief_version: str = "",
    style_examples: str = "",
    pretranslated_name: str | None = None,
) -> dict[str, object]:
    if _entry_is_name_only(entry) and pretranslated_name is not None:
        return _entry_name_only_preview_row(
            entry=entry,
            name=pretranslated_name,
            references=references,
            tier_by_id=tier_by_id,
            term_map=term_map or {},
            brief_version=brief_version,
        )

    client = client_factory()
    try:
        translator = Translator(client=client, model=model)
        translation_refs = _translation_references(references, tier_by_id=tier_by_id)
        translated = translator.translate_entry(
            name_text=entry.name.source_text if entry.name is not None else None,
            body_text=body_text,
            unlock_text=entry.combined_unlock,
            references=translation_refs,
            max_width=max_width,
            style_examples=style_examples,
        )
        translated, quality_review, retry_history = _maybe_retry_entry_translation(
            translator=translator,
            entry=entry,
            translated=translated,
            pretranslated_name=pretranslated_name,
            body_text=body_text,
            max_width=max_width,
            references=translation_refs,
            style_examples=style_examples,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    ok = not translated.token_errors
    text = translated.text + credit_lines if ok else translated.text
    name = pretranslated_name if pretranslated_name is not None else translated.name
    patchable, patch_warnings = _entry_patchability(
        entry=entry,
        name=name,
        text=text,
        unlock=translated.unlock,
        ok=ok,
    )
    apply_mode = _entry_apply_mode(patchable, patch_warnings)
    review = _entry_review(
        entry=entry,
        name=name,
        text=text,
        unlock=translated.unlock,
        ok=ok,
        term_map=term_map or {},
        quality_review=quality_review,
        retry_history=retry_history,
    )
    return {
        "entry_key": entry.entry_key,
        "ok": ok,
        "patchable": patchable,
        "patch_warnings": patch_warnings,
        "apply_mode": apply_mode,
        "apply_warnings": patch_warnings,
        "target_units": _entry_target_units(entry),
        "name": name,
        "text": text,
        "unlock": translated.unlock,
        "token_errors": translated.token_errors,
        "source": _entry_source_row(entry),
        "rag_refs": _rag_ref_rows(references, tier_by_id=tier_by_id),
        "needs_review": (not ok) or _review_needs_attention(review),
        "review": review,
        "brief_version": brief_version,
    }


def _entry_is_name_only(entry) -> bool:
    return entry.name is not None and not entry.text and not entry.unlock


def _entry_name_only_preview_row(
    *,
    entry,
    name: str,
    references,
    tier_by_id: dict[int, str] | None = None,
    term_map: dict[str, str],
    brief_version: str,
) -> dict[str, object]:
    text: list[str] = []
    unlock: list[str] = []
    patchable, patch_warnings = _entry_patchability(
        entry=entry,
        name=name,
        text=text,
        unlock=unlock,
        ok=True,
    )
    apply_mode = _entry_apply_mode(patchable, patch_warnings)
    review = _entry_review(
        entry=entry,
        name=name,
        text=text,
        unlock=unlock,
        ok=True,
        term_map=term_map,
    )
    return {
        "entry_key": entry.entry_key,
        "ok": True,
        "patchable": patchable,
        "patch_warnings": patch_warnings,
        "apply_mode": apply_mode,
        "apply_warnings": patch_warnings,
        "target_units": _entry_target_units(entry),
        "name": name,
        "text": text,
        "unlock": unlock,
        "token_errors": [],
        "source": _entry_source_row(entry),
        "rag_refs": _rag_ref_rows(references, tier_by_id=tier_by_id),
        "needs_review": _review_needs_attention(review),
        "review": review,
        "brief_version": brief_version,
    }


def _apply_preview_consistency(rows: list[dict[str, object]]) -> None:
    name_terms = _preview_name_terms(rows)
    if not name_terms:
        return

    for row in rows:
        if row.get("ok") is not True:
            continue
        source = row.get("source")
        if not isinstance(source, dict):
            continue
        source_text = " ".join(
            item
            for field in ("name", "text", "unlock")
            for item in _source_field_strings(source.get(field))
        )
        if not source_text:
            continue

        for source_name, target_name in name_terms:
            if f"{source_name} Card" not in source_text:
                continue
            expected = target_name if target_name.endswith("牌") else f"{target_name}牌"
            if _row_contains_target(row, expected):
                continue
            if _replace_row_styled_card_target(row, expected):
                continue
            _add_consistency_warning(
                row,
                f"{source_name} Card should use mod-local name translation {expected!r}",
            )

        review = row.get("review")
        if isinstance(review, dict):
            row["needs_review"] = (row.get("ok") is not True) or _review_needs_attention(
                review
            )


def _preview_name_terms(rows: list[dict[str, object]]) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    for row in rows:
        if row.get("ok") is not True:
            continue
        entry_key = row.get("entry_key")
        if not isinstance(entry_key, str) or not entry_key.startswith("descriptions."):
            continue
        source = row.get("source")
        target_name = row.get("name")
        if not isinstance(source, dict) or not isinstance(target_name, str):
            continue
        source_name = source.get("name")
        if not isinstance(source_name, str) or not source_name.strip():
            continue
        if source_name == target_name:
            continue
        terms.append((source_name, target_name))
    return sorted(terms, key=lambda item: len(item[0]), reverse=True)


def _source_field_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _row_contains_target(row: dict[str, object], expected: str) -> bool:
    if row.get("name") == expected:
        return True
    return any(
        expected in item
        for field in ("text", "unlock")
        for item in _source_field_strings(row.get(field))
    )


def _replace_row_styled_card_target(row: dict[str, object], expected: str) -> bool:
    changed = False
    for field in ("text", "unlock"):
        value = row.get(field)
        if not isinstance(value, list):
            continue
        new_items = []
        for item in value:
            if not isinstance(item, str):
                new_items.append(item)
                continue
            new_item, count = _STYLED_CARD_TARGET_RE.subn(
                lambda match: f"{match.group(1)}{expected}{match.group(3)}",
                item,
                count=1,
            )
            changed = changed or count > 0
            new_items.append(new_item)
        row[field] = new_items
    return changed


def _add_consistency_warning(row: dict[str, object], message: str) -> None:
    review = row.get("review")
    if not isinstance(review, dict):
        review = _empty_review()
        row["review"] = review
    warnings = review.get("consistency_warnings")
    if not isinstance(warnings, list):
        warnings = []
        review["consistency_warnings"] = warnings
    if message not in warnings:
        warnings.append(message)


def _maybe_retry_entry_translation(
    *,
    translator,
    entry,
    translated,
    pretranslated_name: str | None = None,
    body_text: str,
    max_width: int,
    references: list[TranslationReference],
    style_examples: str = "",
):
    retry_history: list[dict[str, object]] = []
    quality_review = _empty_quality_review()
    if translated.token_errors:
        return translated, quality_review, retry_history

    review_method = getattr(translator, "review_entry_translation", None)
    revise_method = getattr(translator, "revise_entry_translation", None)
    if not callable(review_method) or not callable(revise_method):
        return translated, quality_review, retry_history

    reviewed_name = pretranslated_name if pretranslated_name is not None else translated.name
    quality_review = review_method(
        name_text=entry.name.source_text if entry.name is not None else None,
        body_text=body_text,
        unlock_text=entry.combined_unlock,
        name=reviewed_name,
        text=translated.text,
        unlock=translated.unlock,
        references=references,
        style_examples=style_examples,
    )
    if not getattr(quality_review, "needs_revision", False):
        return translated, quality_review, retry_history

    retry_history.append(
        {
            "reason": "quality_review",
            "naturalness_warnings": list(
                getattr(quality_review, "naturalness_warnings", [])
            ),
            "meaning_warnings": list(getattr(quality_review, "meaning_warnings", [])),
            "rewrite_hint": getattr(quality_review, "rewrite_hint", ""),
        }
    )
    revised = revise_method(
        name_text=entry.name.source_text if entry.name is not None else None,
        body_text=body_text,
        unlock_text=entry.combined_unlock,
        current_name=reviewed_name,
        current_text=translated.text,
        current_unlock=translated.unlock,
        review_feedback=_quality_review_feedback(quality_review),
        references=references,
        max_width=max_width,
        style_examples=style_examples,
    )
    if revised.token_errors:
        retry_history[-1]["retry_token_errors"] = revised.token_errors
        return translated, quality_review, retry_history

    final_review = review_method(
        name_text=entry.name.source_text if entry.name is not None else None,
        body_text=body_text,
        unlock_text=entry.combined_unlock,
        name=pretranslated_name if pretranslated_name is not None else revised.name,
        text=revised.text,
        unlock=revised.unlock,
        references=references,
        style_examples=style_examples,
    )
    return revised, final_review, retry_history


def _quality_review_feedback(review) -> str:
    parts: list[str] = []
    naturalness = list(getattr(review, "naturalness_warnings", []))
    meaning = list(getattr(review, "meaning_warnings", []))
    if naturalness:
        parts.append("Naturalness warnings: " + "; ".join(naturalness))
    if meaning:
        parts.append("Meaning warnings: " + "; ".join(meaning))
    rewrite_hint = getattr(review, "rewrite_hint", "")
    if rewrite_hint:
        parts.append("Rewrite hint: " + rewrite_hint)
    return "\n".join(parts) if parts else "Revise the translation to sound natural."


def _entry_error_row(
    *,
    entry,
    references,
    error: Exception,
    tier_by_id: dict[int, str] | None = None,
    brief_version: str = "",
) -> dict[str, object]:
    return {
        "entry_key": entry.entry_key,
        "ok": False,
        "patchable": False,
        "patch_warnings": ["entry translation failed"],
        "apply_mode": "blocked",
        "apply_warnings": ["entry translation failed"],
        "target_units": _entry_target_units(entry),
        "name": None,
        "text": [],
        "unlock": [],
        "token_errors": [],
        "error": str(error),
        "source": _entry_source_row(entry),
        "rag_refs": _rag_ref_rows(references, tier_by_id=tier_by_id),
        "needs_review": True,
        "review": _empty_review(),
        "brief_version": brief_version,
    }


def _entry_review(
    *,
    entry,
    name: str | None,
    text: list[str],
    unlock: list[str],
    ok: bool,
    term_map: dict[str, str],
    quality_review=None,
    retry_history: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Run the locked-term checker over one entry's translation."""
    violations: list[dict[str, object]] = []
    if ok and term_map:
        source = _entry_source_row(entry)
        violations = [
            v.to_dict()
            for v in check_entry_terms(
                source=source,
                target={"name": name, "text": text, "unlock": unlock},
                term_map=term_map,
            )
        ]
    quality = quality_review or _empty_quality_review()
    return {
        "term_violations": violations,
        "consistency_warnings": [],
        "naturalness_warnings": list(getattr(quality, "naturalness_warnings", [])),
        "meaning_warnings": list(getattr(quality, "meaning_warnings", [])),
        "rewrite_hint": getattr(quality, "rewrite_hint", ""),
        "retry_history": retry_history or [],
    }


def _empty_review() -> dict[str, object]:
    return {
        "term_violations": [],
        "consistency_warnings": [],
        "naturalness_warnings": [],
        "meaning_warnings": [],
        "rewrite_hint": "",
        "retry_history": [],
    }


def _review_needs_attention(review: dict[str, object]) -> bool:
    return any(
        bool(review.get(key))
        for key in (
            "term_violations",
            "consistency_warnings",
            "naturalness_warnings",
            "meaning_warnings",
        )
    )


def _empty_quality_review():
    class EmptyQualityReview:
        needs_revision = False
        naturalness_warnings: list[str] = []
        meaning_warnings: list[str] = []
        rewrite_hint = ""

    return EmptyQualityReview()


def _brief_version(term_map: dict[str, str]) -> str:
    """Reproducible hash of the frozen locked-term map used for a batch."""
    import hashlib

    payload = json.dumps(term_map, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


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


def _entry_apply_mode(patchable: bool, warnings: list[str]) -> str:
    if patchable:
        return "unit"
    if warnings and all(_is_table_level_apply_warning(warning) for warning in warnings):
        return "table"
    return "blocked"


def _entry_translatable_body(entry) -> str:
    return " ".join(
        unit.source_text for unit in entry.text if not _is_credit_line(unit.source_text)
    )


def _entry_credit_lines(entry) -> list[str]:
    return [unit.source_text for unit in entry.text if _is_credit_line(unit.source_text)]


def _is_credit_line(text: str) -> bool:
    return bool(_CREDIT_LINE_RE.match(text))


def _translation_references(
    references, *, tier_by_id: dict[int, str] | None = None
) -> list[TranslationReference]:
    tiers = tier_by_id or {}
    return [
        TranslationReference(
            source_text=ref.source_text,
            target_text=ref.target_text,
            score=ref.score,
            tier=tiers.get(getattr(ref, "tm_entry_id", None), "loose"),
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


def _build_tier_by_id(
    glossary_refs, dense_refs, expected_context_types: set[str]
) -> dict[int, str]:
    """Map ``tm_entry_id`` → tier.

    Glossary hits are ``locked`` and win over dense hits. Dense hits whose
    ``context_type`` matches the entry's expected context types are
    ``same_context``; the rest are ``loose``.
    """
    tier_by_id: dict[int, str] = {}
    for ref in glossary_refs:
        tier_by_id[getattr(ref, "tm_entry_id", None)] = "locked"
    for ref in dense_refs:
        ref_id = getattr(ref, "tm_entry_id", None)
        if ref_id in tier_by_id:
            continue  # glossary wins
        tier_by_id[ref_id] = (
            "same_context"
            if getattr(ref, "context_type", "") in expected_context_types
            else "loose"
        )
    return tier_by_id


def _entry_expected_context_types(entry_key: str) -> set[str]:
    """Context types that count as same-context for an entry's refs."""
    parts = entry_key.split(".")
    if len(parts) < 2 or parts[0] != "descriptions":
        return set()
    label = _context_label(parts[1])
    return {f"{label}_description_line", f"{label}_name"}


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


def _rag_ref_rows(
    references, *, tier_by_id: dict[int, str] | None = None
) -> list[dict[str, object]]:
    tiers = tier_by_id or {}
    return [
        {
            "score": ref.score,
            "mod": ref.mod_id,
            "unit_key": ref.unit_key,
            "context_type": getattr(ref, "context_type", ""),
            "tier": tiers.get(getattr(ref, "tm_entry_id", None), "loose"),
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
