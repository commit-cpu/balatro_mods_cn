from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.lua.extractor import LuaExtractor, TranslationUnit
from app.lua.grouping import TranslationEntry, group_translation_units
from app.lua.patcher import LuaPatcher, PatchInstruction
from app.lua.string_literals import escape_lua_string_content
from app.lua.tokens import validate_token_identity


@dataclass(frozen=True)
class IncrementalContextResult:
    context_rows: list[dict[str, Any]]
    missing_entry_keys: list[str]
    missing_unit_keys: list[str]
    source_unit_count: int
    target_unit_count: int


def build_incremental_context(
    source_path: Path,
    target_path: Path,
) -> IncrementalContextResult:
    source_units = LuaExtractor().extract_file(source_path)
    target_units = LuaExtractor().extract_file(target_path) if target_path.exists() else []
    source_by_key = {unit.unit_key: unit for unit in source_units}
    target_by_key = {unit.unit_key: unit for unit in target_units}
    missing = [unit.unit_key for unit in source_units if unit.unit_key not in target_by_key]
    entry_by_unit = _entry_key_by_unit(source_units)
    missing_entries = _ordered_unique(
        entry_by_unit[key] for key in missing if key in entry_by_unit
    )

    context_rows = [
        row
        for entry in group_translation_units(source_units)
        if (row := _context_row_for_entry(entry, source_by_key, target_by_key)) is not None
    ]
    context_rows = [
        row
        for row in context_rows
        if row["entry_key"] not in missing_entries or _row_has_usable_name(row)
    ]

    return IncrementalContextResult(
        context_rows=context_rows,
        missing_entry_keys=missing_entries,
        missing_unit_keys=missing,
        source_unit_count=len(source_units),
        target_unit_count=len(target_units),
    )


def apply_missing_preview_to_source(
    *,
    source_path: Path,
    target_path: Path,
    preview_rows: list[dict[str, Any]],
    missing_unit_keys: set[str],
) -> tuple[bytes, dict[str, int]]:
    source_bytes = source_path.read_bytes()
    source_units = LuaExtractor().extract_file(source_path)
    target_units = LuaExtractor().extract_file(target_path) if target_path.exists() else []
    target_by_key = {unit.unit_key: unit.source_text for unit in target_units}
    preview_translations = _preview_translation_map(preview_rows)

    instructions: list[PatchInstruction] = []
    filled_missing = 0
    errors: list[str] = []
    for unit in source_units:
        if unit.byte_start < 0 or unit.byte_end < 0:
            errors.append(f"runtime-generated unit cannot be written: {unit.unit_key}")
            continue
        if unit.unit_key in missing_unit_keys:
            value = preview_translations.get(unit.unit_key)
            if not isinstance(value, str):
                errors.append(f"missing preview translation: {unit.unit_key}")
                continue
            filled_missing += 1
        else:
            value = target_by_key.get(unit.unit_key, unit.source_text)
        instructions.append(
            PatchInstruction(
                unit_key=unit.unit_key,
                byte_start=unit.byte_start,
                byte_end=unit.byte_end,
                new_text=escape_lua_string_content(value),
            )
        )
    if errors:
        raise ValueError("; ".join(errors))

    patched = LuaPatcher().patch(source_bytes, instructions)
    stats = {
        "source_units": len(source_units),
        "existing_units": len(set(target_by_key) & {unit.unit_key for unit in source_units}),
        "missing_units": len(missing_unit_keys),
        "filled_missing_units": filled_missing,
    }
    return patched, stats


def _context_row_for_entry(
    entry: TranslationEntry,
    source_by_key: dict[str, TranslationUnit],
    target_by_key: dict[str, TranslationUnit],
) -> dict[str, Any] | None:
    name = _valid_target_text(entry.name, source_by_key, target_by_key) if entry.name else None
    text = _complete_valid_field(entry.text, source_by_key, target_by_key)
    unlock = _complete_valid_field(entry.unlock, source_by_key, target_by_key)
    if name is None and not text and not unlock:
        return None
    return {
        "entry_key": entry.entry_key,
        "ok": True,
        "patchable": False,
        "patch_warnings": ["context row generated from existing zh_CN.lua"],
        "apply_mode": "blocked",
        "apply_warnings": ["context only"],
        "target_units": _entry_target_units(entry),
        "name": name,
        "text": text,
        "unlock": unlock,
        "token_errors": [],
        "source": _entry_source_row(entry),
        "rag_refs": [],
        "needs_review": False,
        "review": _empty_review(),
        "brief_version": "",
        "reuse_source": "existing_zh_lua",
    }


