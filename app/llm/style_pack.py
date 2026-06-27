from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.lua.extractor import LuaExtractor


DEFAULT_STYLE_PACK_PATH = Path("app/llm/assets/balatro_origin_style_pack.json")
STYLE_CATEGORY_FALLBACKS = {
    "sleeve": "back",
}


@dataclass(frozen=True, slots=True)
class StyleExample:
    category: str
    context_type: str
    unit_key: str
    source: str
    target: str
    source_mod_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "context_type": self.context_type,
            "unit_key": self.unit_key,
            "source": self.source,
            "target": self.target,
            "source_mod_id": self.source_mod_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StyleExample":
        return cls(
            category=str(raw["category"]),
            context_type=str(raw["context_type"]),
            unit_key=str(raw["unit_key"]),
            source=str(raw["source"]),
            target=str(raw["target"]),
            source_mod_id=str(raw.get("source_mod_id", "")),
        )


@dataclass(frozen=True, slots=True)
class StyleCategory:
    category: str
    available_count: int
    minimum_required: int
    examples: list[StyleExample]

    @property
    def minimum_met(self) -> bool:
        return self.available_count >= self.minimum_required

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "available_count": self.available_count,
            "minimum_required": self.minimum_required,
            "minimum_met": self.minimum_met,
            "examples": [example.to_dict() for example in self.examples],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StyleCategory":
        return cls(
            category=str(raw["category"]),
            available_count=int(raw["available_count"]),
            minimum_required=int(raw["minimum_required"]),
            examples=[
                StyleExample.from_dict(item)
                for item in raw.get("examples", [])
                if isinstance(item, dict)
            ],
        )


