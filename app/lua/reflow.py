from __future__ import annotations

import re
import unicodedata


_TOKEN_RE = re.compile(r"\{[^}]*\}|#\d+#")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'’-]*")
_NO_LINE_START = set("，。！？、；：）】》」』")


def visual_width(text: str) -> int:
    width = 0
    for part in _split_tokens(text):
        if _TOKEN_RE.fullmatch(part):
            width += _token_width(part)
        else:
            width += sum(_char_width(char) for char in part)
    return width


def reflow_zh_text(text: str, *, max_width: int) -> list[str]:
    if not text:
        return []

    parts = _split_reflow_parts(text)
    lines: list[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        if _TOKEN_RE.fullmatch(part):
            current += part
            continue
        if _ASCII_WORD_RE.fullmatch(part):
            candidate = current + part
            if current and visual_width(candidate) > max_width:
                lines.append(current)
                current = part
            else:
                current = candidate
            continue

        for char in part:
            candidate = current + char
            if current and visual_width(candidate) > max_width:
                lines.append(current)
                current = char
                if lines and current in _NO_LINE_START:
                    lines[-1] += current
                    current = ""
            else:
                current = candidate

    if current:
        lines.append(current)
    return lines


def _split_tokens(text: str) -> list[str]:
    parts: list[str] = []
    last = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() > last:
            parts.append(text[last : match.start()])
        parts.append(match.group())
        last = match.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


def _split_reflow_parts(text: str) -> list[str]:
    parts: list[str] = []
    for token_part in _split_tokens(text):
        if _TOKEN_RE.fullmatch(token_part):
            parts.append(token_part)
            continue
        last = 0
        for match in _ASCII_WORD_RE.finditer(token_part):
            if match.start() > last:
                parts.append(token_part[last : match.start()])
            parts.append(match.group())
            last = match.end()
        if last < len(token_part):
            parts.append(token_part[last:])
    return parts


def _token_width(token: str) -> int:
    if token == "{}" or token.startswith("{"):
        return 0
    if token.startswith("#") and token.endswith("#"):
        return 3
    return visual_width(token)


def _char_width(char: str) -> int:
    if char.isspace():
        return 1
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1
