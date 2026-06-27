from __future__ import annotations

from pathlib import Path

from app.db.migrate import migrate
from app.llm.style_pack import (
    DEFAULT_STYLE_PACK_PATH,
    StyleCategory,
    StyleExample,
    StylePack,
    build_style_pack,
    load_style_pack,
    render_style_examples,
    save_style_pack,
    select_style_examples,
    select_tm_style_examples,
)


EN_LUA = b"""return {
    descriptions={
        Joker={
            j_a={name="Joker A", text={"Creates a copy", "at end of round"}},
            j_b={name="Joker B", text={"Retrigger adjacent Jokers"}},
        },
        Back={
            b_a={name="Back A", text={"Start with extra hand size"}},
        },
        Blind={
            bl_a={name="Blind A", text={"All cards are debuffed"}},
        },
    },
}
"""


ZH_LUA = b"""return {
    descriptions={
        Joker={
            j_a={name="\xe5\xb0\x8f\xe4\xb8\x91A", text={"\xe5\x9c\xa8\xe5\x9b\x9e\xe5\x90\x88\xe7\xbb\x93\xe6\x9d\x9f\xe6\x97\xb6", "\xe5\x88\x9b\xe5\xbb\xba\xe4\xb8\x80\xe5\xbc\xa0\xe5\xa4\x8d\xe5\x88\xb6\xe7\x89\x8c"}},
            j_b={name="\xe5\xb0\x8f\xe4\xb8\x91B", text={"\xe9\x87\x8d\xe6\x96\xb0\xe8\xa7\xa6\xe5\x8f\x91\xe7\x9b\xb8\xe9\x82\xbb\xe5\xb0\x8f\xe4\xb8\x91"}},
        },
        Back={
            b_a={name="\xe7\x89\x8c\xe7\xbb\x84A", text={"\xe5\xbc\x80\xe5\xb1\x80\xe6\x97\xb6\xe6\x89\x8b\xe7\x89\x8c\xe4\xb8\x8a\xe9\x99\x90\xe6\x9b\xb4\xe5\xa4\x9a"}},
        },
        Blind={
            bl_a={name="\xe7\x9b\xb2\xe6\xb3\xa8A", text={"\xe6\x89\x80\xe6\x9c\x89\xe7\x89\x8c\xe9\x83\xbd\xe8\xa2\xab\xe5\x89\x8a\xe5\xbc\xb1"}},
        },
    },
}
"""


def _write_origin_pair(tmp_path: Path) -> Path:
    repo = tmp_path / "Balatro__Origin"
    loc = repo / "localization"
    loc.mkdir(parents=True)
    (loc / "en-us.lua").write_bytes(EN_LUA)
    (loc / "zh_CN.lua").write_bytes(ZH_LUA)
    return repo


def test_build_style_pack_groups_examples_by_description_category(tmp_path: Path) -> None:
    repo = _write_origin_pair(tmp_path)

    pack = build_style_pack(
        repo=repo,
        source="localization/en-us.lua",
        target="localization/zh_CN.lua",
        min_per_category=1,
        max_per_category=2,
    )

    assert pack.source_mod_id == "balatro_origin"
    assert set(pack.categories) == {"back", "blind", "joker"}
    assert [example.unit_key for example in pack.categories["joker"].examples] == [
        "descriptions.Joker.j_a.text[0]",
        "descriptions.Joker.j_a.text[1]",
    ]
    assert pack.categories["joker"].available_count == 5
    assert pack.categories["joker"].minimum_met is True


def test_style_pack_round_trips_json(tmp_path: Path) -> None:
    repo = _write_origin_pair(tmp_path)
    pack = build_style_pack(
        repo=repo,
        source="localization/en-us.lua",
        target="localization/zh_CN.lua",
        min_per_category=1,
        max_per_category=2,
    )
    output = tmp_path / "style_pack.json"

    save_style_pack(pack, output)
    loaded = load_style_pack(output)

    assert loaded.to_dict() == pack.to_dict()


def test_default_style_pack_is_prebuilt_with_minimum_category_examples() -> None:
    pack = load_style_pack(DEFAULT_STYLE_PACK_PATH)

    assert pack is not None
    assert len(pack.categories) >= 10
    assert all(category.minimum_met for category in pack.categories.values())
    assert all(len(category.examples) >= 10 for category in pack.categories.values())


