from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import connect
from app.lua.extractor import LuaExtractor, TranslationUnit
from app.lua.tokens import TokenizedString, normalize_for_rag, validate_token_identity


@dataclass(frozen=True)
class ImportResult:
    mod_id: str
    source_unit_count: int
    target_unit_count: int
    imported_pair_count: int
    skipped_count: int


def import_locale_pair(
    *,
    db_path: Path,
    mod_id: str,
    repo_path: Path,
    source_locale_path: str,
    target_locale_path: str,
    collection: str,
) -> ImportResult:
    extractor = LuaExtractor()
    source_units = extractor.extract_file(repo_path / source_locale_path)
    target_units = extractor.extract_file(repo_path / target_locale_path)
    target_by_key = {unit.unit_key: unit for unit in target_units}

    imported = 0
    skipped = 0

    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(
                mod_id, repo_path, source_locale_path, target_locale_path
            ) values (?, ?, ?, ?)
            on conflict(mod_id) do update set
                repo_path = excluded.repo_path,
                source_locale_path = excluded.source_locale_path,
                target_locale_path = excluded.target_locale_path
            """,
            (mod_id, str(repo_path), source_locale_path, target_locale_path),
        )

        for source_unit in source_units:
            target_unit = target_by_key.get(source_unit.unit_key)
            if target_unit is None:
                skipped += 1
                continue

            entry = _build_entry(mod_id, source_unit, target_unit)
            if entry is None:
                skipped += 1
                continue

            cursor = db.execute(
                """
                insert or ignore into tm_entries(
                    mod_id, unit_key, context_type, source_text, target_text,
                    normalized_source, token_signature, quality, qdrant_point_id,
                    source_hash, target_hash
                ) values (
                    :mod_id, :unit_key, :context_type, :source_text, :target_text,
                    :normalized_source, :token_signature, :quality, :qdrant_point_id,
                    :source_hash, :target_hash
                )
                """,
                entry,
            )
            if cursor.rowcount != 1:
                continue

            tm_entry_id = db.execute(
                "select id from tm_entries where qdrant_point_id = ?",
                (entry["qdrant_point_id"],),
            ).fetchone()["id"]
            db.execute(
                """
                insert or ignore into vector_outbox(tm_entry_id, operation, collection)
                values (?, 'upsert', ?)
                """,
                (tm_entry_id, collection),
            )
            imported += 1

        db.execute(
            """
            insert into import_runs(
                mod_id, source_locale_path, target_locale_path,
                source_unit_count, imported_pair_count, skipped_count
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                mod_id,
                source_locale_path,
                target_locale_path,
                len(source_units),
                imported,
                skipped,
            ),
        )
        db.commit()

    return ImportResult(
        mod_id=mod_id,
        source_unit_count=len(source_units),
        target_unit_count=len(target_units),
        imported_pair_count=imported,
        skipped_count=skipped,
    )


def _build_entry(
    mod_id: str,
    source_unit: TranslationUnit,
    target_unit: TranslationUnit,
) -> dict[str, str] | None:
    source_text = source_unit.source_text
    target_text = target_unit.source_text
    if not source_text.strip() or not target_text.strip():
        return None
    if validate_token_identity(source_text, target_text):
        return None

    source_hash = _sha256(source_text)
    target_hash = _sha256(target_text)
    qdrant_point_id = _sha256(
        f"{mod_id}:{source_unit.unit_key}:{source_hash}:{target_hash}"
    )

    return {
        "mod_id": mod_id,
        "unit_key": source_unit.unit_key,
        "context_type": source_unit.context_type,
        "source_text": source_text,
        "target_text": target_text,
        "normalized_source": normalize_for_rag(source_text),
        "token_signature": TokenizedString.from_string(source_text).token_signature,
        "quality": "imported_human",
        "qdrant_point_id": qdrant_point_id,
        "source_hash": source_hash,
        "target_hash": target_hash,
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
