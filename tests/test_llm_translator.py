from app.llm.translator import TranslationReference, Translator


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = None

    def chat_json(self, messages):
        self.messages = messages
        return {"translation": self.content}


def test_translator_reports_token_errors_without_partial_restore() -> None:
    client = FakeClient("[[TOKEN_0]]+#1#? no")
    translator = Translator(client=client, model="deepseek-chat")

    result = translator.translate(
        source_text="{C:mult}+#1#{} Mult",
        references=[
            TranslationReference(
                source_text="{C:mult}+#1#{} Mult",
                target_text="{C:mult}+#1#{}倍率",
                score=0.91,
            )
        ],
    )

    assert result.candidate_text == "[[TOKEN_0]]+#1#? no"
    assert result.token_errors
    assert client.messages is not None
    assert "[[TOKEN_0]]+[[TOKEN_1]][[TOKEN_2]] Mult" in client.messages[-1]["content"]


def test_translator_reports_no_token_errors_for_valid_output() -> None:
    client = FakeClient("[[TOKEN_0]]+[[TOKEN_1]][[TOKEN_2]]倍率")
    translator = Translator(client=client, model="deepseek-chat")

    result = translator.translate(source_text="{C:mult}+#1#{} Mult", references=[])

    assert result.candidate_text == "{C:mult}+#1#{}倍率"
    assert result.token_errors == []


def test_translate_entry_reflows_combined_text() -> None:
    class EntryClient:
        def chat_json(self, messages):
            assert "Creates a [[TOKEN_0]]Negative[[TOKEN_1]] copy of a random [[TOKEN_2]]consumable[[TOKEN_3]]" in messages[-1]["content"]
            return {
                "name": "帕奇欧",
                "text": "[[TOKEN_0]]负片[[TOKEN_1]]复制一张随机[[TOKEN_2]]消耗牌[[TOKEN_3]]",
                "unlock": "",
            }

    translator = Translator(client=EntryClient(), model="deepseek-chat")

    result = translator.translate_entry(
        name_text="Perkeo",
        body_text="Creates a {C:dark_edition}Negative{} copy of a random {C:attention}consumable{}",
        unlock_text="",
        references=[],
        max_width=18,
    )

    assert result.name == "帕奇欧"
    assert "".join(result.text) == "{C:dark_edition}负片{}复制一张随机{C:attention}消耗牌{}"
    assert len(result.text) > 1
    assert result.token_errors == []


def test_translate_entry_includes_style_references() -> None:
    class EntryClient:
        def __init__(self) -> None:
            self.content = None

        def chat_json(self, messages):
            self.content = messages[-1]["content"]
            return {
                "name": "帕奇欧",
                "text": "在离开商店时随机复制一张消耗牌",
                "unlock": "",
            }

    client = EntryClient()
    translator = Translator(client=client, model="deepseek-chat")

    translator.translate_entry(
        name_text="Perkeo",
        body_text="Creates a copy",
        unlock_text="",
        references=[],
        max_width=80,
        style_examples="Balatro Simplified Chinese style references:\n- EN: Creates a copy\n  ZH: 随机复制一张",
    )

    assert "Balatro Simplified Chinese style references" in client.content
    assert "ZH: 随机复制一张" in client.content


def test_translate_entry_reports_reordered_token_errors() -> None:
    class EntryClient:
        def chat_json(self, messages):
            return {
                "name": "帕奇欧",
                "text": "创建一张随机[[TOKEN_2]]消耗牌[[TOKEN_3]]的[[TOKEN_0]]负片[[TOKEN_1]]复制牌",
                "unlock": "",
            }

    translator = Translator(client=EntryClient(), model="deepseek-chat")

    result = translator.translate_entry(
        name_text="Perkeo",
        body_text="Creates a {C:dark_edition}Negative{} copy of a random {C:attention}consumable{}",
        unlock_text="",
        references=[],
        max_width=18,
    )

    assert "".join(result.text) == "创建一张随机{C:attention}消耗牌{}的{C:dark_edition}负片{}复制牌"
    assert result.token_errors == []


def test_references_rendered_as_tiered_sections() -> None:
    class CaptureClient:
        def __init__(self) -> None:
            self.content = None

        def chat_json(self, messages):
            self.content = messages[-1]["content"]
            return {"translation": "x"}

    client = CaptureClient()
    translator = Translator(client=client, model="m")
    translator.translate(
        source_text="Negative",
        references=[
            TranslationReference("Negative", "负片", 1.0, tier="locked"),
            TranslationReference("copy", "复制", 0.8, tier="same_context"),
            TranslationReference("shop", "商店", 0.5, tier="loose"),
        ],
    )

    assert "Locked glossary:" in client.content
    assert "Same-context references:" in client.content
    assert "Loose references:" in client.content
    # locked ref content present under its section
    assert "负片" in client.content
    # order: locked before same_context before loose
    assert client.content.index("Locked glossary:") < client.content.index(
        "Same-context references:"
    ) < client.content.index("Loose references:")


