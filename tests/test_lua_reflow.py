from app.lua.reflow import reflow_zh_text, visual_width


def test_visual_width_ignores_style_tokens_and_counts_variables_as_one() -> None:
    assert visual_width("{C:mult}倍率{}+#1#") == 6


def test_reflow_zh_text_does_not_split_tokens() -> None:
    lines = reflow_zh_text(
        "在商店结束时，复制一张你拥有的随机{C:attention}消耗牌{}并赋予{C:dark_edition}负片{}版本",
        max_width=18,
    )

    assert len(lines) > 1
    assert "".join(lines) == "在商店结束时，复制一张你拥有的随机{C:attention}消耗牌{}并赋予{C:dark_edition}负片{}版本"
    assert all("{C:" not in line or "}" in line for line in lines)
    assert all(visual_width(line) <= 18 for line in lines)


def test_reflow_zh_text_keeps_punctuation_off_line_start_when_possible() -> None:
    lines = reflow_zh_text("获得倍率，并在回合结束时重置", max_width=8)

    assert all(not line.startswith(("，", "。", "、", "；", "：")) for line in lines)


def test_reflow_zh_text_does_not_split_ascii_words() -> None:
    lines = reflow_zh_text(
        "使用这张小丑牌在{C:attention}Sweaty {C:attention}Stake{}难度下获胜",
        max_width=18,
    )

    assert "".join(lines) == "使用这张小丑牌在{C:attention}Sweaty {C:attention}Stake{}难度下获胜"
    assert any("Sweaty" in line for line in lines)
    assert any("Stake" in line for line in lines)
    assert not any(line.endswith(("Sw", "Swe", "Swea", "Sweat")) for line in lines)
    assert not any(line.startswith(("eaty", "aty", "ty", "y ")) for line in lines)
    assert not any(line.endswith(("St", "Sta", "Stak")) for line in lines)
    assert not any(line.startswith(("ake", "ke")) for line in lines)


def test_reflow_zh_text_does_not_split_common_balatro_terms() -> None:
    lines = reflow_zh_text(
        "将 {C:attention}#1#{} 张选定的卡牌增强为 {C:attention}污渍玻璃牌{}，当前为{C:money}$#2#{}",
        max_width=18,
    )

    assert "".join(lines) == (
        "将 {C:attention}#1#{} 张选定的卡牌增强为 {C:attention}污渍玻璃牌{}，当前为{C:money}$#2#{}"
    )
    joined_for_review = " ".join(lines)
    assert "卡 牌" not in joined_for_review
    assert "污渍玻璃 牌" not in joined_for_review
    assert "当 前" not in joined_for_review


def test_reflow_zh_text_keeps_styled_spans_and_parentheses_together() -> None:
    lines = reflow_zh_text(
        "重新触发{C:attention}每张{}打出的点数为{C:attention}无点数{}的牌"
        "{C:inactive}（如果你有一手完美的牌）{}",
        max_width=18,
    )

    joined_for_review = " ".join(lines)
    assert any("{C:attention}无点数{}" in line for line in lines)
    assert "{C:inactive}（如果你有一手完美的牌）{}" in lines
    assert "{C:attention}无 点数{}" not in joined_for_review
    assert "（如果 你有一手完美的牌）" not in joined_for_review
