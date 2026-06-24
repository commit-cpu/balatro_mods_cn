"""LuaJIT compilation validation.

Uses the system ``luajit`` binary to verify that a Lua file is syntactically
valid after patching.  This is the final safety gate before publishing.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def validate_file(path: Path | str, *, timeout: float = 30.0) -> tuple[bool, str]:
    """Check whether *path* is valid Lua syntax using ``luajit -bl``.

    Returns ``(is_valid, error_message)``.  *error_message* is empty on
    success; on failure it contains the stderr output from luajit.
    """
    result = subprocess.run(
        ["luajit", "-bl", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode == 0:
        return True, ""

    error = result.stderr.strip() if result.stderr else f"luajit exit code {result.returncode}"
    logger.warning("LuaJIT validation failed for %s: %s", path, error)
    return False, error


def validate_string(lua_code: str, *, timeout: float = 30.0) -> tuple[bool, str]:
    """Check whether *lua_code* is valid by piping it to ``luajit``.

    Returns ``(is_valid, error_message)``.
    """
    result = subprocess.run(
        ["luajit", "-bl", "-e", lua_code],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode == 0:
        return True, ""

    error = result.stderr.strip() if result.stderr else f"luajit exit code {result.returncode}"
    return False, error


def luajit_available() -> bool:
    """Return ``True`` if ``luajit`` is on PATH and executable."""
    try:
        result = subprocess.run(
            ["luajit", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# validation pipeline helpers
# ---------------------------------------------------------------------------


class LuaValidationError(ValueError):
    """Raised when a patched Lua file fails validation."""


def validate_or_raise(path: Path | str, *, timeout: float = 30.0) -> None:
    """Like :func:`validate_file` but raises :class:`LuaValidationError` on
    failure."""
    ok, err = validate_file(path, timeout=timeout)
    if not ok:
        raise LuaValidationError(f"Lua validation failed for {path}: {err}")


def diff_is_translation_only(
    original: bytes,
    patched: bytes,
    units: list,
) -> tuple[bool, str]:
    """Verify that *patched* differs from *original* only in expected string
    content spans.

    Returns ``(is_clean, message)``.  If any byte outside the union of all
    unit ``(byte_start, byte_end)`` spans has changed, the result is
    ``(False, explanation)``.
    """
    # Build sorted list of translation spans from the *original* file.
    # We'll compare non-translation regions sequentially, accounting for
    # cumulative size drift from multi-byte UTF-8 replacements.
    spans = sorted(
        [(u.byte_start, u.byte_end) for u in units],
        key=lambda s: s[0],
    )

    # Walk through both files comparing non-translation regions.
    # orig_pos / pat_pos track current read positions.
    orig_pos = 0
    pat_pos = 0
    diffs: list[str] = []
    span_idx = 0

    while orig_pos < len(original) and pat_pos < len(patched):
        # Find the next translation span that starts at or after orig_pos
        while span_idx < len(spans) and spans[span_idx][0] < orig_pos:
            span_idx += 1

        if span_idx < len(spans):
            span_start, span_end = spans[span_idx]
        else:
            span_start = len(original)
            span_end = len(original)

        # Non-translation region: [orig_pos, span_start)
        non_trans_len = span_start - orig_pos
        if non_trans_len > 0:
            # Compare this region in both files
            orig_chunk = original[orig_pos:span_start]
            pat_chunk = patched[pat_pos : pat_pos + non_trans_len]
            if orig_chunk != pat_chunk:
                for j in range(min(len(orig_chunk), len(pat_chunk))):
                    if orig_chunk[j] != pat_chunk[j]:
                        diffs.append(
                            f"Byte {orig_pos + j}: expected {orig_chunk[j]!r} "
                            f"but got {pat_chunk[j]!r} "
                            f"(context: {orig_chunk[max(0,j-5):j+5]!r} → "
                            f"{pat_chunk[max(0,j-5):j+5]!r})"
                        )
                        break
                if len(diffs) >= 5:
                    break
            orig_pos += non_trans_len
            pat_pos += non_trans_len

        # Skip the translation span in both files
        if span_idx < len(spans):
            orig_pos = span_end
            # The patched file's translation span ends at pat_pos + len(new_text).
            # We don't know the new length directly, so advance pat_pos to the
            # next non-translation byte by searching for the byte that follows
            # the translation in the original.
            if span_end < len(original):
                # Find the byte in patched that matches original[span_end]
                # by scanning forward from pat_pos
                next_byte = original[span_end : span_end + 1]
                # Search forward in patched for this byte
                search_start = pat_pos
                # We need at least the translation's minimum length (empty string = 0)
                # Scan for the synchronization byte
                found = False
                for scan in range(search_start, min(search_start + 5000, len(patched))):
                    if patched[scan : scan + 1] == next_byte:
                        pat_pos = scan
                        found = True
                        break
                if not found:
                    diffs.append(
                        f"Lost synchronization at orig byte {span_end}: "
                        f"cannot find {next_byte!r} in patched file"
                    )
                    break
            else:
                # Translation was at end of file
                pat_pos = len(patched)
            span_idx += 1

    # Check trailing non-translation bytes
    if orig_pos < len(original) and pat_pos < len(patched):
        orig_tail = original[orig_pos:]
        pat_tail = patched[pat_pos:]
        if orig_tail != pat_tail:
            diffs.append(
                f"Trailing bytes differ: {orig_tail[:20]!r} → {pat_tail[:20]!r}"
            )
    elif orig_pos < len(original):
        diffs.append(f"Original has {len(original) - orig_pos} extra trailing bytes")
    elif pat_pos < len(patched):
        diffs.append(f"Patched has {len(patched) - pat_pos} extra trailing bytes")

    if diffs:
        return False, "Unauthorised byte changes detected:\n" + "\n".join(diffs)

    return True, ""
