from typer.testing import CliRunner
import json
from pathlib import Path
import threading
import time

from app.cli.main import (
    _apply_preview_consistency,
    _entry_style_examples,
    _llm_concurrency,
    _llm_config,
    _name_prepass_allows_reference,
    app,
)
from app.db.migrate import migrate
from app.llm.style_pack import StyleCategory, StyleExample, StylePack
from app.rag.term_checker import LockedTermInfo, check_entry_terms


def test_cli_has_rag_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "import-local-tm" in result.output
    assert "sync-vectors" in result.output
    assert "search" in result.output
    assert "build-style-pack" in result.output
    assert "apply-entry-preview" in result.output
    assert "audit-entry-output" in result.output
    assert "audit-rerun-keys" in result.output
    assert "merge-entry-preview" in result.output
    assert "translate-entry-loop" in result.output
    assert "rag-preview-mod" in result.output
    assert "translate-preview-mod" in result.output
    assert "translate-entry-preview-mod" in result.output


def test_build_style_pack_command_writes_json(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "origin"
    repo.mkdir()
    output = tmp_path / "style_pack.json"

    class FakePack:
        class Category:
            minimum_met = True

        categories = {"joker": Category()}

        def to_dict(self):
            return {
                "source_mod_id": "balatro_origin",
                "source_locale_path": "localization/en-us.lua",
                "target_locale_path": "localization/zh_CN.lua",
                "categories": {
                    "joker": {
                        "category": "joker",
                        "available_count": 12,
                        "minimum_required": 10,
                        "minimum_met": True,
                        "examples": [],
                    }
                },
            }

    def fake_build_style_pack(**kwargs):
        assert kwargs["repo"] == repo
        assert kwargs["source"] == "localization/en-us.lua"
        assert kwargs["target"] == "localization/zh_CN.lua"
        assert kwargs["min_per_category"] == 10
        assert kwargs["max_per_category"] == 1000
        return FakePack()

    monkeypatch.setattr("app.cli.main.build_style_pack", fake_build_style_pack)

    result = CliRunner().invoke(
        app,
        [
            "build-style-pack",
            "--repo",
            str(repo),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["categories"]["joker"]["available_count"] == 12
    assert "Style pack categories=1" in result.output


def test_apply_preview_consistency_uses_mod_name_for_styled_card_terms() -> None:
    rows = [
        {
            "entry_key": "descriptions.Enhanced.m_fam_stained_glass",
            "ok": True,
            "name": "彩色玻璃",
            "text": ["每次计分时获得版本"],
            "unlock": [],
            "source": {"name": "Stained Glass", "text": [], "unlock": []},
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
        {
            "entry_key": "descriptions.Familiar_Tarots.c_fam_vengeance",
            "ok": True,
            "name": "复仇",
            "text": ["将卡牌转化为{C:attention}污渍玻璃牌{}。"],
            "unlock": [],
            "source": {
                "name": "Vengeance",
                "text": ["Enhances selected card into a {C:attention}Stained Glass Card{}."],
                "unlock": [],
            },
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
    ]

    _apply_preview_consistency(rows)

    assert rows[1]["text"] == ["将卡牌转化为{C:attention}彩色玻璃牌{}。"]
    assert rows[1]["needs_review"] is False
    assert rows[1]["review"]["consistency_warnings"] == []


def test_apply_preview_consistency_reuses_best_translation_for_duplicate_source_body() -> None:
    rows = [
        {
            "entry_key": "descriptions.Familiar_Planets.c_one",
            "ok": True,
            "name": "一",
            "text": ["(等级：#1#+i) 虚数升级", "{C:attention}#4# {C:red}X#2#{}倍率"],
            "unlock": [],
            "target_units": {
                "name": "descriptions.Familiar_Planets.c_one.name",
                "text": [
                    "descriptions.Familiar_Planets.c_one.text[0]",
                    "descriptions.Familiar_Planets.c_one.text[1]",
                    "descriptions.Familiar_Planets.c_one.text[2]",
                    "descriptions.Familiar_Planets.c_one.text[3]",
                ],
                "unlock": [],
            },
            "patchable": False,
            "patch_warnings": ["text line count mismatch: source=4, target=2"],
            "apply_mode": "table",
            "source": {
                "name": "One",
                "text": [
                    "(lvl:#1#+i) Imaginary Level Up",
                    "{C:attention}#4#",
                    "{C:red}X#2#{} Mult and",
                    "{C:blue}X#3#{} chips",
                ],
                "unlock": [],
            },
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
        {
            "entry_key": "descriptions.Familiar_Planets.c_two",
            "ok": True,
            "name": "二",
            "text": ["(lvl:#1#+i) 虚数升级", "Imaginary 手牌"],
            "unlock": [],
            "target_units": {
                "name": "descriptions.Familiar_Planets.c_two.name",
                "text": [
                    "descriptions.Familiar_Planets.c_two.text[0]",
                    "descriptions.Familiar_Planets.c_two.text[1]",
                    "descriptions.Familiar_Planets.c_two.text[2]",
                    "descriptions.Familiar_Planets.c_two.text[3]",
                ],
                "unlock": [],
            },
            "patchable": False,
            "patch_warnings": ["text line count mismatch: source=4, target=2"],
            "apply_mode": "table",
            "source": {
                "name": "Two",
                "text": [
                    "(lvl:#1#+i) Imaginary Level Up",
                    "{C:attention}#4#",
                    "{C:red}X#2#{} Mult and",
                    "{C:blue}X#3#{} chips",
                ],
                "unlock": [],
            },
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
    ]

    _apply_preview_consistency(rows)

    assert rows[1]["text"] == rows[0]["text"]
    assert rows[1]["needs_review"] is False
    assert rows[1]["apply_mode"] == "table"
    assert rows[1]["patch_warnings"] == ["text line count mismatch: source=4, target=2"]


def test_apply_preview_consistency_flags_rerunnable_residual_english() -> None:
    row = {
        "entry_key": "descriptions.Familiar_Tarots.c_verdict",
        "ok": True,
        "name": "裁决",
        "text": ["生成一张随机的", "{C:attention}Consumble{}牌"],
        "unlock": [],
        "target_units": {
            "name": "descriptions.Familiar_Tarots.c_verdict.name",
            "text": [
                "descriptions.Familiar_Tarots.c_verdict.text[0]",
                "descriptions.Familiar_Tarots.c_verdict.text[1]",
            ],
            "unlock": [],
        },
        "patchable": True,
        "patch_warnings": [],
        "apply_mode": "unit",
        "source": {
            "name": "Verdict",
            "text": ["Creates a random", "{C:attention}Consumble{} card"],
            "unlock": [],
        },
        "review": {
            "term_violations": [],
            "consistency_warnings": [],
            "naturalness_warnings": [],
            "meaning_warnings": [],
            "rewrite_hint": "",
            "retry_history": [],
        },
        "needs_review": False,
    }

    _apply_preview_consistency([row])

    assert row["needs_review"] is True
    assert row["review"]["consistency_warnings"] == [
        "Residual English in text[1]: {C:attention}Consumble{}牌"
    ]


def test_name_prepass_rejects_unrelated_exact_context_reference() -> None:
    class Ref:
        source_text = "Gilded"
        mod_id = "partner_api"
        context_type = "partner_name"

    assert not _name_prepass_allows_reference(
        "Gilded",
        Ref(),
        expected_context_types={"enhanced_name"},
    )


def test_name_prepass_allows_same_context_exact_reference() -> None:
    class Ref:
        source_text = "Gilded"
        mod_id = "some_mod"
        context_type = "enhanced_name"

    assert _name_prepass_allows_reference(
        "Gilded",
        Ref(),
        expected_context_types={"enhanced_name"},
    )


def test_name_prepass_allows_origin_exact_reference_across_contexts() -> None:
    class Ref:
        source_text = "Seal"
        mod_id = "balatro_origin"
        context_type = "other_name"

    assert _name_prepass_allows_reference(
        "Seal",
        Ref(),
        expected_context_types={"enhanced_name"},
    )


def test_term_review_skips_non_origin_exact_term_from_unrelated_context() -> None:
    violations = check_entry_terms(
        source={"name": "Gilded", "text": [], "unlock": []},
        target={"name": "镀金", "text": [], "unlock": []},
        term_map={"Gilded": "黄金伙伴"},
        term_info={
            "Gilded": LockedTermInfo(
                target="黄金伙伴",
                context_types=frozenset({"partner_name"}),
                mod_ids=frozenset({"partner_api"}),
            )
        },
        expected_context_types={"enhanced_name", "enhanced_description_line"},
    )

    assert violations == []


def test_term_review_keeps_origin_exact_term_across_contexts() -> None:
    violations = check_entry_terms(
        source={"name": "Steel Card", "text": [], "unlock": []},
        target={"name": "钢牌", "text": [], "unlock": []},
        term_map={"Steel Card": "钢铁牌"},
        term_info={
            "Steel Card": LockedTermInfo(
                target="钢铁牌",
                context_types=frozenset({"enhanced_name"}),
                mod_ids=frozenset({"balatro_origin"}),
            )
        },
        expected_context_types={"joker_name", "joker_description_line"},
    )

    assert len(violations) == 1
    assert violations[0].term == "Steel Card"


def test_entry_style_examples_prefers_tm_custom_category_before_official_fallback(
    tmp_path,
) -> None:
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
    style_pack = StylePack(
        source_mod_id="balatro_origin",
        source_locale_path="en-us.lua",
        target_locale_path="zh_CN.lua",
        categories={
            "back": StyleCategory(
                category="back",
                available_count=1,
                minimum_required=1,
                examples=[
                    StyleExample(
                        category="back",
                        context_type="back_description_line",
                        unit_key="descriptions.Back.b_blue.text[0]",
                        source="{C:blue}+#1#{} hand",
                        target="每回合",
                    )
                ],
            )
        },
    )

    rendered = _entry_style_examples(
        style_pack=style_pack,
        db_path=db_path,
        entry_key="descriptions.Sleeve.sleeve_new",
        query_text="{C:blue}+1{} hand every round",
        limit=2,
    )

    assert "translated_sleeves:descriptions.Sleeve.sleeve_demo.text[0]" in rendered
    assert "每回合出牌次数{C:blue}+1{}" in rendered
    assert "descriptions.Back.b_blue.text[0]" in rendered


def test_rag_preview_mod_prints_references(monkeypatch, tmp_path) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")

    class FakeUnit:
        unit_key = "descriptions.Joker.j_test.name"
        source_text = "Gain +#1# Mult"

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [FakeUnit()]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRef:
        score = 0.91
        mod_id = "memory_mod"
        unit_key = "descriptions.Joker.j_memory.text[0]"
        source_text = "gain {C:mult}+#1#{} Mult"
        target_text = "获得{C:mult}+#1#{}倍率"

    class FakeResult:
        references = [FakeRef()]

    def fake_retrieve_references(**kwargs):
        assert kwargs["query_text"] == "Gain +#1# Mult"
        assert kwargs["top_k"] == 3
        return FakeResult()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", fake_retrieve_references)

    result = CliRunner().invoke(
        app,
        [
            "rag-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--top-k",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert "descriptions.Joker.j_test.name" in result.output
    assert "Gain +#1# Mult" in result.output
    assert "获得" in result.output


def test_translate_preview_mod_writes_jsonl(monkeypatch, tmp_path) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "preview.jsonl"

    class FakeUnit:
        unit_key = "descriptions.Joker.j_test.name"
        source_text = "Gain +#1# Mult"

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [FakeUnit()]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRef:
        score = 0.91
        mod_id = "memory_mod"
        unit_key = "memory.key"
        source_text = "Gain +#1# Mult"
        target_text = "获得 +#1# 倍率"

    class FakeRetrieval:
        references = [FakeRef()]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, references):
            assert source_text == "Gain +#1# Mult"
            assert references[0].target_text == "获得 +#1# 倍率"

            class Result:
                candidate_text = "获得 +#1# 倍率"
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--top-k",
            "3",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["unit_key"] == "descriptions.Joker.j_test.name"
    assert rows[0]["candidate_zh"] == "获得 +#1# 倍率"
    assert rows[0]["token_errors"] == []
    assert rows[0]["rag_refs"][0]["target"] == "获得 +#1# 倍率"


def test_translate_entry_preview_mod_runs_llm_calls_concurrently_in_source_order(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"
    active = 0
    max_active = 0
    lock = threading.Lock()
    clients = []

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Joker.j_a.name", "A"),
                FakeUnit("descriptions.Joker.j_a.text[0]", "first entry"),
                FakeUnit("descriptions.Joker.j_b.name", "B"),
                FakeUnit("descriptions.Joker.j_b.text[0]", "second entry"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(
            self,
            *,
            name_text,
            body_text,
            unlock_text,
            references,
            max_width,
            style_examples="",
        ):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            if body_text == "first entry":
                time.sleep(0.08)
            with lock:
                active -= 1

            class Result:
                name = f"{name_text}-zh"
                text = [f"{body_text}-zh"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: clients.append(object()) or clients[-1])

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "2",
            "--top-k",
            "3",
            "--concurrency",
            "2",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "concurrency=2" in result.output
    assert max_active == 2
    assert len(clients) == 2
    assert result.output.index("LLM done [2/2]") < result.output.index("LLM done [1/2]")
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["entry_key"] for row in rows] == [
        "descriptions.Joker.j_a",
        "descriptions.Joker.j_b",
    ]
    assert [row["text"] for row in rows] == [["first entry-zh"], ["second entry-zh"]]
    assert all(row["ok"] is True for row in rows)


def test_translate_entry_preview_mod_filters_entry_keys_file(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"
    keys_file = tmp_path / "rerun_keys.txt"
    keys_file.write_text("descriptions.Joker.j_b\n", encoding="utf-8")
    context_preview = tmp_path / "base_preview.jsonl"
    context_preview.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Other.m_custom",
                "ok": True,
                "needs_review": False,
                "source": {"name": "Custom Seal", "text": ["Adds Custom Seal"]},
                "name": "自定义蜡封",
                "text": ["添加自定义蜡封"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Joker.j_a.name", "A"),
                FakeUnit("descriptions.Joker.j_a.text[0]", "first entry"),
                FakeUnit("descriptions.Joker.j_b.name", "B"),
                FakeUnit("descriptions.Joker.j_b.text[0]", "second entry"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, *, name_text, body_text, style_examples, **kwargs):
            assert name_text == "B"
            assert body_text == "second entry"
            assert "Custom Seal -> 自定义蜡封" in style_examples

            class Result:
                name = "B-zh"
                text = ["second entry-zh"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "9999",
            "--entry-keys-file",
            str(keys_file),
            "--context-preview",
            str(context_preview),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "entry_filter=1" in result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["entry_key"] for row in rows] == ["descriptions.Joker.j_b"]
    assert rows[0]["text"] == ["second entry-zh"]


def test_translate_entry_preview_mod_logs_parallel_failure_summary(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Joker.j_bad.text[0]", "bad token"),
                FakeUnit("descriptions.Joker.j_fail.text[0]", "boom"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, *, body_text, **kwargs):
            if body_text == "boom":
                raise RuntimeError("upstream timeout")

            class Result:
                name = None
                text = []
                unlock = []
                token_errors = ["text: Token count mismatch"]

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr(
        "app.cli.main._entry_style_examples",
        lambda **kwargs: (
            "Balatro Simplified Chinese style references:\n"
            "- balatro_origin:descriptions.Joker.j_ref.text\n"
            "  EN: ref\n"
            "  ZH: 参考"
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "2",
            "--concurrency",
            "2",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "LLM queued [1/2] descriptions.Joker.j_bad" in result.output
    assert "style_refs=1" in result.output
    assert "LLM failed [2/2] descriptions.Joker.j_fail: upstream timeout" in result.output
    assert "Preview summary: ok=0 failed=1 token_error_entries=1 needs_review=2" in result.output


def test_translate_entry_preview_mod_accumulates_related_group_context(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"
    translated_order: list[str] = []

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Familiar_Tarots.c_fam_vengeance.name", "Vengeance"),
                FakeUnit(
                    "descriptions.Familiar_Tarots.c_fam_vengeance.text[0]",
                    "Enhances selected card into a {C:attention}Stained Glass Card{}.",
                ),
                FakeUnit(
                    "descriptions.Enhanced.m_fam_stained_glass.name",
                    "Stained Glass",
                ),
                FakeUnit(
                    "descriptions.Enhanced.m_fam_stained_glass.text[0]",
                    "Gains random Edition",
                ),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, *, name_text, body_text, style_examples="", **kwargs):
            translated_order.append(name_text)
            if name_text == "Vengeance":
                assert "Stained Glass -> 彩色玻璃" in style_examples
                assert "descriptions.Enhanced.m_fam_stained_glass" in style_examples

                class Result:
                    name = "复仇"
                    text = ["将卡牌转化为{C:attention}彩色玻璃牌{}。"]
                    unlock = []
                    token_errors = []

                return Result()

            class Result:
                name = "彩色玻璃"
                text = ["每次计分时获得随机版本"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "2",
            "--concurrency",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert translated_order == ["Stained Glass", "Vengeance"]
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["entry_key"] for row in rows] == [
        "descriptions.Familiar_Tarots.c_fam_vengeance",
        "descriptions.Enhanced.m_fam_stained_glass",
    ]
    assert rows[0]["text"] == ["将卡牌转化为{C:attention}彩色玻璃牌{}。"]


def test_translate_entry_preview_mod_sends_global_name_glossary_to_all_entries(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Enhanced.m_fam_stained_glass.name", "Stained Glass"),
                FakeUnit("descriptions.Enhanced.m_fam_stained_glass.text[0]", "Gains Edition"),
                FakeUnit("descriptions.Joker.j_plain.name", "Plain Joker"),
                FakeUnit("descriptions.Joker.j_plain.text[0]", "Gives chips"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class Result:
        def __init__(self, candidate_text, token_errors=None) -> None:
            self.candidate_text = candidate_text
            self.token_errors = token_errors or []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, **kwargs):
            translations = {
                "Stained Glass": "彩色玻璃",
                "Plain Joker": "普通小丑",
            }
            return Result(translations[source_text])

        def translate_entry(self, *, name_text, body_text, style_examples="", **kwargs):
            assert "Stained Glass -> 彩色玻璃" in style_examples
            assert "Plain Joker -> 普通小丑" in style_examples

            class EntryResult:
                name = "彩色玻璃" if name_text == "Stained Glass" else "普通小丑"
                text = ["已翻译"]
                unlock = []
                token_errors = []

            return EntryResult()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "2",
            "--concurrency",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["name"] for row in rows] == ["彩色玻璃", "普通小丑"]


def test_translate_entry_preview_mod_uses_origin_name_patterns_for_name_prepass(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Other.fam_gilded_seal_seal.name", "Gilded Seal"),
                FakeUnit(
                    "descriptions.Other.fam_gilded_seal_seal.text[0]",
                    "{C:money}$5{} when played",
                ),
            ]

    class BadRef:
        tm_entry_id = 10
        score = 1.0
        mod_id = "partner_api"
        unit_key = "descriptions.Partner.pnr_partner_gilded.name"
        context_type = "partner_name"
        source_text = "Gilded"
        target_text = "黄金伙伴"

    class FakeRetrieval:
        references = [BadRef()]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class NameResult:
        candidate_text = "镀金蜡封"
        token_errors = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, references):
            assert source_text == "Gilded Seal"
            pairs = {(ref.source_text, ref.target_text) for ref in references}
            assert ("Seal", "蜡封") in pairs
            assert ("Gold Seal", "金色蜡封") in pairs
            assert ("Gilded", "黄金伙伴") not in pairs
            return NameResult()

        def translate_entry(self, **kwargs):
            class Result:
                name = "黄金伙伴封印"
                text = ["打出时获得{C:money}$5{}"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")
    monkeypatch.setattr(
        "app.cli.main.build_locked_term_map",
        lambda db_path, mod_id=None: {
            "Blue Seal": "蓝色蜡封",
            "Gold Seal": "金色蜡封",
            "Purple Seal": "紫色蜡封",
            "Red Seal": "红色蜡封",
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--concurrency",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["name"] == "镀金蜡封"


def test_translate_entry_preview_mod_uses_name_prepass_for_label_only_entries(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [FakeUnit("misc.labels.fam_familiar_seal_seal", "Familiar Seal")]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class NameResult:
        candidate_text = "使魔蜡封"
        token_errors = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, references):
            assert source_text == "Familiar Seal"
            return NameResult()

        def translate_entry(self, **kwargs):
            raise AssertionError("label-only entries should not call translate_entry")

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--concurrency",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["ok"] is True
    assert row["patchable"] is True
    assert row["name"] == "使魔蜡封"
    assert row["text"] == []
    assert row["token_errors"] == []


def test_translate_entry_preview_name_prepass_ignores_unrelated_exact_context_refs(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Enhanced.m_gilded.name", "Gilded"),
                FakeUnit(
                    "descriptions.Enhanced.m_gilded.text[0]",
                    "{C:money}$#1#{} when held in hand",
                ),
            ]

    class BadRef:
        tm_entry_id = 10
        score = 1.0
        mod_id = "partner_api"
        unit_key = "descriptions.Partner.pnr_partner_gilded.name"
        context_type = "partner_name"
        source_text = "Gilded"
        target_text = "黄金伙伴"

    class FakeRetrieval:
        references = [BadRef()]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class NameResult:
        candidate_text = "镀金"
        token_errors = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, references):
            assert source_text == "Gilded"
            pairs = {(ref.source_text, ref.target_text) for ref in references}
            assert ("Gilded", "黄金伙伴") not in pairs
            return NameResult()

        def translate_entry(self, **kwargs):
            class Result:
                name = "镀金"
                text = ["在手牌中时获得{C:money}$#1#{}"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["name"] == "镀金"


def test_translate_entry_preview_canonicalizes_duplicate_source_names(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Other.fam_sapphire_seal_seal.name", "Sapphire Seal"),
                FakeUnit("descriptions.Other.fam_sapphire_seal_seal.text[0]", "Creates a card"),
                FakeUnit("misc.labels.fam_sapphire_seal_seal", "Sapphire Seal"),
            ]

    class FakeRetrieval:
        references = []

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    translated_names = iter(["蓝宝石蜡封", "宝蓝蜡封"])

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, *, source_text, **kwargs):
            class Result:
                candidate_text = next(translated_names)
                token_errors = []

            return Result()

        def translate_entry(self, *, name_text, **kwargs):
            class Result:
                name = "蓝宝石蜡封"
                text = ["生成一张牌"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "2",
            "--concurrency",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    by_key = {row["entry_key"]: row for row in rows}
    assert by_key["descriptions.Other.fam_sapphire_seal_seal"]["name"] == "蓝宝石蜡封"
    assert by_key["misc.labels.fam_sapphire_seal_seal"]["name"] == "蓝宝石蜡封"


def test_translate_entry_preview_mod_seeds_name_prepass_from_context_preview(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"
    keys_file = tmp_path / "rerun_keys.txt"
    keys_file.write_text("descriptions.Other.fam_sapphire_seal_seal\n", encoding="utf-8")
    context_preview = tmp_path / "base_preview.jsonl"
    context_preview.write_text(
        json.dumps(
            {
                "entry_key": "misc.labels.fam_sapphire_seal_seal",
                "ok": True,
                "needs_review": False,
                "source": {"name": "Sapphire Seal", "text": [], "unlock": []},
                "name": "宝石蓝蜡封",
                "text": [],
                "unlock": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Other.fam_sapphire_seal_seal.name", "Sapphire Seal"),
                FakeUnit(
                    "descriptions.Other.fam_sapphire_seal_seal.text[0]",
                    "Creates a {C:blue}Spectral{} card",
                ),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, **kwargs):
            raise AssertionError("context-preview name seed should skip name prepass")

        def translate_entry(self, *, name_text, **kwargs):
            assert name_text == "Sapphire Seal"

            class Result:
                name = "错误译名"
                text = ["生成一张{C:blue}幻灵牌{}"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--entry-keys-file",
            str(keys_file),
            "--context-preview",
            str(context_preview),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["name"] == "宝石蓝蜡封"


def test_translate_entry_preview_mod_uses_brief_name_seed(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mod_id": "Mod",
                "locale": "zh_CN",
                "source": {"repo": str(tmp_path), "source": "localization/default.lua"},
                "name_map": {"Seal": "蜡封"},
                "label_map": {},
                "term_map": {},
                "forbidden_terms": {},
                "open_questions": [],
                "proposed_updates": [],
                "last_preview": "",
                "last_audit": "",
                "updated_at": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Edition.e_seal.name", "Seal"),
                FakeUnit("descriptions.Edition.e_seal.text[0]", "Seal Card"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate(self, **kwargs):
            raise AssertionError("brief name seed should skip name prepass")

        def translate_entry(self, *, name_text, **kwargs):
            assert name_text == "Seal"
            captured["style_examples"] = kwargs.get("style_examples")

            class Result:
                name = "错误译名"
                text = ["蜡封牌"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main._entry_style_examples", lambda **kwargs: "")

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--output",
            str(output),
            "--brief",
            str(brief),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Confirmed mod translation brief" in str(captured["style_examples"])
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["name"] == "蜡封"


def test_translate_entry_preview_mod_writes_grouped_jsonl(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LLM_CONCURRENCY", raising=False)
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Joker.j_test.name", "Test Joker"),
                FakeUnit("descriptions.Joker.j_test.text[0]", "Gain +#1# Mult"),
                FakeUnit("descriptions.Joker.j_test.text[1]", "at end of round"),
                FakeUnit("descriptions.Joker.j_test.unlock[0]", "Find this Joker"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRef:
        score = 0.91
        mod_id = "memory_mod"
        unit_key = "memory.key"
        source_text = "Gain +#1# Mult"
        target_text = "获得 +#1# 倍率"

    class FakeRetrieval:
        references = [FakeRef()]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(
            self,
            *,
            name_text,
            body_text,
            unlock_text,
            references,
            max_width,
            style_examples,
        ):
            assert name_text == "Test Joker"
            assert body_text == "Gain +#1# Mult at end of round"
            assert unlock_text == "Find this Joker"
            assert references[0].target_text == "获得 +#1# 倍率"
            assert max_width == 18
            assert style_examples == "Official examples for joker"

            class Result:
                name = "测试小丑"
                text = ["获得 +#1# 倍率", "在回合结束时"]
                unlock = ["找到这张小丑牌"]
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main.load_style_pack", lambda path=None: object())

    class FakeStyleExample:
        unit_key = "style.key"
        source_mod_id = ""

    monkeypatch.setattr(
        "app.cli.main.select_style_examples",
        lambda pack, *, entry_key, query_text, limit, allow_fallback=True: [FakeStyleExample()],
    )
    monkeypatch.setattr("app.cli.main.select_tm_style_examples", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "app.cli.main.render_style_examples",
        lambda examples: "Official examples for joker",
    )
    seen_queries = []

    def fake_retrieve_references(**kwargs):
        seen_queries.append(kwargs["query_text"])
        assert kwargs["top_k"] == 3
        return FakeRetrieval()

    monkeypatch.setattr("app.cli.main.retrieve_references", fake_retrieve_references)
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--top-k",
            "3",
            "--max-width",
            "18",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["entry_key"] == "descriptions.Joker.j_test"
    assert rows[0]["patchable"] is True
    assert rows[0]["patch_warnings"] == []
    assert rows[0]["target_units"] == {
        "name": "descriptions.Joker.j_test.name",
        "text": [
            "descriptions.Joker.j_test.text[0]",
            "descriptions.Joker.j_test.text[1]",
        ],
        "unlock": ["descriptions.Joker.j_test.unlock[0]"],
    }
    assert rows[0]["source"] == {
        "name": "Test Joker",
        "text": ["Gain +#1# Mult", "at end of round"],
        "unlock": ["Find this Joker"],
    }
    assert rows[0]["name"] == "测试小丑"
    assert rows[0]["text"] == ["获得 +#1# 倍率", "在回合结束时"]
    assert rows[0]["unlock"] == ["找到这张小丑牌"]
    assert rows[0]["ok"] is True
    assert rows[0]["token_errors"] == []
    assert rows[0]["rag_refs"][0]["target"] == "获得 +#1# 倍率"
    assert seen_queries == [
        "Gain +#1# Mult",
        "at end of round",
        "Gain +#1# Mult at end of round",
    ]


def test_translate_entry_preview_mod_preserves_credit_lines_without_llm(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Edition.e_test.name", "Nitro"),
                FakeUnit("descriptions.Edition.e_test.text[0]", "{C:attention}+2{} hand size"),
                FakeUnit("descriptions.Edition.e_test.text[1]", "Idea: Boi Rowan"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(
            self,
            *,
            name_text,
            body_text,
            unlock_text,
            references,
            max_width,
            style_examples="",
        ):
            assert body_text == "{C:attention}+2{} hand size"

            class Result:
                name = "Nitro"
                text = ["{C:attention}+2{}手牌上限"]
                unlock = []
                token_errors = []

            return Result()

    def fake_retrieve_references(**kwargs):
        assert kwargs["query_text"] == "{C:attention}+2{} hand size"
        return FakeRetrieval()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", fake_retrieve_references)
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["text"] == ["{C:attention}+2{}手牌上限", "Idea: Boi Rowan"]
    assert rows[0]["ok"] is True
    assert rows[0]["patchable"] is True


def test_translate_entry_preview_mod_injects_glossary_references(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Joker.j_perkeo.name", "Perkeo"),
                FakeUnit(
                    "descriptions.Joker.j_perkeo.text[0]",
                    "Creates a {C:dark_edition}Negative{} copy",
                ),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class DenseRef:
        score = 0.77
        mod_id = "memory_mod"
        unit_key = "memory.key"
        source_text = "random consumable"
        target_text = "随机消耗牌"

    class GlossaryRef:
        score = 1.0
        mod_id = "balatro_origin"
        unit_key = "descriptions.Edition.e_negative.name"
        source_text = "Negative"
        target_text = "负片"

    class FakeRetrieval:
        references = [DenseRef()]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, *, references, **kwargs):
            assert references[0].source_text == "Negative"
            assert references[0].target_text == "负片"
            assert references[1].target_text == "随机消耗牌"

            class Result:
                name = "Perkeo"
                text = ["创建{C:dark_edition}负片{}复制"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())

    glossary_queries = []

    def fake_retrieve_glossary_references(**kwargs):
        glossary_queries.append(kwargs["query_text"])
        return [GlossaryRef()]

    monkeypatch.setattr(
        "app.cli.main.retrieve_glossary_references",
        fake_retrieve_glossary_references,
    )
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["rag_refs"][0]["target"] == "负片"
    assert glossary_queries == ["Perkeo Creates a {C:dark_edition}Negative{} copy"]


def test_translate_entry_preview_retries_after_quality_review(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Edition.e_test.name", "Nitro"),
                FakeUnit(
                    "descriptions.Edition.e_test.text[0]",
                    "{C:attention}+2{} hand size when {C:attention}played{}",
                ),
                FakeUnit(
                    "descriptions.Edition.e_test.text[1]",
                    "{C:attention}Resets{} at end of round{}",
                ),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class QualityReview:
        def __init__(self, needs_revision, naturalness_warnings, rewrite_hint) -> None:
            self.needs_revision = needs_revision
            self.naturalness_warnings = naturalness_warnings
            self.meaning_warnings = []
            self.rewrite_hint = rewrite_hint

        def to_dict(self):
            return {
                "needs_revision": self.needs_revision,
                "naturalness_warnings": self.naturalness_warnings,
                "meaning_warnings": self.meaning_warnings,
                "rewrite_hint": self.rewrite_hint,
            }

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, **kwargs):
            class Result:
                name = "Nitro"
                text = [
                    "{C:attention}+2{}手牌上限，当{C:attention}打出{}时，"
                    "{C:attention}重置{}，在回合结束时{}"
                ]
                unlock = []
                token_errors = []

            return Result()

        def review_entry_translation(self, *, text, **kwargs):
            if "当" in "".join(text):
                return QualityReview(
                    True,
                    ["语序生硬，保留英文 when/resets 结构"],
                    "改为：打出时 +2 手牌上限，回合结束时重置。",
                )
            return QualityReview(False, [], "")

        def revise_entry_translation(self, *, review_feedback, **kwargs):
            assert "打出时 +2 手牌上限" in review_feedback

            class Result:
                name = "Nitro"
                text = [
                    "{C:attention}打出{}时{C:attention}+2{}手牌上限，回合结束时{C:attention}重置{}"
                ]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    row = rows[0]
    assert row["text"] == [
        "{C:attention}打出{}时{C:attention}+2{}手牌上限，回合结束时{C:attention}重置{}"
    ]
    assert row["needs_review"] is False
    assert row["review"]["naturalness_warnings"] == []
    assert row["review"]["retry_history"][0]["reason"] == "quality_review"
    assert "语序生硬" in row["review"]["retry_history"][0]["naturalness_warnings"][0]


def test_translate_entry_preview_keeps_original_when_quality_retry_breaks_tokens(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Back.b_test.name", "Test Deck"),
                FakeUnit(
                    "descriptions.Back.b_test.text[0]",
                    "{C:blue}+1{} hand every round",
                ),
            ]

    class QualityReview:
        needs_revision = True
        naturalness_warnings = ["语序需要调整"]
        meaning_warnings = []
        rewrite_hint = "每回合出牌次数+1"

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, **kwargs):
            class Result:
                name = "测试牌组"
                text = ["每回合出牌次数{C:blue}+1{}"]
                unlock = []
                token_errors = []

            return Result()

        def review_entry_translation(self, **kwargs):
            return QualityReview()

        def revise_entry_translation(self, **kwargs):
            class Result:
                name = "测试牌组"
                text = []
                unlock = []
                token_errors = ["text: Token count mismatch"]

            return Result()

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["ok"] is True
    assert row["token_errors"] == []
    assert row["text"] == ["每回合出牌次数{C:blue}+1{}"]
    assert row["needs_review"] is True
    assert row["review"]["naturalness_warnings"] == ["语序需要调整"]
    assert row["review"]["retry_history"][0]["retry_token_errors"] == ["text: Token count mismatch"]


def test_translate_entry_preview_retries_initial_token_errors(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Joker.j_planet.name", "Astrophysicist"),
                FakeUnit(
                    "descriptions.Joker.j_planet.text[0]",
                    "Create a {C:blue}Planet{} card",
                ),
            ]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, **kwargs):
            class Result:
                name = "天体物理学家"
                text = ["创建一张{C:blue}星球{}{C:inactive}牌"]
                unlock = []
                token_errors = ["text: Extra token: '{C:inactive}'"]

            return Result()

        def revise_entry_translation(self, *, review_feedback, **kwargs):
            assert "Extra token" in review_feedback

            class Result:
                name = "天体物理学家"
                text = ["创建一张{C:blue}星球{}牌"]
                unlock = []
                token_errors = []

            return Result()

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["ok"] is True
    assert row["token_errors"] == []
    assert row["text"] == ["创建一张{C:blue}星球{}牌"]
    assert row["review"]["retry_history"][0]["reason"] == "token_errors"
    assert row["review"]["retry_history"][0]["initial_token_errors"] == [
        "text: Extra token: '{C:inactive}'"
    ]


def test_translate_entry_preview_marks_token_errors_as_needs_review(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Back.b_test.name", "Test Deck"),
                FakeUnit("descriptions.Back.b_test.text[0]", "{C:blue}+1{} hand"),
            ]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, **kwargs):
            class Result:
                name = "测试牌组"
                text = []
                unlock = []
                token_errors = ["text: Token count mismatch"]

            return Result()

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["ok"] is False
    assert row["needs_review"] is True
    assert row["token_errors"] == ["text: Token count mismatch"]


def test_translate_entry_preview_mod_emits_review_tiers_and_brief_version(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            return [
                FakeUnit("descriptions.Joker.j_perkeo.name", "Perkeo"),
                FakeUnit(
                    "descriptions.Joker.j_perkeo.text[0]",
                    "Creates a {C:dark_edition}Negative{} copy",
                ),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class DenseRef:
        tm_entry_id = 200
        context_type = "joker_description_line"
        score = 0.77
        mod_id = "memory_mod"
        unit_key = "memory.key"
        source_text = "random consumable"
        target_text = "随机消耗牌"

    class GlossaryRef:
        tm_entry_id = 100
        context_type = "edition_name"
        score = 1.0
        mod_id = "balatro_origin"
        unit_key = "descriptions.Edition.e_negative.name"
        source_text = "Negative"
        target_text = "负片"

    class FakeRetrieval:
        references = [DenseRef()]

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, *, references, **kwargs):
            # tiers propagate into the references handed to the translator
            tiers = {r.source_text: r.tier for r in references}
            assert tiers["Negative"] == "locked"
            assert tiers["random consumable"] == "same_context"

            class Result:
                name = "Perkeo"
                # deliberate violation: Negative translated as 负面, not 负片
                text = ["创建{C:dark_edition}负面{}复制"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr(
        "app.cli.main.retrieve_glossary_references",
        lambda **kwargs: [GlossaryRef()],
    )
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr(
        "app.cli.main.build_locked_term_map",
        lambda db_path, mod_id=None: {"Negative": "负片"},
    )

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    row = rows[0]

    # tiered rag_refs
    assert row["rag_refs"][0]["tier"] == "locked"
    assert row["rag_refs"][0]["context_type"] == "edition_name"
    assert row["rag_refs"][1]["tier"] == "same_context"

    # review fields
    assert row["needs_review"] is True
    assert row["brief_version"].startswith("sha256:")
    violations = row["review"]["term_violations"]
    assert len(violations) == 1
    assert violations[0]["term"] == "Negative"
    assert violations[0]["expected"] == "负片"
    assert violations[0]["kind"] == "styled"
    # placeholder review sub-fields present for later phases
    assert row["review"]["naturalness_warnings"] == []
    assert row["review"]["meaning_warnings"] == []


def test_translate_entry_preview_marks_line_count_mismatch_as_table_apply_mode(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text("return {}", encoding="utf-8")
    output = tmp_path / "entry_preview.jsonl"

    class FakeUnit:
        def __init__(self, unit_key, source_text) -> None:
            self.unit_key = unit_key
            self.source_text = source_text

    class FakeExtractor:
        def extract_file(self, path):
            assert path == source
            return [
                FakeUnit("descriptions.Joker.j_test.name", "Test Joker"),
                FakeUnit("descriptions.Joker.j_test.text[0]", "One long line"),
            ]

    class FakeEmbedding:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeRetrieval:
        references = []

    class FakeTranslator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def translate_entry(self, **kwargs):
            class Result:
                name = "测试小丑"
                text = ["第一行", "第二行"]
                unlock = []
                token_errors = []

            return Result()

    monkeypatch.setattr("app.cli.main.LuaExtractor", FakeExtractor)
    monkeypatch.setattr("app.cli.main.OllamaEmbeddingClient", FakeEmbedding)
    monkeypatch.setattr("app.cli.main.QdrantTmStore", FakeStore)
    monkeypatch.setattr("app.cli.main.retrieve_references", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["ok"] is True
    assert rows[0]["needs_review"] is False
    assert rows[0]["patchable"] is False
    assert rows[0]["apply_mode"] == "table"
    assert rows[0]["apply_warnings"] == ["text line count mismatch: source=1, target=2"]
    assert rows[0]["patch_warnings"] == ["text line count mismatch: source=1, target=2"]


def test_apply_entry_preview_writes_only_safe_patchable_rows(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={
        Joker={
            j_safe={name="Safe Joker", text={"Gain +#1# Mult"}},
            j_review={name="Review Joker", text={"Needs review"}},
            j_unpatchable={name="Long Joker", text={"One line"}},
        },
    },
}
""",
        encoding="utf-8",
    )
    preview = tmp_path / "preview.jsonl"
    rows = [
        {
            "entry_key": "descriptions.Joker.j_safe",
            "ok": True,
            "patchable": True,
            "needs_review": False,
            "target_units": {
                "name": "descriptions.Joker.j_safe.name",
                "text": ["descriptions.Joker.j_safe.text[0]"],
                "unlock": [],
            },
            "name": "安全小丑",
            "text": ["获得 +#1# 倍率"],
            "unlock": [],
        },
        {
            "entry_key": "descriptions.Joker.j_review",
            "ok": True,
            "patchable": True,
            "needs_review": True,
            "target_units": {
                "name": "descriptions.Joker.j_review.name",
                "text": ["descriptions.Joker.j_review.text[0]"],
                "unlock": [],
            },
            "name": "待审小丑",
            "text": ["需要复审"],
            "unlock": [],
        },
        {
            "entry_key": "descriptions.Joker.j_unpatchable",
            "ok": True,
            "patchable": False,
            "needs_review": False,
            "target_units": {
                "name": "descriptions.Joker.j_unpatchable.name",
                "text": ["descriptions.Joker.j_unpatchable.text[0]"],
                "unlock": [],
            },
            "name": "长小丑",
            "text": ["第一行", "第二行"],
            "unlock": [],
        },
    ]
    preview.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "localization" / "zh_CN.lua"
    monkeypatch.setattr("app.cli.main.validate_file", lambda path: (True, ""))

    result = CliRunner().invoke(
        app,
        [
            "apply-entry-preview",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--input",
            str(preview),
            "--output",
            "localization/zh_CN.lua",
        ],
    )

    assert result.exit_code == 0, result.output
    patched = output.read_text(encoding="utf-8")
    assert "安全小丑" in patched
    assert "获得 +#1# 倍率" in patched
    assert "Review Joker" in patched
    assert "待审小丑" not in patched
    assert "Long Joker" in patched
    assert "长小丑" not in patched
    assert "applied_entries=1" in result.output
    assert "skipped_needs_review=1" in result.output
    assert "skipped_requires_table_level=1" in result.output
    assert "skipped_blocked=0" in result.output


def test_apply_entry_preview_keeps_existing_output_when_lua_validation_fails(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={Joker={j_test={name="Test Joker", text={"Hello"}}}},
}
""",
        encoding="utf-8",
    )
    preview = tmp_path / "preview.jsonl"
    preview.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Joker.j_test",
                "ok": True,
                "patchable": True,
                "needs_review": False,
                "target_units": {
                    "name": "descriptions.Joker.j_test.name",
                    "text": ["descriptions.Joker.j_test.text[0]"],
                    "unlock": [],
                },
                "name": "测试小丑",
                "text": ["你好"],
                "unlock": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "localization" / "zh_CN.lua"
    output.write_text("keep me", encoding="utf-8")
    monkeypatch.setattr("app.cli.main.validate_file", lambda path: (False, "bad lua"))

    result = CliRunner().invoke(
        app,
        [
            "apply-entry-preview",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--input",
            str(preview),
            "--output",
            "localization/zh_CN.lua",
        ],
    )

    assert result.exit_code == 1
    assert "Lua validation failed: bad lua" in result.output
    assert output.read_text(encoding="utf-8") == "keep me"
    assert not output.with_name(output.name + ".tmp").exists()


def test_apply_entry_preview_normalizes_embedded_newlines_for_unit_patch(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={Other={p_test={name="Test Pack", text={"Choose one"}}}},
}
""",
        encoding="utf-8",
    )
    preview = tmp_path / "preview.jsonl"
    preview.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Other.p_test",
                "ok": True,
                "patchable": True,
                "needs_review": False,
                "target_units": {
                    "name": "descriptions.Other.p_test.name",
                    "text": ["descriptions.Other.p_test.text[0]"],
                    "unlock": [],
                },
                "name": "神圣包",
                "text": ["从最多{C:attention}#2#{}张神圣牌中\n"],
                "unlock": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "localization" / "zh_CN.lua"
    monkeypatch.setattr("app.cli.main.validate_file", lambda path: (True, ""))

    result = CliRunner().invoke(
        app,
        [
            "apply-entry-preview",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--input",
            str(preview),
            "--output",
            "localization/zh_CN.lua",
        ],
    )

    assert result.exit_code == 0, result.output
    patched = output.read_text(encoding="utf-8")
    assert '"从最多{C:attention}#2#{}张神圣牌中"' in patched
    assert '"从最多{C:attention}#2#{}张神圣牌中\n"' not in patched


def test_apply_entry_preview_table_level_applies_line_count_changes(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "localization" / "default.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={
        Joker={
            j_long={
                name="Long Joker",
                text={"One line"},
                unlock={"Find it"},
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    preview = tmp_path / "preview.jsonl"
    preview.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Joker.j_long",
                "ok": True,
                "patchable": False,
                "apply_mode": "table",
                "needs_review": False,
                "patch_warnings": [
                    "text line count mismatch: source=1, target=2",
                    "unlock line count mismatch: source=1, target=2",
                ],
                "target_units": {
                    "name": "descriptions.Joker.j_long.name",
                    "text": ["descriptions.Joker.j_long.text[0]"],
                    "unlock": ["descriptions.Joker.j_long.unlock[0]"],
                },
                "name": "长小丑",
                "text": ["第一行", "第二行"],
                "unlock": ["找到它", "再打出它"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "localization" / "zh_CN.lua"
    monkeypatch.setattr("app.cli.main.validate_file", lambda path: (True, ""))

    result = CliRunner().invoke(
        app,
        [
            "apply-entry-preview",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/default.lua",
            "--input",
            str(preview),
            "--output",
            "localization/zh_CN.lua",
            "--table-level",
        ],
    )

    assert result.exit_code == 0, result.output
    patched = output.read_text(encoding="utf-8")
    assert "长小丑" in patched
    assert '"第一行"' in patched
    assert '"第二行"' in patched
    assert '"找到它"' in patched
    assert '"再打出它"' in patched
    assert "applied_entries=1" in result.output
    assert "applied_table=1" in result.output
    assert "skipped_requires_table_level=0" in result.output
    assert "skipped_blocked=0" in result.output


def test_audit_entry_output_reports_generic_post_apply_issues(tmp_path) -> None:
    source = tmp_path / "localization" / "en-us.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={
        Other={
            m_custom={name="Custom Seal", text={"Creates a card"}},
        },
    },
    misc={
        labels={m_custom="Custom Seal"},
        v_dictionary={a_stock="+#1# Stock"},
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "localization" / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions={
        Other={
            m_custom={name="自定义蜡封", text={"Creates a card"}},
        },
    },
    misc={
        labels={m_custom="自定义封印"},
        v_dictionary={a_stock="+#1# Stock"},
    },
}
""",
        encoding="utf-8",
    )
    preview = tmp_path / "preview.jsonl"
    preview.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "entry_key": "descriptions.Other.m_custom",
                        "ok": True,
                        "needs_review": True,
                        "apply_mode": "unit",
                    }
                ),
                json.dumps(
                    {
                        "entry_key": "misc.v_dictionary.a_stock",
                        "ok": False,
                        "needs_review": True,
                        "apply_mode": "blocked",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "audit.json"

    result = CliRunner().invoke(
        app,
        [
            "audit-entry-output",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/en-us.lua",
            "--target",
            "localization/zh_CN.lua",
            "--preview",
            str(preview),
            "--json-output",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "failed=1" in result.output
    assert "needs_review=1" in result.output
    assert "residual_english=2" in result.output
    assert "untranslated=2" in result.output
    assert "label_name_mismatches=1" in result.output
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["needs_review"] == 1
    mismatch = payload["label_name_mismatches"][0]
    assert mismatch["entry_key"] == "m_custom"
    assert mismatch["description_entry_key"] == "descriptions.Other.m_custom"
    assert mismatch["label_unit_key"] == "misc.labels.m_custom"
    assert mismatch["description_name"] == "自定义蜡封"
    assert mismatch["label"] == "自定义封印"


def test_audit_rerun_keys_writes_generic_entry_key_list(tmp_path) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "failed_rows": [
                    {"entry_key": "descriptions.Joker.j_failed"},
                ],
                "needs_review_rows": [
                    {"entry_key": "descriptions.Joker.j_review"},
                ],
                "residual_english": [
                    {
                        "unit_key": "descriptions.Other.p_pack.text[0]",
                        "severity": "rerun",
                    },
                    {
                        "unit_key": "descriptions.Joker.j_acronym.name",
                        "severity": "review",
                    },
                ],
                "untranslated_units": [
                    {
                        "unit_key": "misc.v_dictionary.a_stock",
                        "severity": "rerun",
                    },
                    {
                        "unit_key": "descriptions.Joker.j_rna.name",
                        "severity": "review",
                    },
                ],
                "label_name_mismatches": [
                    {
                        "entry_key": "m_custom",
                        "description_entry_key": "descriptions.Other.m_custom",
                        "label_unit_key": "misc.labels.m_custom",
                    },
                ],
                "name_inconsistencies": [
                    {
                        "source": "Sample",
                        "entry_keys": [
                            "descriptions.Other.sample",
                            "misc.labels.sample",
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "rerun_keys.txt"

    result = CliRunner().invoke(
        app,
        [
            "audit-rerun-keys",
            "--audit",
            str(audit),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8").splitlines() == [
        "descriptions.Joker.j_failed",
        "descriptions.Joker.j_review",
        "descriptions.Other.p_pack",
        "misc.v_dictionary.a_stock",
        "descriptions.Other.m_custom",
        "misc.labels.m_custom",
        "descriptions.Other.sample",
        "misc.labels.sample",
    ]
    assert "Wrote 8 rerun entry keys" in result.output


def test_audit_entry_output_classifies_residual_english_severity(tmp_path) -> None:
    source = tmp_path / "localization" / "en-us.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={
        Joker={
            j_english={name="English Joker", text={"Gain Chips"}},
            j_mixed={name="Mixed Joker", text={"Gain Chips"}},
            j_acronym={name="H.A.M Radio", text={"Uses code"}},
            j_rna={name="RNA", text={"Copies DNA"}},
        },
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "localization" / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions={
        Joker={
            j_english={name="English Joker", text={"Gain Chips"}},
            j_mixed={name="混合小丑", text={"获得 Chips"}},
            j_acronym={name="H.A.M 电台", text={"使用代码"}},
            j_rna={name="RNA", text={"复制 DNA"}},
        },
    },
}
""",
        encoding="utf-8",
    )
    report = tmp_path / "audit.json"

    result = CliRunner().invoke(
        app,
        [
            "audit-entry-output",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/en-us.lua",
            "--target",
            "localization/zh_CN.lua",
            "--json-output",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_text(encoding="utf-8"))
    by_key = {item["unit_key"]: item for item in payload["residual_english"]}
    assert by_key["descriptions.Joker.j_english.name"]["severity"] == "rerun"
    assert by_key["descriptions.Joker.j_english.text[0]"]["severity"] == "rerun"
    assert by_key["descriptions.Joker.j_mixed.text[0]"]["severity"] == "rerun"
    assert by_key["descriptions.Joker.j_acronym.name"]["severity"] == "review"
    assert by_key["descriptions.Joker.j_rna.name"]["severity"] == "review"
    untranslated = {item["unit_key"]: item for item in payload["untranslated_units"]}
    assert untranslated["descriptions.Joker.j_english.name"]["severity"] == "rerun"
    assert untranslated["descriptions.Joker.j_rna.name"]["severity"] == "review"


def test_audit_entry_output_reruns_lowercase_gameplay_residuals(tmp_path) -> None:
    source = tmp_path / "localization" / "en-us.lua"
    source.parent.mkdir()
    source.write_text(
        """return {
    descriptions={
        Tarot={
            c_one={name="One", text={"Convert one card"}},
        },
        Edition={
            e_null={name="Null", text={"+null chips"}},
        },
    },
}
""",
        encoding="utf-8",
    )
    target = tmp_path / "localization" / "zh_CN.lua"
    target.write_text(
        """return {
    descriptions={
        Tarot={
            c_one={name="一", text={"转化{C:attention}one{}张牌"}},
        },
        Edition={
            e_null={name="空", text={"{C:blue}+null{}筹码"}},
        },
    },
}
""",
        encoding="utf-8",
    )
    report = tmp_path / "audit.json"

    result = CliRunner().invoke(
        app,
        [
            "audit-entry-output",
            "--repo",
            str(tmp_path),
            "--source",
            "localization/en-us.lua",
            "--target",
            "localization/zh_CN.lua",
            "--json-output",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_text(encoding="utf-8"))
    by_key = {item["unit_key"]: item for item in payload["residual_english"]}
    assert by_key["descriptions.Tarot.c_one.text[0]"]["severity"] == "rerun"
    assert by_key["descriptions.Edition.e_null.text[0]"]["severity"] == "rerun"


def test_merge_entry_preview_replaces_rows_by_entry_key(tmp_path) -> None:
    base = tmp_path / "base.jsonl"
    updates = tmp_path / "updates.jsonl"
    output = tmp_path / "merged.jsonl"
    base.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"entry_key": "a", "text": ["old a"]},
                {"entry_key": "b", "text": ["old b"]},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    updates.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"entry_key": "b", "text": ["new b"]},
                {"entry_key": "c", "text": ["new c"]},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "merge-entry-preview",
            "--base",
            str(base),
            "--updates",
            str(updates),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"entry_key": "a", "text": ["old a"]},
        {"entry_key": "b", "text": ["new b"]},
        {"entry_key": "c", "text": ["new c"]},
    ]
    assert "replaced=1" in result.output
    assert "appended=1" in result.output


def test_merge_entry_preview_safe_updates_preserve_base_on_failed_update(
    tmp_path,
) -> None:
    base = tmp_path / "base.jsonl"
    updates = tmp_path / "updates.jsonl"
    output = tmp_path / "merged.jsonl"
    base.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Enhanced.m_div",
                "ok": True,
                "needs_review": False,
                "apply_mode": "table",
                "text": ["{X:mult,C:white}X#1#{}倍率"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    updates.write_text(
        json.dumps(
            {
                "entry_key": "descriptions.Enhanced.m_div",
                "ok": False,
                "needs_review": True,
                "apply_mode": "blocked",
                "token_errors": ["text: Token count mismatch"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "merge-entry-preview",
            "--base",
            str(base),
            "--updates",
            str(updates),
            "--output",
            str(output),
            "--safe-updates",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "entry_key": "descriptions.Enhanced.m_div",
            "ok": True,
            "needs_review": False,
            "apply_mode": "table",
            "text": ["{X:mult,C:white}X#1#{}倍率"],
        }
    ]
    assert "replaced=0" in result.output
    assert "skipped=1" in result.output


def test_merge_entry_preview_can_apply_consistency_after_merge(tmp_path) -> None:
    base = tmp_path / "base.jsonl"
    updates = tmp_path / "updates.jsonl"
    output = tmp_path / "merged.jsonl"
    source_body = {
        "text": [
            "(lvl:#1#+i) Imaginary Level Up",
            "{C:attention}#4#",
            "{C:red}X#2#{} Mult and",
            "{C:blue}X#3#{} chips",
        ],
        "unlock": [],
    }
    base_rows = [
        {
            "entry_key": "descriptions.Familiar_Planets.c_good",
            "ok": True,
            "name": "好",
            "text": ["(等级：#1#+i) 虚数升级", "{C:attention}#4# {C:red}X#2#{}倍率"],
            "unlock": [],
            "target_units": {
                "name": "descriptions.Familiar_Planets.c_good.name",
                "text": [
                    "descriptions.Familiar_Planets.c_good.text[0]",
                    "descriptions.Familiar_Planets.c_good.text[1]",
                    "descriptions.Familiar_Planets.c_good.text[2]",
                    "descriptions.Familiar_Planets.c_good.text[3]",
                ],
                "unlock": [],
            },
            "patchable": False,
            "patch_warnings": ["text line count mismatch: source=4, target=2"],
            "apply_mode": "table",
            "source": {"name": "Good", **source_body},
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
        {
            "entry_key": "descriptions.Familiar_Planets.c_bad",
            "ok": True,
            "name": "坏",
            "text": ["(lvl:#1#+i) 虚数升级", "Imaginary 手牌"],
            "unlock": [],
            "target_units": {
                "name": "descriptions.Familiar_Planets.c_bad.name",
                "text": [
                    "descriptions.Familiar_Planets.c_bad.text[0]",
                    "descriptions.Familiar_Planets.c_bad.text[1]",
                    "descriptions.Familiar_Planets.c_bad.text[2]",
                    "descriptions.Familiar_Planets.c_bad.text[3]",
                ],
                "unlock": [],
            },
            "patchable": False,
            "patch_warnings": ["text line count mismatch: source=4, target=2"],
            "apply_mode": "table",
            "source": {"name": "Bad", **source_body},
            "review": {
                "term_violations": [],
                "consistency_warnings": [],
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
                "retry_history": [],
            },
            "needs_review": False,
        },
    ]
    base.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in base_rows) + "\n",
        encoding="utf-8",
    )
    updates.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "merge-entry-preview",
            "--base",
            str(base),
            "--updates",
            str(updates),
            "--output",
            str(output),
            "--apply-consistency",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[1]["text"] == rows[0]["text"]
    assert rows[1]["needs_review"] is False
    assert "consistency=1" in result.output


def test_translate_entry_loop_runs_full_then_rerun_until_clean(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "Familiar"
    source = repo / "localization" / "en-us.lua"
    source.parent.mkdir(parents=True)
    source.write_text("return {}\n", encoding="utf-8")
    work_dir = tmp_path / "loop"
    output = Path("localization/zh_CN.lua")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_translate_entry_preview_mod(**kwargs):
        calls.append(("translate", kwargs))
        out = kwargs["output"]
        assert isinstance(out, Path)
        if kwargs.get("entry_keys_file") is None:
            rows = [{"entry_key": "descriptions.Joker.j_one", "ok": True}]
        else:
            rows = [{"entry_key": "descriptions.Joker.j_one", "ok": True, "name": "一"}]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def fake_apply_entry_preview(**kwargs):
        calls.append(("apply", kwargs))
        out = kwargs["output"]
        assert isinstance(out, Path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"-- generated from {kwargs['input'].name}\n", encoding="utf-8")

    def fake_audit_entry_output(**kwargs):
        calls.append(("audit", kwargs))
        json_output = kwargs["json_output"]
        assert isinstance(json_output, Path)
        if kwargs["target"].name == "round_00_zh_CN.lua":
            report = {
                "summary": {"needs_review": 1, "residual_english": 0},
                "failed_rows": [],
                "needs_review_rows": [
                    {"entry_key": "descriptions.Joker.j_one", "apply_mode": "table"}
                ],
                "residual_english": [],
                "untranslated_units": [],
                "label_name_mismatches": [],
                "name_inconsistencies": [],
            }
        else:
            report = {
                "summary": {"needs_review": 0, "residual_english": 0},
                "failed_rows": [],
                "needs_review_rows": [],
                "residual_english": [],
                "untranslated_units": [],
                "label_name_mismatches": [],
                "name_inconsistencies": [],
            }
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    def fake_merge_entry_preview(**kwargs):
        calls.append(("merge", kwargs))
        assert kwargs["safe_updates"] is True
        assert kwargs["apply_consistency"] is True
        output_path = kwargs["output"]
        assert isinstance(output_path, Path)
        output_path.write_text(kwargs["updates"].read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        "app.cli.main.translate_entry_preview_mod", fake_translate_entry_preview_mod
    )
    monkeypatch.setattr("app.cli.main.apply_entry_preview", fake_apply_entry_preview)
    monkeypatch.setattr("app.cli.main.audit_entry_output", fake_audit_entry_output)
    monkeypatch.setattr("app.cli.main.merge_entry_preview", fake_merge_entry_preview)

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-loop",
            "--repo",
            str(repo),
            "--source",
            "localization/en-us.lua",
            "--output",
            str(output),
            "--work-dir",
            str(work_dir),
            "--limit",
            "9999",
            "--top-k",
            "5",
            "--max-width",
            "18",
            "--concurrency",
            "4",
            "--max-rounds",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [name for name, _ in calls] == [
        "translate",
        "apply",
        "audit",
        "translate",
        "merge",
        "apply",
        "audit",
    ]
    assert (repo / output).read_text(encoding="utf-8") == (
        "-- generated from round_01_preview.jsonl\n"
    )
    manifest = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_rounds"] == 2
    assert manifest["stopped_reason"] == "no_rerun_keys"
    assert manifest["final_audit_summary"] == {
        "needs_review": 0,
        "residual_english": 0,
    }
    assert manifest["rounds"][0]["preview"] == str(work_dir / "round_00_preview.jsonl")
    assert manifest["rounds"][1]["rerun"] == str(work_dir / "round_01_rerun.jsonl")
    assert (work_dir / "round_00_rerun_keys.txt").read_text(encoding="utf-8").splitlines() == [
        "descriptions.Joker.j_one"
    ]
    assert "Translation loop complete" in result.output
    assert "stopped_reason=no_rerun_keys" in result.output


def test_translate_entry_loop_resolves_relative_work_dir_before_apply(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = Path("Familiar")
    source = repo / "localization" / "en-us.lua"
    source.parent.mkdir(parents=True)
    source.write_text("return {}\n", encoding="utf-8")
    calls: list[tuple[str, Path]] = []

    def fake_translate_entry_preview_mod(**kwargs):
        out = kwargs["output"]
        assert isinstance(out, Path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"entry_key": "descriptions.Joker.j_one", "ok": True}) + "\n",
            encoding="utf-8",
        )

    def fake_apply_entry_preview(**kwargs):
        out = kwargs["output"]
        assert isinstance(out, Path)
        calls.append(("apply_output", out))
        # Match apply-entry-preview behavior: relative output is resolved inside repo.
        actual_output = out if out.is_absolute() else kwargs["repo"] / out
        actual_output.parent.mkdir(parents=True, exist_ok=True)
        actual_output.write_text("-- generated\n", encoding="utf-8")

    def fake_audit_entry_output(**kwargs):
        json_output = kwargs["json_output"]
        assert isinstance(json_output, Path)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(
                {
                    "summary": {"needs_review": 0},
                    "failed_rows": [],
                    "needs_review_rows": [],
                    "residual_english": [],
                    "untranslated_units": [],
                    "label_name_mismatches": [],
                    "name_inconsistencies": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "app.cli.main.translate_entry_preview_mod", fake_translate_entry_preview_mod
    )
    monkeypatch.setattr("app.cli.main.apply_entry_preview", fake_apply_entry_preview)
    monkeypatch.setattr("app.cli.main.audit_entry_output", fake_audit_entry_output)

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-loop",
            "--repo",
            str(repo),
            "--source",
            "localization/en-us.lua",
            "--output",
            "localization/zh_CN_loop.lua",
            "--work-dir",
            "relative_loop",
            "--max-rounds",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ("apply_output", tmp_path / "relative_loop" / "round_00_zh_CN.lua")
    ]
    assert (repo / "localization" / "zh_CN_loop.lua").read_text(
        encoding="utf-8"
    ) == "-- generated\n"


def test_llm_config_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_TRANSLATION_MODEL", "custom-model")

    base_url, model = _llm_config()

    assert base_url == "https://llm.example/v1"
    assert model == "custom-model"


def test_llm_config_defaults_to_openai_compatible_base_url(monkeypatch) -> None:
    monkeypatch.setattr("app.cli.main.load_dotenv", lambda: None)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_TRANSLATION_MODEL", raising=False)

    base_url, model = _llm_config()

    assert base_url == "https://api.openai.com/v1"
    assert model


def test_llm_concurrency_defaults_to_one_and_reads_environment(monkeypatch) -> None:
    monkeypatch.delenv("LLM_CONCURRENCY", raising=False)
    assert _llm_concurrency() == 1

    monkeypatch.setenv("LLM_CONCURRENCY", "3")
    assert _llm_concurrency() == 3
    assert _llm_concurrency(2) == 2
