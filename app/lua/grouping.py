from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.lua.extractor import TranslationUnit


_ARRAY_KEY_RE = re.compile(r"^(?P<entry>.+)\.(?P<field>text|unlock)\[(?P<index>\d+)\]$")
_MISC_ARRAY_KEY_RE = re.compile(r"^(?P<entry>misc\.quips\..+)\[(?P<index>\d+)\]$")


@dataclass(frozen=True)
class TranslationEntry:
    entry_key: str
    name: TranslationUnit | None = None
    text: list[TranslationUnit] = field(default_factory=list)
    unlock: list[TranslationUnit] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        return " ".join(unit.source_text for unit in self.text)

    @property
    def combined_unlock(self) -> str:
        return " ".join(unit.source_text for unit in self.unlock)


def group_translation_units(units: list[TranslationUnit]) -> list[TranslationEntry]:
    builders: dict[str, dict] = {}
    order: list[str] = []

    for unit in units:
        entry_key, field_name, index = _split_unit_key(unit.unit_key)
        if entry_key not in builders:
            builders[entry_key] = {"name": None, "text": [], "unlock": []}
            order.append(entry_key)

        if field_name == "name":
            builders[entry_key]["name"] = unit
        elif field_name == "text":
            builders[entry_key]["text"].append((index, unit))
        elif field_name == "unlock":
            builders[entry_key]["unlock"].append((index, unit))

    groups: list[TranslationEntry] = []
    for entry_key in order:
        item = builders[entry_key]
        groups.append(
            TranslationEntry(
                entry_key=entry_key,
                name=item["name"],
                text=[unit for _, unit in sorted(item["text"], key=lambda pair: pair[0])],
                unlock=[unit for _, unit in sorted(item["unlock"], key=lambda pair: pair[0])],
            )
        )
    return groups


def _split_unit_key(unit_key: str) -> tuple[str, str, int]:
    if unit_key.endswith(".name"):
        return unit_key.removesuffix(".name"), "name", 0
    if unit_key.startswith(("misc.dictionary.", "misc.labels.")):
        return unit_key, "name", 0

    misc_match = _MISC_ARRAY_KEY_RE.match(unit_key)
    if misc_match is not None:
        return misc_match.group("entry"), "text", int(misc_match.group("index"))

    match = _ARRAY_KEY_RE.match(unit_key)
    if match is None:
        return unit_key, "unknown", 0
    return match.group("entry"), match.group("field"), int(match.group("index"))
