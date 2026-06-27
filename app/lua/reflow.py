from __future__ import annotations

import logging
import re
import unicodedata
import warnings

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)
import jieba  # noqa: E402


_TOKEN_RE = re.compile(r"\{[^}]*\}|#\d+#")
_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'’-]*")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_TRAILING_STYLE_TOKEN_RE = re.compile(r"(\{(?!\})[^}]*\})+$")
_NO_LINE_START = set("，。！？、；：）】》」』")
_BALATRO_WORDS = (
    "卡牌",
    "小丑牌",
    "人头牌",
    "计分牌",
    "扑克牌",
    "消耗牌",
    "补充包",
    "玻璃牌",
    "污渍玻璃牌",
    "黄金伙伴牌",
    "红牌伙伴",
    "魅惑卡牌",
    "分裂牌",
    "宝石牌",
    "不锈钢牌",
    "手牌上限",
    "出牌次数",
    "弃牌次数",
    "小丑槽",
    "小丑牌槽位",
    "盲注",
    "首个盲注",
    "负片",
    "倍率",
    "筹码",
    "金钱",
    "资金",
    "当前",
    "空位",
    "等级",
    "售价",
    "储备",
    "底注",
    "回合结束",
    "商店结束",
    "重新触发",
    "永久复制",
)

jieba.setLogLevel(logging.WARNING)
for _word in _BALATRO_WORDS:
    jieba.add_word(_word, freq=1_000_000)


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
        if _is_atomic_word(part):
            candidate = current + part
            if current and visual_width(candidate) > max_width:
                prefix, carry = _split_trailing_style_tokens(current)
                if carry:
                    if prefix:
                        lines.append(prefix)
                    current = carry + part
                else:
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
        parts.extend(_split_plain_text(token_part))
    return _merge_parenthetical_parts(_merge_styled_spans(parts))


def _split_plain_text(text: str) -> list[str]:
    parts: list[str] = []
    last = 0
    for match in _ASCII_WORD_RE.finditer(text):
        if match.start() > last:
            parts.extend(_segment_non_ascii(text[last : match.start()]))
        parts.append(match.group())
        last = match.end()
    if last < len(text):
        parts.extend(_segment_non_ascii(text[last:]))
    return parts


def _segment_non_ascii(text: str) -> list[str]:
    parts: list[str] = []
    last = 0
    for match in _CJK_RE.finditer(text):
        if match.start() > last:
            parts.extend(text[last : match.start()])
        parts.extend(word for word in jieba.cut(match.group(), HMM=False) if word)
        last = match.end()
    if last < len(text):
        parts.extend(text[last:])
    return parts


def _is_atomic_word(part: str) -> bool:
    return bool(_TOKEN_RE.search(part)) or bool(_ASCII_WORD_RE.fullmatch(part)) or (
        len(part) > 1 and bool(_CJK_RE.fullmatch(part))
    )


def _merge_styled_spans(parts: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if _is_opening_style_token(part):
            span = [part]
            index += 1
            while index < len(parts):
                span.append(parts[index])
                if parts[index] == "{}":
                    index += 1
                    break
                index += 1
            merged.append("".join(span))
            continue
        merged.append(part)
        index += 1
    return merged


def _merge_parenthetical_parts(parts: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part in {"（", "("}:
            closing = "）" if part == "（" else ")"
            group = [part]
            index += 1
            while index < len(parts):
                group.append(parts[index])
                if parts[index] == closing:
                    index += 1
                    if index < len(parts) and parts[index] == "{}":
                        group.append(parts[index])
                        index += 1
                    break
                index += 1
            merged.append("".join(group))
            continue
        merged.append(part)
        index += 1
    return merged


def _is_opening_style_token(part: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(part)) and part != "{}" and part.startswith("{")


def _split_trailing_style_tokens(text: str) -> tuple[str, str]:
    match = _TRAILING_STYLE_TOKEN_RE.search(text)
    if match is None:
        return text, ""
    return text[: match.start()], match.group(1)


def _token_width(token: str) -> int:
    if token == "{}" or token.startswith("{"):
        return 0
    if token.startswith("#") and token.endswith("#"):
        return 1
    return visual_width(token)


def _char_width(char: str) -> int:
    if char.isspace():
        return 1
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1
