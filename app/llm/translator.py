from __future__ import annotations

from dataclasses import dataclass

from app.lua.tokens import (
    TokenMismatchError,
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


def _build_messages(
    *,
    model: str,
    safe_source: str,
    references: list[TranslationReference],
) -> list[dict[str, str]]:
    refs = "\n".join(
        f"- score={ref.score:.4f}\n  EN: {ref.source_text}\n  ZH: {ref.target_text}"
        for ref in references
    )
    return [
        {
            "role": "system",
            "content": (
                "You translate Balatro mod localization strings into Simplified Chinese. "
                "Preserve every placeholder exactly, including [[TOKEN_n]] markers. "
                "Return JSON only with key translation."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Model hint: {model}\n"
                f"Source string:\n{safe_source}\n\n"
                f"Translation memory references:\n{refs or '(none)'}\n\n"
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
) -> list[dict[str, str]]:
    refs = "\n".join(
        f"- score={ref.score:.4f}\n  EN: {ref.source_text}\n  ZH: {ref.target_text}"
        for ref in references
    )
    return [
        {
            "role": "system",
            "content": (
                "You translate Balatro mod localization entries into Simplified Chinese. "
                "Translate the complete description as one coherent entry, not line by line. "
                "Preserve every [[TOKEN_n]] placeholder exactly. "
                "Do not translate names after labels like Idea:, Art:, Code:, or Concept:. "
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
                f"Translation memory references:\n{refs or '(none)'}\n\n"
                "Return: {\"name\":\"...\",\"text\":\"...\",\"unlock\":\"...\"}"
            ),
        },
    ]


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