def _valid_target_text(
    source_unit: TranslationUnit | None,
    source_by_key: dict[str, TranslationUnit],
    target_by_key: dict[str, TranslationUnit],
) -> str | None:
    if source_unit is None:
        return None
    source = source_by_key.get(source_unit.unit_key)
    target = target_by_key.get(source_unit.unit_key)
    if source is None or target is None:
        return None
    if source.source_text == target.source_text and _contains_ascii(source.source_text):
        return None
    if _has_residual_english(target.source_text):
        return None
    if validate_token_identity(source.source_text, target.source_text, order_sensitive=False):
        return None
    return target.source_text


def _complete_valid_field(
    units: list[TranslationUnit],
    source_by_key: dict[str, TranslationUnit],
    target_by_key: dict[str, TranslationUnit],
) -> list[str]:
    if not units:
        return []
    values: list[str] = []
    for unit in units:
        value = _valid_target_text(unit, source_by_key, target_by_key)
        if value is None:
            return []
        values.append(value)
    return values


def _preview_translation_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    translations: dict[str, str] = {}
    for row in rows:
        if row.get("ok") is not True or row.get("needs_review") is True:
            continue
        target_units = row.get("target_units")
        if not isinstance(target_units, dict):
            continue
        name_key = target_units.get("name")
        name_value = row.get("name")
        if isinstance(name_key, str) and isinstance(name_value, str):
            translations[name_key] = name_value
        _extend_list_translations(
            translations,
            target_units.get("text"),
            row.get("text"),
        )
        _extend_list_translations(
            translations,
            target_units.get("unlock"),
            row.get("unlock"),
        )
    return translations


def _extend_list_translations(
    translations: dict[str, str],
    keys: object,
    values: object,
) -> None:
    if not isinstance(keys, list) or not isinstance(values, list):
        return
    for key, value in zip(keys, values, strict=False):
        if isinstance(key, str) and isinstance(value, str):
            translations[key] = value


def _entry_key_by_unit(units: list[TranslationUnit]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in group_translation_units(units):
        for unit in _entry_units(entry):
            mapping[unit.unit_key] = entry.entry_key
    return mapping


def _entry_units(entry: TranslationEntry) -> list[TranslationUnit]:
    units = []
    if entry.name is not None:
        units.append(entry.name)
    units.extend(entry.text)
    units.extend(entry.unlock)
    return units


def _entry_target_units(entry: TranslationEntry) -> dict[str, Any]:
    return {
        "name": entry.name.unit_key if entry.name is not None else None,
        "text": [unit.unit_key for unit in entry.text],
        "unlock": [unit.unit_key for unit in entry.unlock],
    }


def _entry_source_row(entry: TranslationEntry) -> dict[str, Any]:
    return {
        "name": entry.name.source_text if entry.name is not None else None,
        "text": [unit.source_text for unit in entry.text],
        "unlock": [unit.source_text for unit in entry.unlock],
    }


def _empty_review() -> dict[str, Any]:
    return {
        "term_violations": [],
        "consistency_warnings": [],
        "naturalness_warnings": [],
        "meaning_warnings": [],
        "rewrite_hint": "",
        "retry_history": [],
    }


def _ordered_unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _row_has_usable_name(row: dict[str, Any]) -> bool:
    return isinstance(row.get("name"), str) and bool(row.get("name"))


def _contains_ascii(value: str) -> bool:
    return any("A" <= char <= "Z" or "a" <= char <= "z" for char in value)


def _has_residual_english(value: str) -> bool:
    cleaned = []
    in_token = False
    for char in value:
        if char == "{":
            in_token = True
            cleaned.append(" ")
            continue
        if char == "}":
            in_token = False
            cleaned.append(" ")
            continue
        cleaned.append(" " if in_token else char)
    text = "".join(cleaned)
    if not any("\u3400" <= char <= "\u9fff" for char in text):
        return False
    words = [word.casefold() for word in _ascii_words(text)]
    return any(word in _GAMEPLAY_ENGLISH_WORDS for word in words)


def _ascii_words(value: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    for char in value:
        if char.isascii() and (char.isalpha() or char.isdigit() or char in "_.?'-"):
            current.append(char)
        elif current:
            word = "".join(current).strip("_.?'-")
            if len(word) >= 3 and any(ch.isalpha() for ch in word):
                words.append(word)
            current = []
    if current:
        word = "".join(current).strip("_.?'-")
        if len(word) >= 3 and any(ch.isalpha() for ch in word):
            words.append(word)
    return words


_GAMEPLAY_ENGLISH_WORDS = {
    "add",
    "adds",
    "after",
    "and",
    "card",
    "cards",
    "chip",
    "chips",
    "discard",
    "gain",
    "gains",
    "hand",
    "level",
    "lvl",
    "mult",
    "played",
    "score",
    "scoring",
    "selected",
    "when",
}
