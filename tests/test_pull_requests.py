from app.github.mod_config import GitRepoRef, ModConfig
from app.github.pull_requests import pr_body


def test_pr_body_is_bilingual_with_english_first() -> None:
    mod = ModConfig(
        id="example_mod",
        origin=GitRepoRef(owner="upstream-owner", repo="example-mod", branch="main"),
        fork=GitRepoRef(owner="bot-owner", repo="example-mod", branch="main"),
        publish_mode="upstream_pr",
        source_locale_paths=["localization/en-us.lua"],
        target_locale_path="localization/zh_CN.lua",
        poll_minutes=360,
        parser_profile="steamodded_lua_v1",
    )

    body = pr_body(mod, "abcdef1234567890", 42)

    assert body.startswith("## Simplified Chinese localization update")
    assert "This PR updates the Simplified Chinese localization" in body
    assert "- Translation units updated: **42**" in body
    assert "- Target file: `localization/zh_CN.lua`" in body
    assert "## 简体中文翻译更新" in body
    assert "本 PR 更新了简体中文本地化" in body
