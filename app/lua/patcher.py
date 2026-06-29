"""Lossless byte-level Lua patcher.

Replaces translation string content in-place using pre-computed byte offsets.
Patches are applied in *reverse offset order* so that earlier byte positions
remain valid after each replacement.

This guarantees that only the targeted string content changes; all other
bytes (comments, whitespace, punctuation, table structure, quotes, etc.)
are preserved exactly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PatchInstruction:
    """One string-replacement operation."""

    unit_key: str
    """Dotted key path for traceability."""

    byte_start: int
    """Byte offset of the *content* to replace (inside quotes)."""

    byte_end: int
    """Byte offset (exclusive) of the *content* to replace."""

    new_text: str
    """Replacement text (must be valid UTF-8, properly escaped for Lua)."""


class LuaPatcher:
    """Apply a batch of :class:`PatchInstruction` to Lua source bytes."""

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def patch(
        self,
        source: bytes,
        instructions: list[PatchInstruction],
    ) -> bytes:
        """Return *source* with every instruction applied.

        Instructions are sorted by descending ``byte_start`` internally so
        that replacements don't invalidate later offsets.
        """
        # Sort reverse by byte_start
        sorted_ins = sorted(instructions, key=lambda i: i.byte_start, reverse=True)
        result = source
        for ins in sorted_ins:
            result = self._apply_one(result, ins)
        return result

    def patch_file(
        self,
        path: str,
        instructions: list[PatchInstruction],
    ) -> None:
        """Read *path*, apply patches, and write back in-place."""
        source = open(path, "rb").read()
        patched = self.patch(source, instructions)
        open(path, "wb").write(patched)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_one(source: bytes, ins: PatchInstruction) -> bytes:
        """Apply a single instruction (caller must ensure offsets are valid)."""
        encoded = ins.new_text.encode("utf-8")
        return source[: ins.byte_start] + encoded + source[ins.byte_end :]


def build_patch_instructions(
    units: list,
    translations: dict[str, str],
) -> tuple[list[PatchInstruction], list[str]]:
    """Build patch instructions from translation units and a translation map.

    *units* should be a list of objects with ``unit_key``, ``byte_start``,
    ``byte_end`` attributes (e.g. :class:`app.lua.extractor.TranslationUnit`).

    *translations* maps ``unit_key`` → translated Chinese text.

    Returns ``(instructions, errors)``.  *errors* lists unit_keys that were
    in the translation map but had no matching unit (or vice versa).
    """
    unit_lookup: dict[str, tuple[int, int]] = {}
    unpatchable_keys: set[str] = set()
    for u in units:
        if u.byte_start < 0 or u.byte_end < 0:
            unpatchable_keys.add(u.unit_key)
            continue
        unit_lookup[u.unit_key] = (u.byte_start, u.byte_end)

    instructions: list[PatchInstruction] = []
    errors: list[str] = []

    translated_keys = set(translations.keys())
    unit_keys = set(unit_lookup.keys())

    # Keys in translations but not in units
    for key in sorted(translated_keys - unit_keys - unpatchable_keys):
        errors.append(f"Translation has no matching unit: {key}")

    # Keys in units but not in translations
    for key in sorted(unit_keys - translated_keys):
        errors.append(f"Unit has no translation: {key}")

    # Build instructions for matching keys
    for key in sorted(translated_keys & unit_keys):
        start, end = unit_lookup[key]
        instructions.append(
            PatchInstruction(
                unit_key=key,
                byte_start=start,
                byte_end=end,
                new_text=translations[key],
            )
        )

    return instructions, errors
