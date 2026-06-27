from __future__ import annotations

from app.lua.patcher import LuaPatcher
from app.lua.table_writer import EntryTableTranslation, build_entry_table_patches


def test_build_entry_table_patches_replaces_text_table_with_new_line_count() -> None:
    source = b"""return {
    descriptions={
        Joker={
            j_test={
                name="Test Joker",
                text={"Hello"},
                unlock={
                    "Find this",
                },
            },
        },
    },
}
"""

    patches, errors = build_entry_table_patches(
        source,
        [
            EntryTableTranslation(
                entry_key="descriptions.Joker.j_test",
                name="测试小丑",
                text=["第一行", "第二行"],
                unlock=["找到这张牌", "再打出它"],
            )
        ],
    )
    patched = LuaPatcher().patch(source, patches).decode("utf-8")

    assert errors == []
    assert 'name="测试小丑"' in patched
    assert 'text={\n                    "第一行",\n                    "第二行",\n                }' in patched
    assert '"找到这张牌"' in patched
    assert '"再打出它"' in patched
    assert '"Hello"' not in patched


def test_build_entry_table_patches_normalizes_embedded_newlines() -> None:
    source = b"""return {
    descriptions={
        Other={
            p_test={
                name="Test Pack",
                text={"Choose one"},
            },
        },
    },
}
"""

    patches, errors = build_entry_table_patches(
        source,
        [
            EntryTableTranslation(
                entry_key="descriptions.Other.p_test",
                name="神圣包",
                text=["从最多{C:attention}#2#{}张神圣牌中\n"],
                unlock=[],
            )
        ],
    )
    patched = LuaPatcher().patch(source, patches).decode("utf-8")

    assert errors == []
    assert '"从最多{C:attention}#2#{}张神圣牌中"' in patched
    assert '"从最多{C:attention}#2#{}张神圣牌中\\n"' not in patched
