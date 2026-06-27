from __future__ import annotations

from dataclasses import dataclass

from app.lua.tokens import (
    TokenMismatchError,
    extract_tokens,
    protect_for_llm,
    restore_tokens,
    validate_token_identity,
)
from app.lua.reflow import reflow_zh_text


@dataclass(frozen=True)
class TranslationReference:
    source_text: str
    target_text: str
    score: float
    tier: str = "loose"
    """Reference tier: ``locked`` (glossary hit), ``same_context`` (dense hit
    sharing the entry's context_type), or ``loose`` (everything else)."""


@dataclass(frozen=True)
class TranslationResult:
    candidate_text: str
    token_errors: list[str]


@dataclass(frozen=True)
class EntryTranslationResult:
    name: str | None
    text: list[str]
    unlock: list[str]
    token_errors: list[str]


@dataclass(frozen=True)
class EntryQualityReview:
    needs_revision: bool
    naturalness_warnings: list[str]
    meaning_warnings: list[str]
    rewrite_hint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "needs_revision": self.needs_revision,
            "naturalness_warnings": self.naturalness_warnings,
            "meaning_warnings": self.meaning_warnings,
            "rewrite_hint": self.rewrite_hint,
        }


class Translator:
    def __init__(self, *, client, model: str) -> None:
        self._client = client
        self._model = model

    def translate(
        self,
        *,
        source_text: str,
        references: list[TranslationReference],
    ) -> TranslationResult:
        safe_source, raw_tokens = protect_for_llm(source_text)
        response = self._client.chat_json(
            _build_messages(
                model=self._model,
                safe_source=safe_source,
                references=references,
            )
        )
        raw_translation = response.get("translation")
        if not isinstance(raw_translation, str):
            raw_translation = ""

        try:
            candidate = restore_tokens(raw_translation, raw_tokens)
            token_errors = validate_token_identity(source_text, candidate)
        except TokenMismatchError as exc:
            candidate = raw_translation
            token_errors = [str(exc)]

        return TranslationResult(candidate_text=candidate, token_errors=token_errors)

    def translate_entry(
        self,
        *,
        name_text: str | None,
        body_text: str,
        unlock_text: str,
        references: list[TranslationReference],
        max_width: int,
        style_examples: str = "",
    ) -> EntryTranslationResult:
        safe_name, name_tokens = protect_for_llm(name_text or "")
        safe_body, body_tokens = protect_for_llm(body_text)
        safe_unlock, unlock_tokens = protect_for_llm(unlock_text)
        response = self._client.chat_json(
            _build_entry_messages(
                model=self._model,
                safe_name=safe_name,
                safe_body=safe_body,
                safe_unlock=safe_unlock,
                references=references,
                style_examples=style_examples,
            )
        )

        token_errors: list[str] = []
        name = None
        if name_text is not None:
            name, errors = _restore_and_validate(
                source=name_text,
                raw_translation=response.get("name"),
                original_tokens=name_tokens,
                allow_reorder=True,
            )
            token_errors.extend(f"name: {error}" for error in errors)
            if errors:
                name = None

        body, errors = _restore_and_validate(
            source=body_text,
            raw_translation=response.get("text"),
            original_tokens=body_tokens,
            allow_reorder=True,
        )
        body_errors = errors
        token_errors.extend(f"text: {error}" for error in errors)

        unlock = ""
        unlock_errors: list[str] = []
        if unlock_text:
            unlock, errors = _restore_and_validate(
                source=unlock_text,
                raw_translation=response.get("unlock"),
                original_tokens=unlock_tokens,
                allow_reorder=True,
            )
            unlock_errors = errors
            token_errors.extend(f"unlock: {error}" for error in errors)

        return EntryTranslationResult(
            name=name,
            text=reflow_zh_text(body, max_width=max_width)
            if body and not body_errors
            else [],
            unlock=reflow_zh_text(unlock, max_width=max_width)
            if unlock and not unlock_errors
            else [],
            token_errors=token_errors,
        )

    def review_entry_translation(
        self,
        *,
        name_text: str | None,
        body_text: str,
        unlock_text: str,
        name: str | None,
        text: list[str],
        unlock: list[str],
        references: list[TranslationReference],
        style_examples: str = "",
    ) -> EntryQualityReview:
        response = self._client.chat_json(
            _build_entry_review_messages(
                model=self._model,
                name_text=name_text or "",
                body_text=body_text,
                unlock_text=unlock_text,
                name=name or "",
                text="".join(text),
                unlock="".join(unlock),
                references=references,
                style_examples=style_examples,
            )
        )
        return _parse_quality_review(response)

    def revise_entry_translation(
        self,
        *,
        name_text: str | None,
        body_text: str,
        unlock_text: str,
        current_name: str | None,
        current_text: list[str],
        current_unlock: list[str],
        review_feedback: str,
        references: list[TranslationReference],
        max_width: int,
        style_examples: str = "",
    ) -> EntryTranslationResult:
        safe_name, name_tokens = protect_for_llm(name_text or "")
        safe_body, body_tokens = protect_for_llm(body_text)
        safe_unlock, unlock_tokens = protect_for_llm(unlock_text)
        safe_current_name = _protect_existing_tokens(current_name or "", name_tokens)
        safe_current_text = _protect_existing_tokens("".join(current_text), body_tokens)
        safe_current_unlock = _protect_existing_tokens(
            "".join(current_unlock), unlock_tokens
        )
        response = self._client.chat_json(
            _build_entry_revision_messages(
                model=self._model,
                safe_name=safe_name,
                safe_body=safe_body,
                safe_unlock=safe_unlock,
                current_name=safe_current_name,
                current_text=safe_current_text,
                current_unlock=safe_current_unlock,
                review_feedback=review_feedback,
                references=references,
                style_examples=style_examples,
            )
        )

        token_errors: list[str] = []
        name = None
        if name_text is not None:
            name, errors = _restore_and_validate(
                source=name_text,
                raw_translation=response.get("name"),
                original_tokens=name_tokens,
                allow_reorder=True,
            )
            token_errors.extend(f"name: {error}" for error in errors)
            if errors:
                name = None

        body, errors = _restore_and_validate(
            source=body_text,
            raw_translation=response.get("text"),
            original_tokens=body_tokens,
            allow_reorder=True,
        )
        body_errors = errors
        token_errors.extend(f"text: {error}" for error in errors)

        unlock = ""
        unlock_errors: list[str] = []
        if unlock_text:
            unlock, errors = _restore_and_validate(
                source=unlock_text,
                raw_translation=response.get("unlock"),
                original_tokens=unlock_tokens,
                allow_reorder=True,
            )
            unlock_errors = errors
            token_errors.extend(f"unlock: {error}" for error in errors)

        return EntryTranslationResult(
            name=name,
            text=reflow_zh_text(body, max_width=max_width)
            if body and not body_errors
            else [],
            unlock=reflow_zh_text(unlock, max_width=max_width)
            if unlock and not unlock_errors
            else [],
            token_errors=token_errors,
        )


