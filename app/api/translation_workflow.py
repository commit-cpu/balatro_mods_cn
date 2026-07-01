from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from app.api.repositories import ApiRepository
from app.api.schemas import TranslationStart
from app.cli.main import (
    reset_translation_progress_callback,
    set_translation_progress_callback,
    translate_entry_loop,
)
from app.cli.translation_loop import default_loop_work_dir
from app.db.connection import connect
from app.lua.extractor import LuaExtractor
from app.lua.patcher import LuaPatcher, PatchInstruction
from app.lua.string_literals import escape_lua_string_content
from app.lua.table_writer import EntryTableTranslation, build_entry_table_patches
from app.lua.validator import validate_file


_ENTRY_UNIT_RE = re.compile(
    r"^(?P<entry>descriptions\.[^.]+\.[^.]+)\.(?P<field>name|text\[(?P<text>\d+)\]|unlock\[(?P<unlock>\d+)\])$"
)


def run_translation_job(db_path: Path, job_id: int, payload: dict[str, Any]) -> None:
    repo = ApiRepository(db_path)
    repo.update_job_status(job_id, "running")
    progress_token = set_translation_progress_callback(
        lambda event, message, event_payload: repo.log_job_event(
            job_id,
            event=event,
            message=message,
            payload=event_payload,
        )
    )
    try:
        repo_path = Path(payload["repo_path"])
        work_dir = Path(payload["work_dir"])
        repo.log_job_event(
            job_id,
            event="translation.loop.start",
            message="Starting translation loop",
            payload={
                "mod_id": payload.get("mod_id"),
                "repo_path": str(repo_path),
                "source": payload.get("source"),
                "output": payload.get("output"),
                "work_dir": str(work_dir),
                "max_rounds": payload.get("max_rounds"),
            },
        )
        translate_entry_loop(
            repo=repo_path,
            source=str(payload["source"]),
            output=Path(str(payload["output"])),
            work_dir=work_dir,
            limit=int(payload.get("limit") or 9999),
            top_k=int(payload.get("top_k") or 5),
            max_width=int(payload.get("max_width") or 18),
            concurrency=payload.get("concurrency"),
            max_rounds=int(payload.get("max_rounds") or 3),
            include_needs_review=bool(payload.get("include_needs_review")),
            validate_lua=bool(payload.get("validate_lua", True)),
            brief=None,
        )
        imported = import_latest_preview_review_items(
            db_path=db_path,
            mod_id=str(payload["mod_id"]),
            work_dir=work_dir,
        )
        repo.log_job_event(
            job_id,
            event="translation.review_items.imported",
            message="Imported review items from latest preview",
            payload={"mod_id": payload.get("mod_id"), "imported_review_items": imported},
        )
        repo.log_job_event(
            job_id,
            event="translation.loop.complete",
            message="Translation loop completed",
            payload={"mod_id": payload.get("mod_id"), "work_dir": str(work_dir)},
        )
        repo.update_job_status(
            job_id,
            "succeeded",
            result={"imported_review_items": imported},
        )
    except Exception as exc:
        repo.log_job_event(
            job_id,
            level="error",
            event="translation.loop.failed",
            message=str(exc),
            payload={"mod_id": payload.get("mod_id")},
        )
        repo.update_job_status(job_id, "failed", last_error=str(exc))
    finally:
        reset_translation_progress_callback(progress_token)


def import_latest_preview_review_items(
    *,
    db_path: Path,
    mod_id: str,
    work_dir: Path,
) -> int:
    manifest_path = work_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rounds = manifest.get("rounds") if isinstance(manifest, dict) else None
    if not isinstance(rounds, list) or not rounds:
        raise ValueError(f"manifest has no rounds: {manifest_path}")
    preview_path = Path(str(rounds[-1]["preview"]))
    rows = _read_jsonl(preview_path)
    review_rows = _preview_rows_to_review_items(mod_id, rows)
    with connect(db_path) as db:
        approved_rows = db.execute(
            """
            select unit_key, source_text
            from review_items
            where mod_id = ? and status = 'approved'
            """,
            (mod_id,),
        ).fetchall()
        approved_keys = {
            (str(row["unit_key"]), str(row["source_text"])) for row in approved_rows
        }
        review_rows = [
            row for row in review_rows if (row[1], row[2]) not in approved_keys
        ]
        db.execute(
            "delete from review_items where mod_id = ? and status != 'approved'",
            (mod_id,),
        )
        db.executemany(
            """
            insert into review_items(
                mod_id, unit_key, source_text, current_target_text,
                suggested_target_text, status, reason
            ) values (?, ?, ?, null, ?, 'pending', ?)
            """,
            review_rows,
        )
        db.commit()
    return len(review_rows)


