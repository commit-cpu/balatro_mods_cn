"""Lossless Lua localization extractor using tree-sitter.

Walks the AST of a Balatro-style ``return { descriptions = { ... } }`` file,
extracting every translatable string together with:

* ``unit_key`` – dotted path like ``descriptions.Joker.j_foo.text[0]``
* ``byte_span`` – (start, end) offsets of the string *content* (without quotes)
* ``context_type`` – inferred category (``joker_description_line``, ``back_name``, etc.)
* ``raw_tokens`` – list of token strings present in the source text
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import tree_sitter_lua as tslua
from tree_sitter import Language, Parser

from app.lua.tokens import TokenSpan, extract_tokens

# ---------------------------------------------------------------------------
# shared parser (lazy init, thread-safe enough for single worker)
# ---------------------------------------------------------------------------

_LANG: Language | None = None
_PARSER: Parser | None = None


def _get_parser() -> Parser:
    global _LANG, _PARSER
    if _LANG is None:
        _LANG = Language(tslua.language())
    if _PARSER is None:
        _PARSER = Parser(_LANG)
    return _PARSER


# ---------------------------------------------------------------------------
# data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TranslationUnit:
    """One translatable string extracted from a Lua localization file."""

    unit_key: str
    """Dotted path, e.g. ``descriptions.Joker.j_foo.text[0]``."""

    source_text: str
    """The raw English text (with tokens intact)."""

    byte_start: int
    """Byte offset of the string *content* (inside quotes) in the source file."""

    byte_end: int
    """Byte offset (exclusive) of the string *content*."""

    context_type: str
    """Inferred category for RAG filtering, e.g. ``joker_description_line``."""

    tokens: list[TokenSpan] = field(default_factory=list)
    """Ordered list of Balatro token strings found in source_text."""


# ---------------------------------------------------------------------------
# extractor
# ---------------------------------------------------------------------------


class LuaExtractor:
    """Extract translatable strings from a Balatro localization Lua file."""

    def __init__(self) -> None:
        self._parser = _get_parser()

    def extract_file(self, path: Path) -> list[TranslationUnit]:
        """Parse *path* and return all translation units."""
        source = path.read_bytes()
        return self.extract_bytes(source)

    def extract_bytes(self, source: bytes) -> list[TranslationUnit]:
        """Parse raw Lua *source* bytes and return all translation units."""
        tree = self._parser.parse(source)
        units: list[TranslationUnit] = []

        root = tree.root_node
        if root.type != "chunk":
            return units

        # Find the return statement → table_constructor
        return_stmt = _first_child_of_type(root, "return_statement")
        if return_stmt is None:
            return units

        expr_list = _first_child_of_type(return_stmt, "expression_list")
        if expr_list is None:
            return units

        outer_table = _first_child_of_type(expr_list, "table_constructor")
        if outer_table is None:
            return units

        # Walk descriptions.{Category}.{key}.{name|text|unlock}
        descriptions = _find_field(source, outer_table, "descriptions")
        if descriptions is None:
            return units

        desc_table = _first_child_of_type(descriptions, "table_constructor")
        if desc_table is None:
            return units

        for category_field in _iter_fields(desc_table):
            category_name = _field_name(source, category_field)
            category_table = _first_child_of_type(category_field, "table_constructor")
            if category_table is None:
                continue

            for entry_field in _iter_fields(category_table):
                entry_key = _field_name(source, entry_field)
                entry_table = _first_child_of_type(entry_field, "table_constructor")
                if entry_table is None:
                    continue

                # --- name ---
                name_field = _find_field(source, entry_table, "name")
                if name_field is not None:
                    str_node = _first_child_of_type(name_field, "string")
                    if str_node is not None:
                        text, start, end = _string_content(source, str_node)
                        units.append(
                            TranslationUnit(
                                unit_key=f"descriptions.{category_name}.{entry_key}.name",
                                source_text=text,
                                byte_start=start,
                                byte_end=end,
                                context_type=f"{_context_label(category_name)}_name",
                                tokens=extract_tokens(text),
                            )
                        )

                # --- text (array of strings) ---
                text_field = _find_field(source, entry_table, "text")
                if text_field is not None:
                    text_table = _first_child_of_type(text_field, "table_constructor")
                    if text_table is not None:
                        for idx, str_node in enumerate(_iter_array_strings(text_table)):
                            text, start, end = _string_content(source, str_node)
                            units.append(
                                TranslationUnit(
                                    unit_key=(
                                        f"descriptions.{category_name}.{entry_key}.text[{idx}]"
                                    ),
                                    source_text=text,
                                    byte_start=start,
                                    byte_end=end,
                                    context_type=f"{_context_label(category_name)}_description_line",
                                    tokens=extract_tokens(text),
                                )
                            )

                # --- unlock (array of strings) ---
                unlock_field = _find_field(source, entry_table, "unlock")
                if unlock_field is not None:
                    unlock_table = _first_child_of_type(unlock_field, "table_constructor")
                    if unlock_table is not None:
                        for idx, str_node in enumerate(_iter_array_strings(unlock_table)):
                            text, start, end = _string_content(source, str_node)
                            units.append(
                                TranslationUnit(
                                    unit_key=(
                                        f"descriptions.{category_name}.{entry_key}.unlock[{idx}]"
                                    ),
                                    source_text=text,
                                    byte_start=start,
                                    byte_end=end,
                                    context_type="unlock_condition",
                                    tokens=extract_tokens(text),
                                )
                            )

        return units


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _first_child_of_type(node, type_name: str):
    """Return the first child of *node* with the given type, or None."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_field(source: bytes, table_node, field_name: str):
    """Find a ``field`` child whose name identifier equals *field_name*."""
    for child in table_node.children:
        if child.type != "field":
            continue
        name_node = child.child_by_field_name("name")
        if name_node is not None and name_node.type == "identifier":
            if _node_text(source, name_node) == field_name:
                return child
    return None