def _render_references(references: list[TranslationReference]) -> str:
    """Render references grouped by tier: locked glossary, same-context, loose.

    Empty tiers are omitted. Returns ``(none)`` when there are no references.
    """
    tiers: list[tuple[str, str]] = [
        ("locked", "Locked glossary"),
        ("same_context", "Same-context references"),
        ("loose", "Loose references"),
    ]
    blocks: list[str] = []
    for tier_key, label in tiers:
        tier_refs = [ref for ref in references if ref.tier == tier_key]
        if not tier_refs:
            continue
        body = "\n".join(
            f"- score={ref.score:.4f}\n  EN: {ref.source_text}\n  ZH: {ref.target_text}"
            for ref in tier_refs
        )
        blocks.append(f"{label}:\n{body}")
    return "\n\n".join(blocks) if blocks else "(none)"


def _build_messages(
    *,
    model: str,
    safe_source: str,
    references: list[TranslationReference],
) -> list[dict[str, str]]:
    refs = _render_references(references)
    return [
        {
            "role": "system",
            "content": (
                "You translate Balatro mod localization strings into Simplified Chinese. "
                "Preserve every placeholder exactly, including [[TOKEN_n]] markers. "
                "Locked glossary entries are authoritative term mappings; follow them. "
                "Return JSON only with key translation."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Model hint: {model}\n"
                f"Source string:\n{safe_source}\n\n"
                f"Translation memory references:\n{refs}\n\n"
                "Return: {\"translation\":\"...\"}"
            ),
        },
    ]


def _build_entry_messages(
    *,
    model: str,
    safe_name: str,
    safe_body: str,
    safe_unlock: str,
    references: list[TranslationReference],
    style_examples: str = "",
) -> list[dict[str, str]]:
    refs = _render_references(references)
    style = style_examples or "(none)"
    return [
        {
            "role": "system",
            "content": (
                "You translate Balatro mod localization entries into Simplified Chinese. "
                "Translate the complete description as one coherent entry, not line by line. "
                "Preserve every [[TOKEN_n]] placeholder exactly. "
                "Do not translate names after labels like Idea:, Art:, Code:, or Concept:. "
                "Locked glossary entries are authoritative term mappings; follow them. "
                "Return JSON only with keys name, text, unlock. The text and unlock values "
                "must be complete unwrapped Chinese strings, not arrays."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Model hint: {model}\n"
                f"Name:\n{safe_name or '(none)'}\n\n"
                f"Description combined from text[]:\n{safe_body or '(none)'}\n\n"
                f"Unlock combined from unlock[]:\n{safe_unlock or '(none)'}\n\n"
                f"Balatro Simplified Chinese style references:\n{style}\n\n"
                f"Translation memory references:\n{refs}\n\n"
                "Return: {\"name\":\"...\",\"text\":\"...\",\"unlock\":\"...\"}"
            ),
        },
    ]


