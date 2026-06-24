"""Tests for app.lua.tokens – token detection, normalization, protection, restoration."""

from __future__ import annotations

import pytest

from app.lua.tokens import (
    TokenMismatchError,
    TokenizedString,
    extract_tokens,
    has_any_token,
    normalize_for_rag,
    protect_for_llm,
    restore_tokens,
    validate_token_identity,
)


class TestTokenExtraction:
    def test_simple_style_token(self) -> None:
        tokens = extract_tokens("{C:mult}+#1#{} Mult")
        assert len(tokens) == 3
        assert tokens[0].raw == "{C:mult}"
        assert tokens[1].raw == "#1#"
        assert tokens[2].raw == "{}"

    def test_combined_style_token(self) -> None:
        tokens = extract_tokens("{C:legendary,E:1}upsides{}")
        assert len(tokens) == 2
        assert tokens[0].raw == "{C:legendary,E:1}"
        assert tokens[1].raw == "{}"

    def test_x_multiplier_token(self) -> None:
        tokens = extract_tokens("{X:mult,C:white} X#1# {}")
        assert len(tokens) == 3
        assert tokens[0].raw == "{X:mult,C:white}"
        assert tokens[1].raw == "#1#"
        assert tokens[2].raw == "{}"

    def test_no_tokens(self) -> None:
        tokens = extract_tokens("Start run with")
        assert len(tokens) == 0

    def test_only_tokens(self) -> None:
        tokens = extract_tokens("{C:attention}#1#{}")
        assert len(tokens) == 3

    def test_nested_braces_not_confused(self) -> None:
        """Ensure we don't confuse Lua table braces with tokens."""
        tokens = extract_tokens("return { descriptions = {")
        assert len(tokens) == 0

    def test_tag_token(self) -> None:
        tokens = extract_tokens("{C:attention,T:tag_double}#1#")
        assert len(tokens) == 2
        assert tokens[0].raw == "{C:attention,T:tag_double}"

    def test_voucher_token(self) -> None:
        tokens = extract_tokens("{C:tarot,T:v_crystal_ball}#1#{} voucher")
        assert len(tokens) == 3
        assert tokens[0].raw == "{C:tarot,T:v_crystal_ball}"

    def test_card_token(self) -> None:
        tokens = extract_tokens("{C:tarot,T:c_fool}#2#")
        assert len(tokens) == 2
        assert tokens[0].raw == "{C:tarot,T:c_fool}"

    def test_scale_token(self) -> None:
        tokens = extract_tokens("{C:money}$#1#{s:0.85} per")
        assert len(tokens) == 3
        assert tokens[0].raw == "{C:money}"
        assert tokens[1].raw == "#1#"
        assert tokens[2].raw == "{s:0.85}"

    def test_spades_hearts(self) -> None:
        tokens = extract_tokens("{C:attention}26{C:spades} Spades{} and")
        assert len(tokens) == 3
        assert tokens[0].raw == "{C:attention}"
        assert tokens[1].raw == "{C:spades}"
        assert tokens[2].raw == "{}"


class TestHasAnyToken:
    def test_with_tokens(self) -> None:
        assert has_any_token("{C:mult}+#1#{} Mult")

    def test_without_tokens(self) -> None:
        assert not has_any_token("Plain text without tokens")

    def test_empty_string(self) -> None:
        assert not has_any_token("")


class TestNormalizeForRag:
    def test_style_and_var(self) -> None:
        result = normalize_for_rag("{C:mult}+#1#{} Mult")
        assert result == "<style_mult>+<var_1><style_reset> mult"

    def test_combined_style(self) -> None:
        result = normalize_for_rag("{C:legendary,E:1}upsides{}")
        assert result == "<style_legendary,edition_1>upsides<style_reset>"

    def test_no_tokens(self) -> None:
        result = normalize_for_rag("Start run with")
        assert result == "start run with"


class TestProtectForLlm:
    def test_replaces_with_placeholders(self) -> None:
        safe, raw_tokens = protect_for_llm("{C:mult}+#1#{} Mult")
        assert safe == "[[TOKEN_0]]+[[TOKEN_1]][[TOKEN_2]] Mult"
        assert raw_tokens == ["{C:mult}", "#1#", "{}"]

    def test_no_tokens(self) -> None:
        safe, raw_tokens = protect_for_llm("Hello world")
        assert safe == "Hello world"
        assert raw_tokens == []


class TestRestoreTokens:
    def test_roundtrip(self) -> None:
        original = "{C:mult}+#1#{} Mult"
        safe, raw = protect_for_llm(original)
        restored = restore_tokens(safe, raw)
        assert restored == original

    def test_reordered_tokens_preserves_position(self) -> None:
        original = "{C:attention}Boss Blind{}, gain a"
        safe, raw = protect_for_llm(original)
        restored = restore_tokens(safe, raw)
        assert restored == original

    def test_mismatch_count_raises(self) -> None:
        safe = "[[TOKEN_0]] text [[TOKEN_1]]"
        with pytest.raises(TokenMismatchError):
            restore_tokens(safe, ["{C:mult}"])  # only 1, need 2

    def test_mismatch_extra_placeholder_raises(self) -> None:
        safe = "[[TOKEN_0]] text [[TOKEN_1]]"
        with pytest.raises(TokenMismatchError):
            restore_tokens(safe, ["{C:mult}", "#1#", "{}"])  # 3, only 2 in text

    def test_reordered_placeholders_raise(self) -> None:
        safe = "[[TOKEN_1]] before [[TOKEN_0]]"
        with pytest.raises(TokenMismatchError):
            restore_tokens(safe, ["{C:mult}", "#1#"])

    def test_no_placeholders(self) -> None:
        restored = restore_tokens("Plain text", [])
        assert restored == "Plain text"


class TestValidateTokenIdentity:
    def test_identical_passes(self) -> None:
        errors = validate_token_identity(
            "{C:mult}+#1#{} Mult",
            "{C:mult}+#1#{} 倍率",
        )
        assert len(errors) == 0

    def test_count_mismatch(self) -> None:
        errors = validate_token_identity(
            "{C:mult}+#1#{} Mult",
            "+#1#{} 倍率",
        )
        assert len(errors) >= 1
        assert any("count" in e.lower() for e in errors)

    def test_order_mismatch(self) -> None:
        errors = validate_token_identity(
            "{C:mult}+#1#{} Mult",
            "#1#+{C:mult}{} 倍率",
        )
        assert len(errors) >= 1

    def test_no_tokens_both_sides(self) -> None:
        errors = validate_token_identity("Hello", "你好")
        assert len(errors) == 0


class TestTokenizedString:
    def test_complete_example(self) -> None:
        ts = TokenizedString.from_string(
            "{C:attention}Boss Blind{}, gain a {C:attention,T:tag_double}#1#"
        )
        assert ts.source == "{C:attention}Boss Blind{}, gain a {C:attention,T:tag_double}#1#"
        assert len(ts.tokens) == 4
        assert ts.token_signature == "style_attention|style_reset|style_attention,tag_tag_double|var_1"

    def test_normalized_lowercase(self) -> None:
        ts = TokenizedString.from_string("Gain {C:mult}+#1#{} Mult")
        assert ts.normalized.startswith("gain ")
        assert "<style_mult>" in ts.normalized

    def test_prompt_safe_placeholders(self) -> None:
        ts = TokenizedString.from_string("{C:mult}+#1#{}")
        assert ts.prompt_safe == "[[TOKEN_0]]+[[TOKEN_1]][[TOKEN_2]]"