@dataclass(frozen=True, slots=True)
class StylePack:
    source_mod_id: str
    source_locale_path: str
    target_locale_path: str
    categories: dict[str, StyleCategory]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_mod_id": self.source_mod_id,
            "source_locale_path": self.source_locale_path,
            "target_locale_path": self.target_locale_path,
            "categories": {
                key: category.to_dict()
                for key, category in sorted(self.categories.items())
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StylePack":
        categories = raw.get("categories", {})
        return cls(
            source_mod_id=str(raw["source_mod_id"]),
            source_locale_path=str(raw["source_locale_path"]),
            target_locale_path=str(raw["target_locale_path"]),
            categories={
                str(key): StyleCategory.from_dict(value)
                for key, value in categories.items()
                if isinstance(value, dict)
            },
        )


def build_style_pack(
    *,
    repo: Path,
    source: str,
    target: str,
    min_per_category: int = 10,
    max_per_category: int = 1000,
    source_mod_id: str = "balatro_origin",
) -> StylePack:
    extractor = LuaExtractor()
    source_units = extractor.extract_file(repo / source)
    target_units = extractor.extract_file(repo / target)
    target_by_key = {unit.unit_key: unit for unit in target_units}
    grouped: dict[str, list[StyleExample]] = {}

    for unit in source_units:
        category = _description_category(unit.unit_key)
        if category is None:
            continue
        target_unit = target_by_key.get(unit.unit_key)
        if target_unit is None:
            continue
        if not unit.source_text.strip() or not target_unit.source_text.strip():
            continue
        if unit.source_text.strip().lower() == target_unit.source_text.strip().lower():
            continue
        grouped.setdefault(category, []).append(
            StyleExample(
                category=category,
                context_type=unit.context_type,
                unit_key=unit.unit_key,
                source=unit.source_text,
                target=target_unit.source_text,
                source_mod_id=source_mod_id,
            )
        )

    categories = {
        category: StyleCategory(
            category=category,
            available_count=len(examples),
            minimum_required=min_per_category,
            examples=sorted(examples, key=_example_priority)[:max_per_category],
        )
        for category, examples in sorted(grouped.items())
    }
    return StylePack(
        source_mod_id=source_mod_id,
        source_locale_path=source,
        target_locale_path=target,
        categories=categories,
    )


def save_style_pack(pack: StylePack, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_style_pack(path: Path = DEFAULT_STYLE_PACK_PATH) -> StylePack | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return StylePack.from_dict(raw)


def select_style_examples(
    pack: StylePack | None,
    *,
    entry_key: str,
    query_text: str = "",
    limit: int = 8,
    allow_fallback: bool = True,
) -> list[StyleExample]:
    if pack is None:
        return []
    category = _description_category(entry_key)
    if category is None:
        return []
    bucket = pack.categories.get(category)
    if bucket is None and allow_fallback:
        fallback = STYLE_CATEGORY_FALLBACKS.get(category)
        bucket = pack.categories.get(fallback) if fallback else None
    if bucket is None:
        return []
    if not query_text.strip():
        return bucket.examples[:limit]
    query_terms = _terms(query_text)
    groups: dict[str, list[StyleExample]] = {}
    for example in bucket.examples:
        groups.setdefault(_entry_key_prefix(example.unit_key), []).append(example)

    ranked_groups = sorted(
        groups.values(),
        key=lambda examples: (
            -max(len(query_terms & _terms(example.source)) for example in examples),
            min(_example_priority(example) for example in examples),
        ),
    )
    selected: list[StyleExample] = []
    for examples in ranked_groups:
        for example in sorted(examples, key=_example_priority):
            selected.append(example)
            if len(selected) >= limit:
                return selected
    return selected


def select_tm_style_examples(
    db_path: Path,
    *,
    entry_key: str,
    query_text: str = "",
    limit: int = 4,
) -> list[StyleExample]:
    category = _description_category(entry_key)
    if category is None or limit <= 0:
        return []
    context_types = _category_context_types(category)
    placeholders = ",".join("?" for _ in context_types)
    with connect(db_path) as db:
        try:
            rows = db.execute(
                f"""
                select mod_id, unit_key, context_type, source_text, target_text
                from tm_entries
                where context_type in ({placeholders})
                  and source_text != ''
                  and target_text != ''
                  and lower(source_text) != lower(target_text)
                order by
                  case when quality = 'imported_human' then 0 else 1 end,
                  mod_id,
                  id
                """,
                tuple(context_types),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    examples = [
        StyleExample(
            category=category,
            context_type=row["context_type"],
            unit_key=row["unit_key"],
            source=row["source_text"],
            target=row["target_text"],
            source_mod_id=row["mod_id"],
        )
        for row in rows
    ]
    return _rank_style_examples(examples, query_text=query_text, limit=limit)


def render_style_examples(examples: list[StyleExample]) -> str:
    if not examples:
        return "(none)"
    lines = [
        "Balatro Simplified Chinese style references:",
        "Use these to match concise in-game wording, sentence order, and line rhythm; locked glossary remains authoritative for terms.",
    ]
    for example in examples:
        source_label = (
            f"{example.source_mod_id}:{example.unit_key}"
            if example.source_mod_id
            else example.unit_key
        )
        lines.append(
            f"- {source_label}\n"
            f"  EN: {example.source}\n"
            f"  ZH: {example.target}"
        )
    return "\n".join(lines)


def _description_category(unit_key: str) -> str | None:
    parts = unit_key.split(".")
    if len(parts) < 3 or parts[0] != "descriptions":
        return None
    return parts[1].lower().replace(" ", "_").replace('"', "")


def _entry_key_prefix(unit_key: str) -> str:
    return re.sub(r"\.(?:name|text\[\d+\]|unlock\[\d+\])$", "", unit_key)


def _category_context_types(category: str) -> list[str]:
    return [
        f"{category}_description_line",
        f"{category}_name",
        "unlock_condition",
    ]


def _rank_style_examples(
    examples: list[StyleExample],
    *,
    query_text: str,
    limit: int,
) -> list[StyleExample]:
    if not query_text.strip():
        return sorted(examples, key=_example_priority)[:limit]
    query_terms = _terms(query_text)
    groups: dict[str, list[StyleExample]] = {}
    for example in examples:
        groups.setdefault(_entry_key_prefix(example.unit_key), []).append(example)

    ranked_groups = sorted(
        groups.values(),
        key=lambda group: (
            -max(len(query_terms & _terms(example.source)) for example in group),
            min(_example_priority(example) for example in group),
        ),
    )
    selected: list[StyleExample] = []
    for group in ranked_groups:
        for example in sorted(group, key=_example_priority):
            selected.append(example)
            if len(selected) >= limit:
                return selected
    return selected


def _example_priority(example: StyleExample) -> tuple[int, str]:
    if example.context_type.endswith("_description_line"):
        return (0, example.unit_key)
    if example.context_type == "unlock_condition":
        return (1, example.unit_key)
    if example.context_type.endswith("_name"):
        return (2, example.unit_key)
    return (3, example.unit_key)


def _terms(text: str) -> set[str]:
    text = re.sub(r"\{[^}]*\}", " ", text)
    return {
        _normalize_term(term.lower())
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_'-]*", text)
        if len(term) >= 3
    }


def _normalize_term(term: str) -> str:
    if len(term) > 4 and term.endswith("s"):
        return term[:-1]
    return term