def test_empty_references_render_none() -> None:
    class CaptureClient:
        def __init__(self) -> None:
            self.content = None

        def chat_json(self, messages):
            self.content = messages[-1]["content"]
            return {"translation": "x"}

    client = CaptureClient()
    translator = Translator(client=client, model="m")
    translator.translate(source_text="Negative", references=[])

    assert "(none)" in client.content
    assert "Locked glossary:" not in client.content


def test_review_entry_translation_parses_quality_feedback() -> None:
    class ReviewClient:
        def __init__(self) -> None:
            self.content = None

        def chat_json(self, messages):
            self.content = messages[-1]["content"]
            return {
                "needs_revision": True,
                "naturalness_warnings": ["语序生硬"],
                "meaning_warnings": [],
                "rewrite_hint": "改成打出时 +2 手牌上限，回合结束时重置。",
            }

    client = ReviewClient()
    translator = Translator(client=client, model="m")

    review = translator.review_entry_translation(
        name_text="Nitro",
        body_text="{C:attention}+2{} hand size when {C:attention}played{}",
        unlock_text="",
        name="Nitro",
        text=["{C:attention}+2{}手牌上限，当{C:attention}打出{}时"],
        unlock=[],
        references=[],
    )

    assert review.needs_revision is True
    assert review.naturalness_warnings == ["语序生硬"]
    assert "Candidate description" in client.content


def test_review_entry_translation_does_not_insert_spaces_between_reflowed_lines() -> None:
    class ReviewClient:
        def __init__(self) -> None:
            self.content = None

        def chat_json(self, messages):
            self.content = messages[-1]["content"]
            return {
                "needs_revision": False,
                "naturalness_warnings": [],
                "meaning_warnings": [],
                "rewrite_hint": "",
            }

    client = ReviewClient()
    translator = Translator(client=client, model="m")

    translator.review_entry_translation(
        name_text="Example",
        body_text="Enhance card",
        unlock_text="",
        name="示例",
        text=["将{C:attention}#1#{}张选定的卡", "牌增强为玻璃牌"],
        unlock=[],
        references=[],
    )

    assert "Candidate description:\n将{C:attention}#1#{}张选定的卡牌增强为玻璃牌" in client.content
    assert "卡 牌" not in client.content


def test_revise_entry_translation_restores_tokens() -> None:
    class RevisionClient:
        def chat_json(self, messages):
            assert "Reviewer feedback:" in messages[-1]["content"]
            return {
                "name": "Nitro",
                "text": "[[TOKEN_2]]打出[[TOKEN_3]]时[[TOKEN_0]]+2[[TOKEN_1]]手牌上限，回合结束时[[TOKEN_4]]重置[[TOKEN_5]][[TOKEN_6]]",
                "unlock": "",
            }

    translator = Translator(client=RevisionClient(), model="m")

    result = translator.revise_entry_translation(
        name_text="Nitro",
        body_text="{C:attention}+2{} hand size when {C:attention}played{} {C:attention}Resets{} at end of round{}",
        unlock_text="",
        current_name="Nitro",
        current_text=["{C:attention}+2{}手牌上限，当{C:attention}打出{}时"],
        current_unlock=[],
        review_feedback="语序生硬",
        references=[],
        max_width=80,
    )

    assert "".join(result.text) == (
        "{C:attention}打出{}时{C:attention}+2{}手牌上限，"
        "回合结束时{C:attention}重置{}{}"
    )
    assert result.token_errors == []


def test_revise_entry_translation_protects_current_translation_tokens() -> None:
    class RevisionClient:
        def __init__(self) -> None:
            self.content = ""
            self.system = ""

        def chat_json(self, messages):
            self.system = messages[0]["content"]
            self.content = messages[-1]["content"]
            return {
                "name": "负片示例",
                "text": "生成一张[[TOKEN_0]]负片[[TOKEN_1]]复制牌",
                "unlock": "",
            }

    client = RevisionClient()
    translator = Translator(client=client, model="m")

    result = translator.revise_entry_translation(
        name_text="Negative Example",
        body_text="Creates a {C:dark_edition}Negative{} copy",
        unlock_text="",
        current_name="负片示例",
        current_text=["创建一张{C:dark_edition}负片{}复制牌"],
        current_unlock=[],
        review_feedback="改成更自然的语序",
        references=[],
        max_width=80,
    )

    assert "Current description:\n创建一张[[TOKEN_0]]负片[[TOKEN_1]]复制牌" in client.content
    assert "Do not copy raw Balatro tokens like {C:attention}" in client.system
    assert "".join(result.text) == "生成一张{C:dark_edition}负片{}复制牌"
    assert result.token_errors == []
