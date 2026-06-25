"""Balatro Lua token patterns: detect, extract, normalize, protect, restore.

Token types found in Balatro localization strings:

    Style / color:
        {C:mult} {C:attention} {C:chips} {C:money} {C:blue} {C:red} ...
        {C:legendary,E:1} {C:inactive,E:1}  -- combined modifiers
        {X:mult,C:white}                     -- X multiplier + color

    Reset:
        {}

    Variable substitution:
        #1# #2# #3# ...

    Scale / misc:
        {s:0.85}

    Tag reference:
        {T:tag_double}

    Voucher reference:
        {T:v_crystal_ball}

    Card references:
        {T:c_hex} {T:c_fool}

    Escape sequences:
        \\n  \\\"  \\\\
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import ClassVar

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches any brace-enclosed Balatro token: {C:mult}, {X:mult,C:white}, {}, {s:0.85}, {T:c_hex}, etc.
_RE_BRACE_TOKEN = re.compile(r"\{[^}]*\}")

# Matches variable substitution placeholders: #1#, #2#, #10#, etc.
_RE_VAR_TOKEN = re.compile(r"#\d+#")

# Combined: matches all protectable tokens in a string
_RE_ALL_TOKENS = re.compile(r"\{[^}]*\}|#\d+#")

# Escape sequences that must survive round-trip
_RE_ESCAPES = re.compile(r"\\[n\"\\]")


# ---------------------------------------------------------------------------
# data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """A single token occurrence in a source string."""

    raw: str
    """The original token text, e.g. ``{C:mult}`` or ``#1#``."""

    start: int
    """Character offset in the original string."""

    end: int
    """Character offset (exclusive) in the original string."""

    placeholder: str
    """Synthetic placeholder for LLM prompts, e.g. ``[[TOKEN_0]]``."""


@dataclass(slots=True)
class TokenizedString:
    """Result of tokenizing a Balatro localization string."""

    source: str
    """The original raw string (with tokens)."""

    tokens: list[TokenSpan]
    """All tokens found, in order of appearance."""

    # Derived representations --------------------------------------------------

    normalized: str
    """Source with tokens replaced by semantic tags, for RAG embedding.

    ``{C:mult}+#1#{} Mult`` → ``<style_mult>+<var_1><style_reset> Mult``
    """

    prompt_safe: str
    """Source with tokens replaced by numbered placeholders, for LLM prompts.

    ``{C:mult}+#1#{} Mult`` → ``[[TOKEN_0]]+[[TOKEN_1]][[TOKEN_2]] Mult``
    """

    token_signature: str
    """Pipe-delimited semantic token types for RAG filter scoring.

    ``style_mult|var_1|style_reset``
    """

    # ------------------------------------------------------------------
    # factory
    # ------------------------------------------------------------------

    @classmethod
    def from_string(cls, text: str) -> TokenizedString:
        """Parse *text* and produce all derived representations."""
        tokens = _extract_tokens(text)
        normalized = _build_normalized(text, tokens)
        prompt_safe = _build_prompt_safe(text, tokens)
        signature = _build_signature(tokens)
        return cls(
            source=text,
            tokens=tokens,
            normalized=normalized,
            prompt_safe=prompt_safe,
            token_signature=signature,
        )


# ---------------------------------------------------------------------------
# public helpers
# ---------------------------------------------------------------------------


def extract_tokens(text: str) -> list[TokenSpan]:
    """Return every protectable token in *text*, in order."""
    return _extract_tokens(text)


def normalize_for_rag(text: str) -> str:
    """Replace tokens with semantic tags suitable for embedding/search.

    >>> normalize_for_rag('{C:mult}+#1#{} Mult')
    '<style_mult>+<var_1><style_reset> Mult'
    """
    return _build_normalized(text, _extract_tokens(text))


def protect_for_llm(text: str) -> tuple[str, list[str]]:
    """Replace tokens with numbered placeholders.

    Returns ``(prompt_safe_text, token_list)`` where *token_list* is ordered
    and can be used by :func:`restore_tokens` to put original tokens back.
    """
    tokens = _extract_tokens(text)
    return _build_prompt_safe(text, tokens), [t.raw for t in tokens]


def restore_tokens(
    llm_output: str,
    original_tokens: list[str],
    *,
    allow_reorder: bool = False,
) -> str:
    """Replace ``[[TOKEN_n]]`` placeholders with the original token text.

    Raises :class:`TokenMismatchError` if the count or order differs.
    """
    # Find all [[TOKEN_n]] in output
    placeholder_pattern = re.compile(r"\[\[TOKEN_(\d+)\]\]")
    found: list[tuple[int, int, int]] = []  # (index, start, end)
    for m in placeholder_pattern.finditer(llm_output):
        found.append((int(m.group(1)), m.start(), m.end()))

    if len(found) != len(original_tokens):
        raise TokenMismatchError(
            f"Token count mismatch: LLM returned {len(found)} placeholders, "
            f"expected {len(original_tokens)}"
        )

    found_order = [idx for idx, _, _ in found]
    expected_order = list(range(len(original_tokens)))
    if allow_reorder:
        if sorted(found_order) != expected_order:
            raise TokenMismatchError(
                f"Token identity mismatch: LLM returned {found_order}, "
                f"expected one each of {expected_order}"
            )
    elif found_order != expected_order:
        raise TokenMismatchError(
            f"Token order mismatch: LLM returned {found_order}, expected {expected_order}"
        )

    # Replace in reverse order to preserve offsets
    result = llm_output
    for idx, start, end in reversed(found):
        if idx >= len(original_tokens):
            raise TokenMismatchError(
                f"Placeholder [[TOKEN_{idx}]] out of range "
                f"(expected 0..{len(original_tokens) - 1})"
            )
        result = result[:start] + original_tokens[idx] + result[end:]

    return result