def _build_entry_review_messages(
    *,
    model: str,
    name_text: str,
    body_text: str,
    unlock_text: str,
    name: str,
    text: str,
    unlock: str,
    references: list[TranslationReference],
    style_examples: str = "",
) -> list[dict[str, str]]:
    refs = _render_references(references)
    style = style_examples or "(none)"
    return [
        {
            "role": "system",
            "content": (
                "You review Simplified Chinese Balatro mod translations. "
                "Focus only on natural Chinese word order, mechanical English structure, "
                "and obvious meaning drift. Do not nitpick wording that is already natural. "
                "Return JSON only with keys needs_revision, naturalness_warnings, "
                "meaning_warnings, rewrite_hint."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Model hint: {model}\n"
                f"Source name:\n{name_text or '(none)'}\n\n"
                f"Source description:\n{body_text or '(none)'}\n\n"
                f"Source unlock:\n{unlock_text or '(none)'}\n\n"
                f"Candidate name:\n{name or '(none)'}\n\n"
                f"Candidate description:\n{text or '(none)'}\n\n"
                f"Candidate unlock:\n{unlock or '(none)'}\n\n"
                f"Balatro Simplified Chinese style references:\n{style}\n\n"
                f"Translation memory references:\n{refs}\n\n"
                "If the candidate sounds like literal English structure, set "
                "needs_revision=true and give a concise rewrite_hint. "
                "Return: {\"needs_revision\":false,\"naturalness_warnings\":[],"
                "\"meaning_warnings\":[],\"rewrite_hint\":\"\"}"
            ),
        },
    ]


def _build_entry_revision_messages(
    *,
    model: str,
    safe_name: str,
    safe_body: str,
    safe_unlock: str,
    current_name: str,
    current_text: str,
    current_unlock: str,
    review_feedback: str,
    references: list[TranslationReference],
    style_examples: str = "",
) -> list[dict[str, str]]:
    refs = _render_references(references)
    style = style_examples or "(none)"
    return [
        {
            "role": "system",
            "content": (
                "You revise Simplified Chinese Balatro mod localization entries. "
                "Fix only the reviewer feedback. Preserve every [[TOKEN_n]] placeholder exactly. "
                "Do not copy raw Balatro tokens like {C:attention}; use the provided "
                "[[TOKEN_n]] placeholders only. "
                "Keep credit lines such as Idea:, Art:, Code:, or Concept: untranslated. "
                "Return JSON only with keys name, text, unlock. The text and unlock values "
                "must be complete unwrapped Chinese strings, not arrays."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Model hint: {model}\n"
                f"Source name:\n{safe_name or '(none)'}\n\n"
                f"Source description:\n{safe_body or '(none)'}\n\n"
                f"Source unlock:\n{safe_unlock or '(none)'}\n\n"
                f"Current name:\n{current_name or '(none)'}\n\n"
                f"Current description:\n{current_text or '(none)'}\n\n"
                f"Current unlock:\n{current_unlock or '(none)'}\n\n"
                f"Reviewer feedback:\n{review_feedback}\n\n"
                f"Balatro Simplified Chinese style references:\n{style}\n\n"
                f"Translation memory references:\n{refs}\n\n"
                "Return: {\"name\":\"...\",\"text\":\"...\",\"unlock\":\"...\"}"
            ),
        },
    ]


def _parse_quality_review(response: dict[str, object]) -> EntryQualityReview:
    needs_revision = bool(response.get("needs_revision"))
    naturalness = _string_list(response.get("naturalness_warnings"))
    meaning = _string_list(response.get("meaning_warnings"))
    rewrite_hint = response.get("rewrite_hint")
    return EntryQualityReview(
        needs_revision=needs_revision,
        naturalness_warnings=naturalness,
        meaning_warnings=meaning,
        rewrite_hint=rewrite_hint if isinstance(rewrite_hint, str) else "",
    )


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _protect_existing_tokens(text: str, original_tokens: list[str]) -> str:
    if not text or not original_tokens:
        return text
    spans = extract_tokens(text)
    if not spans:
        return text

    used: set[int] = set()
    replacements: list[tuple[int, int, str]] = []
    for span in spans:
        token_index = _next_matching_token_index(
            raw=span.raw,
            original_tokens=original_tokens,
            used=used,
        )
        if token_index is None:
            continue
        used.add(token_index)
        replacements.append((span.start, span.end, f"[[TOKEN_{token_index}]]"))

    protected = text
    for start, end, placeholder in reversed(replacements):
        protected = protected[:start] + placeholder + protected[end:]
    return protected


def _next_matching_token_index(
    *, raw: str, original_tokens: list[str], used: set[int]
) -> int | None:
    for index, token in enumerate(original_tokens):
        if index not in used and token == raw:
            return index
    return None


def _restore_and_validate(
    *,
    source: str,
    raw_translation,
    original_tokens: list[str],
    allow_reorder: bool = False,
) -> tuple[str, list[str]]:
    if not isinstance(raw_translation, str):
        return "", ["missing translation"]
    try:
        candidate = restore_tokens(
            raw_translation,
            original_tokens,
            allow_reorder=allow_reorder,
        )
    except TokenMismatchError as exc:
        return raw_translation, [str(exc)]
    return candidate, validate_token_identity(
        source,
        candidate,
        order_sensitive=not allow_reorder,
    )
