"""Tests for app.lua.patcher – lossless byte-level patching."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.lua.extractor import LuaExtractor
from app.lua.patcher import (
    LuaPatcher,
    PatchInstruction,
    build_patch_instructions,
)


@pytest.fixture
def patcher() -> LuaPatcher:
    return LuaPatcher()


@pytest.fixture
def extractor() -> LuaExtractor:
    return LuaExtractor()


# ---------------------------------------------------------------------------
# unit tests – PatchInstruction
# ---------------------------------------------------------------------------


class TestPatchInstruction:
    def test_simple_replacement(self, patcher: LuaPatcher) -> None:
        source = b'"Hello world"'
        ins = PatchInstruction(
            unit_key="test.key",
            byte_start=1,
            byte_end=12,
            new_text="你好世界",
        )
        result = patcher.patch(source, [ins])
        assert result == b'"\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c"'

    def test_reverse_order_matters(self, patcher: LuaPatcher) -> None:
        """Two instructions: earlier in file and later.  Must still work."""
        source = b'first="A" second="B"'
        # first="A" second="B"
        # 0123456789...  "A" content at 7-8, "B" content at 18-19
        instructions = [
            PatchInstruction("a", 7, 8, "X"),
            PatchInstruction("b", 18, 19, "Y"),
        ]
        result = patcher.patch(source, instructions)
        assert result == b'first="X" second="Y"'

    def test_same_length_replacement(self, patcher: LuaPatcher) -> None:
        source = b'"hi"'
        ins = PatchInstruction("k", 1, 3, "yo")
        result = patcher.patch(source, [ins])
        assert result == b'"yo"'


# ---------------------------------------------------------------------------
# integration tests – full extract → patch → validate cycle
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_lua(tmp_path: Path) -> tuple[bytes, Path]:
    content = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Test Joker",
                text={
                    "{C:mult}+#1#{} Mult",
                    "for every {C:attention}Joker{}",
                },
            },
        },
    },
}
"""
    path = tmp_path / "en.lua"
    path.write_bytes(content)
    return content, path


@pytest.fixture(scope="module")
def origin_path() -> Path:
    p = Path("data/repos/Balatro__Origin/localization/en-us.lua")
    if not p.exists():
        pytest.skip("Origin en-us.lua not available")
    return p


class TestRoundTrip:
    def test_identity_patch(self, extractor: LuaExtractor, patcher: LuaPatcher, sample_lua: tuple[bytes, Path]) -> None:
        source, path = sample_lua
        units = extractor.extract_file(path)
        identity = {u.unit_key: u.source_text for u in units}
        instructions, errors = build_patch_instructions(units, identity)
        assert len(errors) == 0
        result = patcher.patch(source, instructions)
        assert result == source, "Identity patch must be byte-for-byte identical"

    def test_translation_patch(self, extractor: LuaExtractor, patcher: LuaPatcher, sample_lua: tuple[bytes, Path]) -> None:
        source, path = sample_lua
        units = extractor.extract_file(path)

        # Build translation map
        translations = {
            "descriptions.Joker.j_test.name": "测试小丑",
            "descriptions.Joker.j_test.text[0]": "{C:mult}+#1#{} 倍率",
            "descriptions.Joker.j_test.text[1]": "每张{C:attention}小丑{}",
        }
        instructions, errors = build_patch_instructions(units, translations)
        assert len(errors) == 0
        result = patcher.patch(source, instructions)

        # Verify each translation appears in the result
        decoded = result.decode("utf-8")
        assert "测试小丑" in decoded
        assert "+#1#{} 倍率" in decoded
        assert "每张{C:attention}小丑{}" in decoded

        # Verify structure is preserved
        assert 'name="' in decoded
        assert 'text={' in decoded
        assert 'return {' in decoded

        # Verify tokens are preserved
        assert "{C:mult}" in decoded
        assert "#1#" in decoded
        assert "{}" in decoded
        assert "{C:attention}" in decoded

    def test_preserves_comments_and_whitespace(
        self, extractor: LuaExtractor, patcher: LuaPatcher, tmp_path: Path
    ) -> None:
        content = b"""-- Header comment
return {
    descriptions={
        Joker={
            j_test={
                name="Test Joker",  -- inline comment
                text={
                    "Hello world",
                },
            },
        },
    },
}
-- Footer comment
"""
        path = tmp_path / "en.lua"
        path.write_bytes(content)
        units = extractor.extract_file(path)

        translations = {
            "descriptions.Joker.j_test.name": "测试",
            "descriptions.Joker.j_test.text[0]": "你好世界",
        }
        instructions, errors = build_patch_instructions(units, translations)
        assert len(errors) == 0
        result = patcher.patch(content, instructions)
        decoded = result.decode("utf-8")

        assert "-- Header comment" in decoded
        assert "-- inline comment" in decoded
        assert "-- Footer comment" in decoded
        assert "测试" in decoded
        assert "你好世界" in decoded

    def test_missing_translations_reported(
        self, extractor: LuaExtractor, patcher: LuaPatcher, sample_lua: tuple[bytes, Path]
    ) -> None:
        _, path = sample_lua
        units = extractor.extract_file(path)
        # Only provide 1 of 3 translations
        translations = {"descriptions.Joker.j_test.name": "测试"}
        instructions, errors = build_patch_instructions(units, translations)
        assert len(errors) == 2
        assert any("text[0]" in e for e in errors)
        assert any("text[1]" in e for e in errors)

    def test_extra_translations_reported(
        self, extractor: LuaExtractor, patcher: LuaPatcher, sample_lua: tuple[bytes, Path]
    ) -> None:
        _, path = sample_lua
        units = extractor.extract_file(path)
        translations = {
            "descriptions.Joker.j_test.name": "测试",
            "descriptions.Joker.j_test.text[0]": "X",
            "descriptions.Joker.j_test.text[1]": "Y",
            "nonexistent.key": "??",
        }
        instructions, errors = build_patch_instructions(units, translations)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]


class TestRealFileRoundTrip:
    """Verify the extractor and patcher work on the real game files."""

    def test_en_identity_roundtrip(self, extractor: LuaExtractor, patcher: LuaPatcher, origin_path: Path) -> None:
        source = origin_path.read_bytes()
        units = extractor.extract_file(origin_path)
        identity = {u.unit_key: u.source_text for u in units}
        instructions, errors = build_patch_instructions(units, identity)
        assert len(errors) == 0
        result = patcher.patch(source, instructions)
        assert result == source, "Real file identity round-trip must be byte-perfect"

    def test_cryptid_en_roundtrip(self, extractor: LuaExtractor, patcher: LuaPatcher) -> None:
        path = Path("data/repos/SpectralPack__Cryptid/localization/en-us.lua")
        if not path.exists():
            pytest.skip("Cryptid en-us.lua not available")
        source = path.read_bytes()
        units = extractor.extract_file(path)
        identity = {u.unit_key: u.source_text for u in units}
        instructions, errors = build_patch_instructions(units, identity)
        assert len(errors) == 0
        result = patcher.patch(source, instructions)
        assert result == source, "Cryptid identity round-trip must be byte-perfect"
