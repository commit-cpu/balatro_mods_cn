"""Lua parsing and patching package."""

from app.lua.extractor import LuaExtractor, TranslationUnit
from app.lua.patcher import (
    LuaPatcher,
    PatchInstruction,
    build_patch_instructions,
)
from app.lua.tokens import (
    TokenizedString,
    TokenMismatchError,
    TokenSpan,
    extract_tokens,
    has_any_token,
    normalize_for_rag,
    protect_for_llm,
    restore_tokens,
    validate_token_identity,
)
from app.lua.validator import (
    LuaValidationError,
    diff_is_translation_only,
    luajit_available,
    validate_file,
    validate_or_raise,
    validate_string,
)

__all__ = [
    "LuaExtractor",
    "LuaPatcher",
    "LuaValidationError",
    "PatchInstruction",
    "TokenMismatchError",
    "TokenSpan",
    "TokenizedString",
    "TranslationUnit",
    "build_patch_instructions",
    "diff_is_translation_only",
    "extract_tokens",
    "has_any_token",
    "luajit_available",
    "normalize_for_rag",
    "protect_for_llm",
    "restore_tokens",
    "validate_file",
    "validate_or_raise",
    "validate_string",
    "validate_token_identity",
]
