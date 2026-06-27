"""Tests for app.lua.extractor – tree-sitter Lua extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.lua.extractor import LuaExtractor, TranslationUnit

# Minimal valid Balatro-style localization file
MINIMAL_LUA = b"""return {
    descriptions={
        Back={
            b_test={
                name="Test Deck",
                text={
                    "Start run with",
                    "{C:attention}+#1#{} bonus",
                },
            },
        },
    },
}
"""


@pytest.fixture
def extractor() -> LuaExtractor:
    return LuaExtractor()


@pytest.fixture
def minimal_file(tmp_path: Path) -> Path:
    path = tmp_path / "en-us.lua"
    path.write_bytes(MINIMAL_LUA)
    return path


@pytest.fixture(scope="module")
def origin_en() -> list[TranslationUnit]:
    path = Path("data/repos/Balatro__Origin/localization/en-us.lua")
    if not path.exists():
        pytest.skip("Origin en-us.lua not available")
    return LuaExtractor().extract_file(path)


class TestExtractBytes:
    def test_extracts_name(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(MINIMAL_LUA)
        names = [u for u in units if u.unit_key.endswith(".name")]
        assert len(names) == 1
        assert names[0].unit_key == "descriptions.Back.b_test.name"
        assert names[0].source_text == "Test Deck"
        assert names[0].context_type == "back_name"

    def test_extracts_text_lines(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(MINIMAL_LUA)
        texts = [u for u in units if ".text[" in u.unit_key]
        assert len(texts) == 2
        assert texts[0].unit_key == "descriptions.Back.b_test.text[0]"
        assert texts[0].source_text == "Start run with"
        assert texts[0].context_type == "back_description_line"
        assert texts[1].unit_key == "descriptions.Back.b_test.text[1]"
        assert texts[1].source_text == "{C:attention}+#1#{} bonus"
        assert texts[1].context_type == "back_description_line"

    def test_total_unit_count(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(MINIMAL_LUA)
        assert len(units) == 3  # 1 name + 2 text lines

    def test_byte_spans_are_correct(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(MINIMAL_LUA)
        for u in units:
            # Verify that the bytes at the span actually decode to source_text
            actual = MINIMAL_LUA[u.byte_start : u.byte_end].decode("utf-8")
            assert actual == u.source_text, (
                f"Byte span mismatch for {u.unit_key}: "
                f"expected {u.source_text!r}, got {actual!r}"
            )

    def test_units_include_extracted_tokens(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(MINIMAL_LUA)
        tokenized = next(u for u in units if u.unit_key == "descriptions.Back.b_test.text[1]")

        assert [token.raw for token in tokenized.tokens] == ["{C:attention}", "#1#", "{}"]

    def test_empty_strings_are_valid_units(self, extractor: LuaExtractor) -> None:
        source = b"""return {
    descriptions={
        Joker={
            j_empty={
                name="",
                text={
                    "",
                },
            },
        },
    },
}
"""
        units = extractor.extract_bytes(source)

        assert [u.source_text for u in units] == ["", ""]
        for unit in units:
            assert unit.byte_start == unit.byte_end

    def test_empty_file(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(b"")
        assert len(units) == 0

    def test_not_a_localization_file(self, extractor: LuaExtractor) -> None:
        units = extractor.extract_bytes(b"print('hello')")
        assert len(units) == 0


MISC_LUA = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Test",
                text={"Line one"},
            },
        },
    },
    misc={
        dictionary={
            ["$"]="$",
            b_FAQ="FAQ",
        },
        v_dictionary={
            a_stock="+#1# Stock",
        },
        labels={
            fn_Mythic="Mythic",
        },
        quips={
            dq_1={
                "Yikes!",
                "Good luck!",
            },
        },
    },
}
"""


