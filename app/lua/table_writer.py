from __future__ import annotations

from dataclasses import dataclass

from app.lua.extractor import (
    _field_name,
    _find_field,
    _first_child_of_type,
    _get_parser,
    _iter_fields,
    _string_content,
)
from app.lua.patcher import PatchInstruction
from app.lua.string_literals import escape_lua_string_content


@dataclass(frozen=True, slots=True)
class EntryTableTranslation:
    entry_key: str
    name: str | None
    text: list[str]
    unlock: list[str]


def build_entry_table_patches(
    source: bytes,
    entries: list[EntryTableTranslation],
) -> tuple[list[PatchInstruction], list[str]]:
    parser = _get_parser()
    tree = parser.parse(source)
    outer_table = _outer_table(tree.root_node)
    if outer_table is None:
        return [], ["missing root localization table"]
    desc_field = _find_field(source, outer_table, "descriptions")
    if desc_field is None:
        return [], ["missing descriptions table"]
    desc_table = _first_child_of_type(desc_field, "table_constructor")
    if desc_table is None:
        return [], ["missing descriptions table"]

    patches: list[PatchInstruction] = []
    errors: list[str] = []
    for entry in entries:
        entry_table = _find_entry_table(source, desc_table, entry.entry_key)
        if entry_table is None:
            errors.append(f"missing entry: {entry.entry_key}")
            continue
        if entry.name is not None:
            _append_name_patch(source, patches, errors, entry_table, entry)
        _append_array_patch(source, patches, errors, entry_table, entry, "text")
        _append_array_patch(source, patches, errors, entry_table, entry, "unlock")
    return patches, errors


def _outer_table(root):
    if root.type != "chunk":
        return None
    return_stmt = _first_child_of_type(root, "return_statement")
    if return_stmt is None:
        return None
    expr_list = _first_child_of_type(return_stmt, "expression_list")
    if expr_list is None:
        return None
    return _first_child_of_type(expr_list, "table_constructor")


def _find_entry_table(source: bytes, desc_table, entry_key: str):
    parts = entry_key.split(".")
    if len(parts) != 3 or parts[0] != "descriptions":
        return None
    category_name = parts[1]
    raw_entry_name, target_occurrence = _split_occurrence_entry_name(parts[2])
    seen = 0
    for category_field in _iter_fields(desc_table):
        if _field_name(source, category_field) != category_name:
            continue
        category_table = _first_child_of_type(category_field, "table_constructor")
        if category_table is None:
            continue
        for entry_field in _iter_fields(category_table):
            if _field_name(source, entry_field) != raw_entry_name:
                continue
            seen += 1
            if seen == target_occurrence:
                return _first_child_of_type(entry_field, "table_constructor")
    return None


def _split_occurrence_entry_name(entry_name: str) -> tuple[str, int]:
    if "#" not in entry_name:
        return entry_name, 1
    raw, suffix = entry_name.rsplit("#", 1)
    if not raw or not suffix.isdecimal():
        return entry_name, 1
    occurrence = int(suffix)
    return raw, occurrence if occurrence > 1 else 1


def _append_name_patch(
    source: bytes,
    patches: list[PatchInstruction],
    errors: list[str],
    entry_table,
    entry: EntryTableTranslation,
) -> None:
    name_field = _find_field(source, entry_table, "name")
    if name_field is None:
        errors.append(f"missing name field: {entry.entry_key}")
        return
    str_node = _first_child_of_type(name_field, "string")
    if str_node is None:
        errors.append(f"missing name string: {entry.entry_key}")
        return
    _, start, end = _string_content(source, str_node)
    patches.append(
        PatchInstruction(
            unit_key=f"{entry.entry_key}.name",
            byte_start=start,
            byte_end=end,
            new_text=escape_lua_string_content(entry.name or ""),
        )
    )


def _append_array_patch(
    source: bytes,
    patches: list[PatchInstruction],
    errors: list[str],
    entry_table,
    entry: EntryTableTranslation,
    field: str,
) -> None:
    values = getattr(entry, field)
    if not values:
        return
    array_field = _find_field(source, entry_table, field)
    if array_field is None:
        errors.append(f"missing {field} field: {entry.entry_key}")
        return
    table = _first_child_of_type(array_field, "table_constructor")
    if table is None:
        errors.append(f"missing {field} table: {entry.entry_key}")
        return
    field_indent = _line_indent(source, array_field.start_byte)
    item_indent = field_indent + "    "
    replacement = _format_lua_string_array(values, field_indent, item_indent)
    patches.append(
        PatchInstruction(
            unit_key=f"{entry.entry_key}.{field}",
            byte_start=table.start_byte,
            byte_end=table.end_byte,
            new_text=replacement,
        )
    )


def _format_lua_string_array(
    values: list[str],
    field_indent: str,
    item_indent: str,
) -> str:
    lines = ["{"]
    for value in values:
        lines.append(f'{item_indent}"{escape_lua_string_content(value)}",')
    lines.append(f"{field_indent}}}")
    return "\n".join(lines)


def _line_indent(source: bytes, byte_offset: int) -> str:
    line_start = source.rfind(b"\n", 0, byte_offset) + 1
    line = source[line_start:byte_offset].decode("utf-8")
    return line[: len(line) - len(line.lstrip(" \t"))]
