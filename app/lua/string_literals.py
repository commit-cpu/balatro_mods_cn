from __future__ import annotations

import re

_CJK_JOIN_SPACE_RE = re.compile(r"(?<=[\u3400-\u9fff]) (?=[\u3400-\u9fff])")


def normalize_lua_string_value(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in normalized:
        normalized = " ".join(part.strip() for part in normalized.split("\n"))
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized).strip()
    return _CJK_JOIN_SPACE_RE.sub("", normalized)


def escape_lua_string_content(value: str) -> str:
    normalized = normalize_lua_string_value(value)
    return (
        normalized.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