def validate_token_identity(
    original: str,
    translated: str,
    *,
    order_sensitive: bool = True,
) -> list[str]:
    """Check that *translated* contains exactly the same tokens as *original*.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    orig_tokens = _extract_tokens(original)
    trans_tokens = _extract_tokens(translated)

    orig_raws = [t.raw for t in orig_tokens]
    trans_raws = [t.raw for t in trans_tokens]

    if len(orig_raws) != len(trans_raws):
        errors.append(
            f"Token count mismatch: original={len(orig_raws)}, translated={len(trans_raws)}"
        )

    if order_sensitive:
        for i, (o, t) in enumerate(zip(orig_raws, trans_raws)):
            if o != t:
                errors.append(
                    f"Token [{i}] mismatch: expected {o!r}, got {t!r}"
                )
    elif Counter(orig_raws) != Counter(trans_raws):
        errors.append(
            f"Token inventory mismatch: original={orig_raws!r}, translated={trans_raws!r}"
        )

    # Also check for any remaining unmatched tokens
    if len(orig_raws) > len(trans_raws):
        for o in orig_raws[len(trans_raws):]:
            errors.append(f"Missing token: {o!r}")
    elif len(trans_raws) > len(orig_raws):
        for t in trans_raws[len(orig_raws):]:
            errors.append(f"Extra token: {t!r}")

    return errors


def has_any_token(text: str) -> bool:
    """Return True if *text* contains any Balatro token."""
    return bool(_RE_ALL_TOKENS.search(text))


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------


class TokenMismatchError(ValueError):
    """Raised when LLM output does not preserve the expected token sequence."""


# ---------------------------------------------------------------------------
# internal
# ---------------------------------------------------------------------------

# Mapping from raw token to semantic tag fragment (for normalized form)
_STYLE_PREFIXES: ClassVar[set[str]] = {"c", "x"}
_VAR_PATTERN = re.compile(r"^#\d+#$")


def _token_semantic_tag(raw: str) -> str:
    """Map a raw token to a semantic tag for normalized / signature form."""
    raw = raw.strip()

    if raw == "{}":
        return "style_reset"

    if _VAR_PATTERN.match(raw):
        # #1# → var_1
        num = raw.strip("#")
        return f"var_{num}"

    # {C:mult} → style_mult, {X:mult,C:white} → style_mult,style_white
    if raw.startswith("{") and raw.endswith("}"):
        inner = raw[1:-1]
        parts: list[str] = []
        for segment in inner.split(","):
            segment = segment.strip()
            if ":" in segment:
                prefix, value = segment.split(":", 1)
                prefix_lower = prefix.lower()
                if prefix_lower in _STYLE_PREFIXES:
                    parts.append(f"style_{value}")
                elif prefix_lower == "s":
                    parts.append(f"scale_{value}")
                elif prefix_lower == "t":
                    parts.append(f"tag_{value}")
                elif prefix_lower == "e":
                    parts.append(f"edition_{value}")
                elif prefix_lower == "v":
                    parts.append(f"voucher_{value}")
                else:
                    parts.append(f"{prefix_lower}_{value}")
            else:
                parts.append(segment)
        return ",".join(parts)

    # Fallback: return as-is but lowercase
    return raw.lower()


def _extract_tokens(text: str) -> list[TokenSpan]:
    """Find all tokens in *text* and return ordered TokenSpans."""
    tokens: list[TokenSpan] = []
    for m in _RE_ALL_TOKENS.finditer(text):
        raw = m.group()
        idx = len(tokens)
        tokens.append(
            TokenSpan(
                raw=raw,
                start=m.start(),
                end=m.end(),
                placeholder=f"[[TOKEN_{idx}]]",
            )
        )
    return tokens


def _build_normalized(text: str, tokens: list[TokenSpan]) -> str:
    """Replace tokens with semantic tags, lowercased."""
    result = text
    # Replace from end to start to preserve offsets
    for t in reversed(tokens):
        tag = f"<{_token_semantic_tag(t.raw)}>"
        result = result[:t.start] + tag + result[t.end:]
    return result.lower()


def _build_prompt_safe(text: str, tokens: list[TokenSpan]) -> str:
    """Replace tokens with [[TOKEN_n]] placeholders."""
    result = text
    for t in reversed(tokens):
        result = result[:t.start] + t.placeholder + result[t.end:]
    return result


def _build_signature(tokens: list[TokenSpan]) -> str:
    """Build a pipe-delimited semantic signature for RAG filtering."""
    return "|".join(_token_semantic_tag(t.raw) for t in tokens)