def apply_approved_review_items(db_path: Path, mod_id: str) -> dict[str, Any]:
    repo = ApiRepository(db_path)
    mod = repo.get_mod(mod_id)
    if mod is None:
        raise KeyError(mod_id)
    repo_path = Path(str(mod["repo_path"]))
    source_path = repo_path / str(mod["source_locale_path"])
    output_path = repo_path / str(mod["target_locale_path"])
    base_path = _translation_candidate_path(repo_path) or source_path
    rows = repo.list_review_items(status="approved", mod_id=mod_id, limit=100_000)
    source_bytes = base_path.read_bytes()
    units = LuaExtractor().extract_file(base_path)
    unit_by_key = {unit.unit_key: unit for unit in units}

    table_groups: dict[str, dict[str, Any]] = {}
    unit_translations: dict[str, str] = {}
    applied_items = 0
    for row in rows:
        final_text = _final_review_text(row)
        applied_items += 1
        match = _ENTRY_UNIT_RE.match(row["unit_key"])
        if match:
            entry = table_groups.setdefault(
                match.group("entry"),
                {"name": None, "text": {}, "unlock": {}},
            )
            field = match.group("field")
            if field == "name":
                entry["name"] = final_text
            elif match.group("text") is not None:
                if final_text != "":
                    entry["text"][int(match.group("text"))] = final_text
            elif match.group("unlock") is not None and final_text != "":
                entry["unlock"][int(match.group("unlock"))] = final_text
            continue
        if final_text != "":
            unit_translations[row["unit_key"]] = final_text

    table_entries = [
        EntryTableTranslation(
            entry_key=entry_key,
            name=entry["name"],
            text=[value for _, value in sorted(entry["text"].items())],
            unlock=[value for _, value in sorted(entry["unlock"].items())],
        )
        for entry_key, entry in sorted(table_groups.items())
    ]
    instructions = [
        PatchInstruction(
            unit_key=key,
            byte_start=unit_by_key[key].byte_start,
            byte_end=unit_by_key[key].byte_end,
            new_text=escape_lua_string_content(value),
        )
        for key, value in sorted(unit_translations.items())
        if key in unit_by_key
    ]
    table_instructions, table_errors = build_entry_table_patches(source_bytes, table_entries)
    if table_errors:
        raise ValueError("; ".join(table_errors))
    instructions.extend(table_instructions)
    patched = LuaPatcher().patch(source_bytes, instructions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    tmp_path.write_bytes(patched)
    valid, error = validate_file(tmp_path)
    if not valid:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(error)
    tmp_path.replace(output_path)
    return {
        "mod_id": mod_id,
        "base": str(base_path),
        "output": str(output_path),
        "applied_items": applied_items,
        "applied_entries": len(table_entries),
        "applied_units": len(instructions),
    }


def _translation_candidate_path(repo_path: Path) -> Path | None:
    work_dir = default_loop_work_dir(repo_path)
    manifest_path = work_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        output = manifest.get("output") if isinstance(manifest, dict) else None
        if isinstance(output, str) and output:
            candidate = Path(output)
            if not candidate.is_absolute():
                candidate = manifest_path.parent / candidate
            if candidate.exists():
                return candidate.resolve()
    fallback = work_dir / "candidate_zh_CN.lua"
    if fallback.exists():
        return fallback.resolve()
    return None


def translation_payload(mod: dict[str, Any], request: TranslationStart) -> dict[str, Any]:
    repo_path = Path(str(mod["repo_path"]))
    work_dir = default_loop_work_dir(repo_path)
    return {
        "mod_id": mod["mod_id"],
        "repo_path": str(repo_path),
        "source": mod["source_locale_path"],
        "target": mod["target_locale_path"],
        "output": str((work_dir / "candidate_zh_CN.lua").resolve()),
        "work_dir": str(work_dir),
        "limit": request.limit,
        "top_k": request.top_k,
        "max_width": request.max_width,
        "concurrency": request.concurrency,
        "max_rounds": request.max_rounds,
        "include_needs_review": request.include_needs_review,
        "validate_lua": request.validate_lua,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _preview_rows_to_review_items(
    mod_id: str,
    rows: list[dict[str, Any]],
) -> list[tuple[str, str, str, str | None, str]]:
    items: list[tuple[str, str, str, str | None, str]] = []
    for row in rows:
        if (
            row.get("ok") is True
            and row.get("needs_review") is not True
            and not _preview_row_is_blocked(row)
        ):
            continue
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        target_units = row.get("target_units") if isinstance(row.get("target_units"), dict) else {}
        reason = _review_reason(row)
        name_key = target_units.get("name")
        if isinstance(name_key, str):
            items.append(
                (
                    mod_id,
                    name_key,
                    str(source.get("name") or ""),
                    _optional_str(row.get("name")),
                    reason,
                )
            )
        for field in ("text", "unlock"):
            unit_keys = target_units.get(field)
            source_values = source.get(field)
            target_values = row.get(field)
            if not isinstance(unit_keys, list):
                continue
            for index, unit_key in enumerate(unit_keys):
                if not isinstance(unit_key, str):
                    continue
                items.append(
                    (
                        mod_id,
                        unit_key,
                        _list_value(source_values, index),
                        _optional_str(
                            _review_target_value(
                                target_values,
                                index=index,
                                unit_count=len(unit_keys),
                            )
                        ),
                        reason,
                    )
                )
    return items


def _review_reason(row: dict[str, Any]) -> str:
    if row.get("ok") is not True:
        return "translation_failed"
    if _preview_row_is_blocked(row):
        return "ai_translation_blocked"
    if row.get("needs_review"):
        return "ai_translation_needs_review"
    return "ai_translation_review"


def _preview_row_is_blocked(row: dict[str, Any]) -> bool:
    return row.get("apply_mode") == "blocked"


def _review_target_value(value: Any, *, index: int, unit_count: int) -> Any:
    if unit_count == 1 and isinstance(value, list) and len(value) > 1:
        return "".join(str(part).strip() for part in value if isinstance(part, str))
    return _list_raw_value(value, index)


def _list_value(value: Any, index: int) -> str:
    raw = _list_raw_value(value, index)
    return raw if isinstance(raw, str) else ""


def _list_raw_value(value: Any, index: int) -> Any:
    if not isinstance(value, list) or index >= len(value):
        return None
    return value[index]


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _final_review_text(row: dict[str, Any]) -> str:
    for key in ("edited_target_text", "suggested_target_text", "current_target_text"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    return ""