def test_select_style_examples_prefers_matching_category(tmp_path: Path) -> None:
    repo = _write_origin_pair(tmp_path)
    pack = build_style_pack(
        repo=repo,
        source="localization/en-us.lua",
        target="localization/zh_CN.lua",
        min_per_category=1,
        max_per_category=3,
    )

    examples = select_style_examples(
        pack,
        entry_key="descriptions.Joker.j_new",
        limit=2,
    )

    assert len(examples) == 2
    assert all(example.category == "joker" for example in examples)
    rendered = render_style_examples(examples)
    assert "Balatro Simplified Chinese style references" in rendered
    assert "EN: Creates a copy" in rendered
    assert "ZH: 在回合结束时" in rendered


def test_select_style_examples_uses_back_style_for_sleeves(tmp_path: Path) -> None:
    repo = _write_origin_pair(tmp_path)
    pack = build_style_pack(
        repo=repo,
        source="localization/en-us.lua",
        target="localization/zh_CN.lua",
        min_per_category=1,
        max_per_category=3,
    )

    examples = select_style_examples(
        pack,
        entry_key="descriptions.Sleeve.sleeve_new",
        limit=1,
    )

    assert examples[0].category == "back"
    assert examples[0].unit_key == "descriptions.Back.b_a.text[0]"


def test_select_tm_style_examples_supports_custom_categories(tmp_path: Path) -> None:
    db_path = tmp_path / "tm.db"
    migrate(db_path)
    with __import__("sqlite3").connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "translated_sleeves",
                "descriptions.Sleeve.sleeve_demo.text[0]",
                "sleeve_description_line",
                "{C:blue}+1{} hand every round",
                "每回合出牌次数{C:blue}+1{}",
                "hand every round",
                "",
                "imported_human",
                "point-style",
                "source-style",
                "target-style",
            ),
        )
        db.commit()

    examples = select_tm_style_examples(
        db_path,
        entry_key="descriptions.Sleeve.sleeve_new",
        query_text="{C:blue}+1{} hand every round",
        limit=2,
    )

    assert len(examples) == 1
    assert examples[0].source_mod_id == "translated_sleeves"
    assert examples[0].context_type == "sleeve_description_line"
    assert examples[0].target == "每回合出牌次数{C:blue}+1{}"


def test_select_style_examples_prefers_text_overlap_within_category(tmp_path: Path) -> None:
    repo = _write_origin_pair(tmp_path)
    pack = build_style_pack(
        repo=repo,
        source="localization/en-us.lua",
        target="localization/zh_CN.lua",
        min_per_category=1,
        max_per_category=10,
    )

    examples = select_style_examples(
        pack,
        entry_key="descriptions.Joker.j_new",
        query_text="Retrigger this Joker",
        limit=1,
    )

    assert examples[0].unit_key == "descriptions.Joker.j_b.text[0]"


def test_select_style_examples_keeps_matching_official_entry_lines(tmp_path: Path) -> None:
    j_a_0 = StyleExample(
        category="joker",
        context_type="joker_description_line",
        unit_key="descriptions.Joker.j_a.text[0]",
        source="Creates a copy",
        target="创建一张复制牌",
    )
    j_a_1 = StyleExample(
        category="joker",
        context_type="joker_description_line",
        unit_key="descriptions.Joker.j_a.text[1]",
        source="at end of round",
        target="在回合结束时",
    )
    j_b_0 = StyleExample(
        category="joker",
        context_type="joker_description_line",
        unit_key="descriptions.Joker.j_b.text[0]",
        source="copy effect",
        target="复制效果",
    )
    pack = StylePack(
        source_mod_id="balatro_origin",
        source_locale_path="localization/en-us.lua",
        target_locale_path="localization/zh_CN.lua",
        categories={
            "joker": StyleCategory(
                category="joker",
                available_count=3,
                minimum_required=1,
                examples=[j_a_0, j_a_1, j_b_0],
            )
        },
    )

    examples = select_style_examples(
        pack,
        entry_key="descriptions.Joker.j_new",
        query_text="Creates a copy effect",
        limit=2,
    )

    assert [example.unit_key for example in examples] == [
        "descriptions.Joker.j_a.text[0]",
        "descriptions.Joker.j_a.text[1]",
    ]
