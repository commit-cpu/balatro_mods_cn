from app.lua.reflow import reflow_zh_text, visual_width


def test_visual_width_ignores_style_tokens_but_counts_variables() -> None:
    assert visual_width("{C:mult}倍率{}+#1#") == 8


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
