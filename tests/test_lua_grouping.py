from app.lua.extractor import TranslationUnit
from app.lua.grouping import group_translation_units


def _unit(key: str, text: str) -> TranslationUnit:
    return TranslationUnit(
        unit_key=key,
        source_text=text,
        byte_start=0,
        byte_end=len(text),
        context_type="joker_description_line",
    )


def test_group_translation_units_by_entry_key() -> None:
    groups = group_translation_units(
        [
            _unit("descriptions.Joker.j_test.name", "Test Joker"),
            _unit("descriptions.Joker.j_test.text[0]", "Gain +#1# Mult"),
            _unit("descriptions.Joker.j_test.text[1]", "at end of round"),
            _unit("descriptions.Joker.j_test.unlock[0]", "Find this Joker"),
            _unit("descriptions.Back.b_test.name", "Test Deck"),
        ]
    )

    assert [group.entry_key for group in groups] == [
        "descriptions.Joker.j_test",
        "descriptions.Back.b_test",
    ]
    assert groups[0].name.source_text == "Test Joker"
    assert [unit.source_text for unit in groups[0].text] == [
        "Gain +#1# Mult",
        "at end of round",
    ]
    assert [unit.source_text for unit in groups[0].unlock] == ["Find this Joker"]
    assert groups[0].combined_text == "Gain +#1# Mult at end of round"
