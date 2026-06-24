"""Tests for app.lua.validator – LuaJIT compile and diff validation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.lua.extractor import LuaExtractor
from app.lua.validator import (
    diff_is_translation_only,
    luajit_available,
    validate_file,
    validate_or_raise,
    validate_string,
    LuaValidationError,
)


@pytest.fixture
def extractor() -> LuaExtractor:
    return LuaExtractor()


class TestDiffIsTranslationOnly:
    def test_identical_bytes_pass(self) -> None:
        src = b'"hello" "world"'
        ok, msg = diff_is_translation_only(src, src, [])
        assert ok
        assert msg == ""

    def test_only_translation_bytes_changed(self, extractor: LuaExtractor) -> None:
        src = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Test Joker",
                text={
                    "Hello",
                },
            },
        },
    },
}
"""
        units = extractor.extract_bytes(src)
        # Change only the "Hello" string content
        # "Hello" is 5 bytes: positions vary depending on exact source
        hello_unit = [u for u in units if u.source_text == "Hello"][0]
        patched = (
            src[: hello_unit.byte_start]
            + "你好".encode("utf-8")
            + src[hello_unit.byte_end :]
        )
        ok, msg = diff_is_translation_only(src, patched, units)
        assert ok, msg

    def test_translation_may_contain_following_structural_byte(
        self, extractor: LuaExtractor
    ) -> None:
        src = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Hello",
                text={
                    "World",
                },
            },
        },
    },
}
"""
        units = extractor.extract_bytes(src)
        hello_unit = next(u for u in units if u.source_text == "Hello")
        patched = (
            src[: hello_unit.byte_start]
            + "你好,带逗号".encode("utf-8")
            + src[hello_unit.byte_end :]
        )

        ok, msg = diff_is_translation_only(src, patched, units)
        assert ok, msg

    def test_structural_change_detected(self, extractor: LuaExtractor) -> None:
        src = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Test Joker",
            },
        },
    },
}
"""
        units = extractor.extract_bytes(src)
        # Change a comma outside the string content
        bad = src.replace(b",", b";", 1)
        ok, msg = diff_is_translation_only(src, bad, units)
        assert not ok
        assert "Unauthorised" in msg


class TestLuaJitAvailable:
    def test_returns_bool(self) -> None:
        result = luajit_available()
        assert isinstance(result, bool)


class TestValidateFile:
    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_valid_file_passes(self, tmp_path: Path) -> None:
        path = tmp_path / "valid.lua"
        path.write_text("return { a = 1 }", encoding="utf-8")
        ok, err = validate_file(path)
        assert ok
        assert err == ""

    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_invalid_file_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "invalid.lua"
        path.write_text("return { a = }", encoding="utf-8")
        ok, err = validate_file(path)
        assert not ok
        assert err

    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_validate_or_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "ok.lua"
        path.write_text("return {}", encoding="utf-8")
        validate_or_raise(path)  # should not raise

    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_validate_or_raise_on_bad_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.lua"
        path.write_text("return {", encoding="utf-8")
        with pytest.raises(LuaValidationError):
            validate_or_raise(path)


class TestValidateString:
    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_valid_string_passes(self) -> None:
        ok, err = validate_string("return { a = 1 }")
        assert ok

    @pytest.mark.skipif(not shutil.which("luajit"), reason="luajit not installed")
    def test_invalid_string_fails(self) -> None:
        ok, err = validate_string("return { a = }")
        assert not ok