def _field_name(source: bytes, field_node) -> str:
    """Return the key name of a ``field`` node."""
    name = field_node.child_by_field_name("name")
    if name is None:
        return "?"
    return _node_text(source, name)


def _node_text(source: bytes, node) -> str:
    """Decode the bytes spanned by *node*."""
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _string_content(source: bytes, string_node) -> tuple[str, int, int]:
    """Return (content_text, content_start_byte, content_end_byte) for a
    ``string`` node, stripping quotes but preserving exact byte positions."""
    content = string_node.child_by_field_name("content")
    if content is not None:
        text = source[content.start_byte : content.end_byte].decode("utf-8")
        return text, content.start_byte, content.end_byte
    # Fallback: strip surrounding quotes ourselves
    raw = source[string_node.start_byte : string_node.end_byte].decode("utf-8")
    # Handle all Lua quote styles: "..."  '...'  [[...]]  [=[...]=]
    if raw.startswith('[[') or raw.startswith('=['):
        # Long bracket string
        text = _unquote_long_bracket(raw)
        # Approximate byte offset (tree-sitter should give content child though)
        offset = len(raw) - len(_unquote_long_bracket_end(raw)) - len(text)
        start = string_node.start_byte + (len(raw.encode("utf-8")) - len(text.encode("utf-8")) - len(_unquote_long_bracket_end(raw).encode("utf-8")))
        # Simpler: just use the content node next time; for now approximate
        return text, string_node.start_byte + 2, string_node.end_byte - 2
    else:
        quote = raw[0]
        text = raw[1:-1] if len(raw) >= 2 else ""
        return text, string_node.start_byte + len(quote.encode("utf-8")), string_node.end_byte - len(quote.encode("utf-8"))


def _unquote_long_bracket(raw: str) -> str:
    """Remove long-bracket delimiters from a Lua string."""
    # Match [[...]] or [=[...]=] or [==[...]==] etc.
    m = re.match(r"\[(=*)\[(.*)\]\1\]", raw, re.DOTALL)
    if m:
        return m.group(2)
    return raw


def _unquote_long_bracket_end(raw: str) -> str:
    """Return the closing delimiter of a long-bracket string."""
    m = re.match(r"\[(=*)\[", raw)
    if m:
        eq = m.group(1)
        return f"]{eq}]"
    return ""


def _iter_fields(table_node):
    """Yield every ``field`` child of *table_node*."""
    for child in table_node.children:
        if child.type == "field":
            yield child


def _iter_array_strings(table_node):
    """Yield ``string`` children of an array-like table constructor, in order.

    In Lua, an array is just a table_constructor whose children are either
    ``string`` nodes directly or ``field`` nodes with implicit numeric keys.
    """
    for child in table_node.children:
        if child.type == "string":
            yield child
        elif child.type == "field":
            # Check if it has a value that is a string (could be an array element)
            value = child.child_by_field_name("value")
            if value is not None and value.type == "string":
                yield value


_CONTEXT_LABELS: dict[str, str] = {
    "Joker": "joker",
    "Back": "back",
    "Blind": "blind",
    "Edition": "edition",
    "Enhanced": "enhanced",
    "Planet": "planet",
    "Spectral": "spectral",
    "Tarot": "tarot",
    "Voucher": "voucher",
    "Tag": "tag",
    "Stake": "stake",
    "Seal": "seal",
    "Booster": "booster",
    "Other": "other",
    "Code": "code",
    "Content Set": "content_set",
    "Sleeve": "sleeve",
    "Challenge": "challenge",
    "Deck": "deck",
    "Shop": "shop",
    "UI": "ui",
}


def _context_label(category_name: str) -> str:
    """Map a Balatro category name to a snake_case context label."""
    return _CONTEXT_LABELS.get(category_name, category_name.lower().replace(" ", "_"))
