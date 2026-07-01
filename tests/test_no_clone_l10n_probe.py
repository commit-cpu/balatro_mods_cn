import os
import time

import httpx

from app.github.no_clone_l10n_probe import (
    GitHubApi,
    LocaleFileAnalysis,
    RepoLocalizationAnalysis,
    canonical_repo_from_meta,
    classify_locale_pair,
    load_index_items,
    summarize_repo_analysis,
)


def test_classify_complete_when_target_covers_source_without_local_warnings() -> None:
    result = classify_locale_pair(
        source_path="localization/en-us.lua",
        target_path="localization/zh_CN.lua",
        source_units={
            "descriptions.Joker.j_test.name": "Test Joker",
            "descriptions.Joker.j_test.text[0]": "Gains {C:chips}+#1#{} Chips",
        },
        target_units={
            "descriptions.Joker.j_test.name": "测试小丑",
            "descriptions.Joker.j_test.text[0]": "获得{C:chips}+#1#{}筹码",
        },
    )

    assert result.status == "complete"
    assert result.missing_keys == []
    assert result.same_as_source_keys == []
    assert result.residual_english_keys == []


def test_classify_missing_zh_when_target_file_absent() -> None:
    result = classify_locale_pair(
        source_path="localization/en-us.lua",
        target_path="localization/zh_CN.lua",
        source_units={"misc.dictionary.example": "Example"},
        target_units=None,
    )

    assert result.status == "missing_zh_CN"
    assert result.missing_count == 1


def test_classify_missing_keys_when_zh_lacks_source_units() -> None:
    result = classify_locale_pair(
        source_path="localization/en-us.lua",
        target_path="localization/zh_CN.lua",
        source_units={
            "misc.dictionary.one": "One",
            "misc.dictionary.two": "Two",
        },
        target_units={"misc.dictionary.one": "一"},
    )

    assert result.status == "missing_keys"
    assert result.missing_keys == ["misc.dictionary.two"]


def test_classify_untranslated_keys_when_target_equals_english_source() -> None:
    result = classify_locale_pair(
        source_path="localization/en-us.lua",
        target_path="localization/zh_CN.lua",
        source_units={"misc.dictionary.example": "Example text"},
        target_units={"misc.dictionary.example": "Example text"},
    )

    assert result.status == "untranslated_keys"
    assert result.same_as_source_keys == ["misc.dictionary.example"]


def test_classify_residual_english_when_target_contains_gameplay_words() -> None:
    result = classify_locale_pair(
        source_path="localization/en-us.lua",
        target_path="localization/zh_CN.lua",
        source_units={"descriptions.Joker.j_test.text[0]": "Gain Chips"},
        target_units={"descriptions.Joker.j_test.text[0]": "获得 Chips"},
    )

    assert result.status == "residual_english"
    assert result.residual_english_keys == ["descriptions.Joker.j_test.text[0]"]


def test_summarize_repo_analysis_distinguishes_missing_source_and_complete() -> None:
    no_localization = summarize_repo_analysis(
        localization_dirs=[],
        locale_files=[],
    )
    assert no_localization.status == "no_localization_dir"

    without_source = summarize_repo_analysis(
        localization_dirs=["localization"],
        locale_files=[],
    )
    assert without_source.status == "localization_without_known_source"

    complete = summarize_repo_analysis(
        localization_dirs=["localization"],
        locale_files=[
            LocaleFileAnalysis(
                source_path="localization/en-us.lua",
                target_path="localization/zh_CN.lua",
                status="complete",
                source_units=1,
                zh_units=1,
            )
        ],
    )
    assert complete.status == "complete"


def test_repo_analysis_uses_problem_status_when_any_locale_pair_needs_work() -> None:
    repo = RepoLocalizationAnalysis(
        status="missing_keys",
        localization_dirs=["localization"],
        source_files=["localization/en-us.lua"],
        zh_files=["localization/zh_CN.lua"],
        details=[
            LocaleFileAnalysis(
                source_path="localization/en-us.lua",
                target_path="localization/zh_CN.lua",
                status="missing_keys",
                source_units=2,
                zh_units=1,
                missing_keys=["misc.dictionary.two"],
            )
        ],
    )

    assert repo.to_dict()["summary"]["missing_keys"] == 1
    assert repo.to_dict()["details"][0]["samples"]["missing_keys"] == [
        "misc.dictionary.two"
    ]


def test_github_api_follows_repository_redirects() -> None:
    client = GitHubApi("fake-token")
    try:
        assert client._client.follow_redirects is True
    finally:
        client.close()


def test_github_api_caches_get_responses_on_disk(tmp_path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "full_name": "example/alpha",
                "name": "alpha",
                "default_branch": "main",
            },
        )

    cache_dir = tmp_path / "github-cache"
    client = GitHubApi(
        "fake-token",
        cache_dir=cache_dir,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.repo("example", "alpha")["full_name"] == "example/alpha"
    finally:
        client.close()

    def fail_on_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network request: {request.url}")

    cached_client = GitHubApi(
        "fake-token",
        cache_dir=cache_dir,
        transport=httpx.MockTransport(fail_on_network),
    )
    try:
        assert cached_client.repo("example", "alpha")["default_branch"] == "main"
    finally:
        cached_client.close()

    assert len(calls) == 1
    assert list(cache_dir.glob("*.json"))


def test_github_api_refreshes_expired_cached_get_response(tmp_path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "full_name": "example/alpha",
                "name": "alpha",
                "default_branch": f"main-{calls}",
            },
        )

    cache_dir = tmp_path / "github-cache"
    client = GitHubApi(
        "fake-token",
        cache_dir=cache_dir,
        cache_ttl_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.repo("example", "alpha")["default_branch"] == "main-1"
    finally:
        client.close()

    cache_file = next(cache_dir.glob("*.json"))
    stale = time.time() - 10
    os.utime(cache_file, (stale, stale))

    refreshed = GitHubApi(
        "fake-token",
        cache_dir=cache_dir,
        cache_ttl_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert refreshed.repo("example", "alpha")["default_branch"] == "main-2"
    finally:
        refreshed.close()

    assert calls == 2


def test_canonical_repo_from_meta_uses_redirected_full_name() -> None:
    owner, repo = canonical_repo_from_meta(
        {"full_name": "ActualOwner/ActualRepo", "name": "ActualRepo"},
        fallback_owner="OldOwner",
        fallback_repo="OldRepo",
    )

    assert owner == "ActualOwner"
    assert repo == "ActualRepo"


def test_load_index_items_can_select_one_mod_by_name_or_repo_url(tmp_path) -> None:
    index_path = tmp_path / "mods.json"
    index_path.write_text(
        """
        [
          {
            "name": "Alpha Mod",
            "github_repo_url": "https://github.com/example/alpha"
          },
          {
            "name": "Balatro Draft",
            "github_repo_url": "https://github.com/spire-winder/Balatro-Draft"
          }
        ]
        """,
        encoding="utf-8",
    )

    by_name = load_index_items(index_path, limit=500, mod_name="Balatro Draft")
    by_repo = load_index_items(
        index_path,
        limit=500,
        repo_url="https://github.com/spire-winder/Balatro-Draft",
    )

    assert [item["name"] for item in by_name] == ["Balatro Draft"]
    assert [item["name"] for item in by_repo] == ["Balatro Draft"]
