from typer.testing import CliRunner
import json
import threading
import time

from app.cli.main import _llm_concurrency, _llm_config, app


def test_cli_has_rag_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "import-local-tm" in result.output
    assert "sync-vectors" in result.output
    assert "search" in result.output
    assert "rag-preview-mod" in result.output
    assert "translate-preview-mod" in result.output
    assert "translate-entry-preview-mod" in result.output


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
        ):
            assert name_text == "Test Joker"
            assert body_text == "Gain +#1# Mult at end of round"
            assert unlock_text == "Find this Joker"
            assert references[0].target_text == "获得 +#1# 倍率"
            assert max_width == 18

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
    seen_queries = []

    def fake_retrieve_references(**kwargs):
        seen_queries.append(kwargs["query_text"])
        assert kwargs["top_k"] == 3
        return FakeRetrieval()

    monkeypatch.setattr("app.cli.main.retrieve_references", fake_retrieve_references)

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
    monkeypatch.setattr(
        "app.cli.main.retrieve_glossary_references",
        lambda **kwargs: [GlossaryRef()],
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


def test_translate_entry_preview_marks_line_count_mismatch_unpatchable(
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
    assert rows[0]["patchable"] is False
    assert rows[0]["patch_warnings"] == ["text line count mismatch: source=1, target=2"]


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