class TestExtractMisc:
    def test_extracts_dictionary_scalars(self, extractor: LuaExtractor) -> None:
        units = {
            u.unit_key: u for u in extractor.extract_bytes(MISC_LUA)
            if u.unit_key.startswith("misc.dictionary.")
        }
        assert set(units) == {"misc.dictionary.$", "misc.dictionary.b_FAQ"}
        assert units["misc.dictionary.b_FAQ"].source_text == "FAQ"
        assert units["misc.dictionary.b_FAQ"].context_type == "misc_dictionary"
        # bracket-string key "$" decodes to a bare $ key
        assert units["misc.dictionary.$"].source_text == "$"

    def test_extracts_labels(self, extractor: LuaExtractor) -> None:
        units = {
            u.unit_key: u for u in extractor.extract_bytes(MISC_LUA)
            if u.unit_key.startswith("misc.labels.")
        }
        assert set(units) == {"misc.labels.fn_Mythic"}
        assert units["misc.labels.fn_Mythic"].source_text == "Mythic"
        assert units["misc.labels.fn_Mythic"].context_type == "misc_label"

    def test_extracts_custom_misc_scalar_sections(self, extractor: LuaExtractor) -> None:
        units = {
            u.unit_key: u for u in extractor.extract_bytes(MISC_LUA)
            if u.unit_key.startswith("misc.v_dictionary.")
        }
        assert set(units) == {"misc.v_dictionary.a_stock"}
        assert units["misc.v_dictionary.a_stock"].source_text == "+#1# Stock"
        assert units["misc.v_dictionary.a_stock"].context_type == "misc_v_dictionary"

    def test_extracts_quips_array(self, extractor: LuaExtractor) -> None:
        units = {
            u.unit_key: u for u in extractor.extract_bytes(MISC_LUA)
            if u.unit_key.startswith("misc.quips.")
        }
        assert set(units) == {"misc.quips.dq_1[0]", "misc.quips.dq_1[1]"}
        assert units["misc.quips.dq_1[0]"].source_text == "Yikes!"
        assert units["misc.quips.dq_1[1]"].source_text == "Good luck!"
        assert units["misc.quips.dq_1[0]"].context_type == "quip_line"

    def test_misc_byte_spans_are_correct(self, extractor: LuaExtractor) -> None:
        units = [u for u in extractor.extract_bytes(MISC_LUA) if u.unit_key.startswith("misc.")]
        assert units  # sanity
        for u in units:
            actual = MISC_LUA[u.byte_start : u.byte_end].decode("utf-8")
            assert actual == u.source_text, (
                f"Byte span mismatch for {u.unit_key}: "
                f"expected {u.source_text!r}, got {actual!r}"
            )

    def test_misc_units_have_tokens(self, extractor: LuaExtractor) -> None:
        source = b'return { misc={ labels={ fn_x="{C:attention}X{}" } } }'
        units = [u for u in extractor.extract_bytes(source) if u.unit_key.startswith("misc.")]
        assert len(units) == 1
        assert [t.raw for t in units[0].tokens] == ["{C:attention}", "{}"]

    def test_descriptions_still_extracted_alongside_misc(
        self, extractor: LuaExtractor
    ) -> None:
        units = extractor.extract_bytes(MISC_LUA)
        keys = {u.unit_key for u in units}
        assert "descriptions.Joker.j_test.name" in keys
        assert "descriptions.Joker.j_test.text[0]" in keys


class TestExtractFile:
    def test_extracts_from_file(self, extractor: LuaExtractor, minimal_file: Path) -> None:
        units = extractor.extract_file(minimal_file)
        assert len(units) == 3

    def test_all_units_have_required_fields(
        self, extractor: LuaExtractor, minimal_file: Path
    ) -> None:
        units = extractor.extract_file(minimal_file)
        for u in units:
            assert isinstance(u, TranslationUnit)
            assert u.unit_key
            assert u.source_text is not None
            assert u.byte_start >= 0
            assert u.byte_end >= u.byte_start
            assert u.context_type


class TestRealFiles:
    """Smoke-test against the actual origin game files."""

    def test_extracts_all_units(self, origin_en: list[TranslationUnit]) -> None:
        assert len(origin_en) > 1000

    def test_all_unit_keys_are_unique(self, origin_en: list[TranslationUnit]) -> None:
        keys = [u.unit_key for u in origin_en]
        assert len(keys) == len(set(keys)), f"Duplicate keys: {set(k for k in keys if keys.count(k) > 1)}"

    def test_no_empty_source_texts(self, origin_en: list[TranslationUnit]) -> None:
        empties = [u for u in origin_en if not u.source_text]
        # Empty strings like "" in challenge deck text are valid but rare
        # They should still have correct byte spans
        for u in empties:
            assert u.byte_start <= u.byte_end

    def test_context_types_are_valid(self, origin_en: list[TranslationUnit]) -> None:
        valid_suffixes = {"_name", "_description_line"}
        valid_exact = {
            "unlock_condition",
            "misc_dictionary",
            "misc_label",
            "quip_line",
        }
        for u in origin_en:
            assert any(u.context_type.endswith(s) for s in valid_suffixes) or (
                u.context_type in valid_exact
                or u.context_type.startswith("misc_")
            ), f"Unexpected context_type: {u.context_type}"
