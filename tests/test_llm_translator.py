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
