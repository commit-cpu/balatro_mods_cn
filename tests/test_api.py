import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.github_workflow import (
    github_probe_payload,
    materialize_probe_row_localization,
)
from app.api.repositories import ApiRepository
from app.api.translation_workflow import apply_approved_review_items
from app.api.translation_workflow import import_latest_preview_review_items
from app.api.translation_workflow import run_translation_job
from app.db.connection import connect
from app.db.migrate import migrate


def _write_mod_index(path: Path) -> None:
    path.write_text(
        """
        [
          {
            "name": "Alpha Mod",
            "github_repo_url": "https://github.com/example/alpha",
            "stars": 42,
            "categories": ["Content", "Joker"],
            "requires-steamodded": true,
            "requires-talisman": false
          },
          {
            "name": "Beta Utility",
            "github_repo_url": "https://github.com/example/beta",
            "stars": 7,
            "categories": ["Quality of Life"],
            "requires-steamodded": false,
            "requires-talisman": true
          },
          {
            "name": "Gamma Unprobed",
            "github_repo_url": "https://github.com/example/gamma",
            "stars": 3,
            "categories": ["Content"],
            "requires-steamodded": false,
            "requires-talisman": false
          }
        ]
        """,
        encoding="utf-8",
    )


def _write_probe_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
        {
          "items": [
            {
              "name": "Alpha Mod",
              "url": "https://github.com/example/alpha",
              "fork": "bot/alpha",
              "analysis": {
                "status": "missing_keys",
                "summary": {
                  "source_units": 10,
                  "zh_units": 9,
                  "missing_keys": 1,
                  "extra_keys": 0,
                  "untranslated_keys": 0,
                  "residual_english": 0
                }
              }
            },
            {
              "name": "Beta Utility",
              "url": "https://github.com/example/beta",
              "analysis": {
                "status": "no_localization_dir",
                "summary": {
                  "source_units": 0,
                  "zh_units": 0,
                  "missing_keys": 0,
                  "extra_keys": 0,
                  "untranslated_keys": 0,
                  "residual_english": 0
                }
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )


def test_api_exposes_summary_mods_jobs_and_review_update(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('sample_mod', '/repos/sample', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.execute(
            """
            insert into jobs(type, status, idempotency_key, payload_json)
            values ('translate_batch', 'pending', 'translate:sample', '{"mod_id":"sample_mod"}')
            """
        )
        db.execute(
            """
            insert into review_items(
                mod_id, unit_key, source_text, current_target_text, status, reason
            ) values (
                'sample_mod', 'descriptions.Joker.j_test.text[0]',
                'Gain Chips', '获得 Chips', 'pending', 'residual_english'
            )
            """
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))

    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert summary.json()["counts"]["mods"] == 1
    assert summary.json()["counts"]["pending_reviews"] == 1

    mods = client.get("/api/mods")
    assert mods.status_code == 200
    assert mods.json()["items"][0]["mod_id"] == "sample_mod"

    jobs = client.get("/api/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["type"] == "translate_batch"

    review_items = client.get("/api/review-items?status=pending&page=1&page_size=10")
    assert review_items.status_code == 200
    assert review_items.json()["total"] == 1
    assert review_items.json()["page"] == 1
    review_id = review_items.json()["items"][0]["id"]

    updated = client.patch(
        f"/api/review-items/{review_id}",
        json={
            "status": "approved",
            "edited_target_text": "获得筹码",
            "reviewer": "human",
            "comment": "去掉英文残留",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "approved"
    assert updated.json()["edited_target_text"] == "获得筹码"


def test_feedback_submission_creates_pending_feedback_and_job(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('sample_mod', '/repos/sample', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))
    response = client.post(
        "/api/feedback",
        json={
            "mod_id": "sample_mod",
            "unit_key": "descriptions.Joker.j_test.text[0]",
            "translation_id": "candidate-1",
            "feedback_type": "untranslated",
            "suggested_text": "获得筹码",
            "comment": "这里没有翻完",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["job"]["type"] == "evaluate_feedback"
    assert payload["job"]["idempotency_key"] == f"feedback:{payload['id']}"

    feedback = client.get("/api/feedback")
    assert feedback.status_code == 200
    assert feedback.json()["items"][0]["feedback_type"] == "untranslated"


def test_admin_route_requires_secret_when_enabled(monkeypatch, tmp_path: Path) -> None:
    from fastapi import HTTPException, Response

    from app.api.admin_auth import (
        ADMIN_COOKIE_NAME,
        admin_route_path,
        require_admin,
        set_admin_cookie,
        validate_admin_secret,
    )
    from app.api.main import _admin_login_page

    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    app = create_app(db_path=db_path)
    paths = {getattr(route, "path", ""): route for route in app.routes}

    assert "/admin" not in paths
    assert "/cnops" in paths
    route_methods = {
        method
        for route in app.routes
        if getattr(route, "path", "") == "/cnops"
        for method in getattr(route, "methods", set())
    }
    assert {"GET", "POST"}.issubset(route_methods)
    assert admin_route_path() == "/cnops"

    try:
        validate_admin_secret(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing admin secret was accepted")

    validate_admin_secret("secret-value")
    response = Response()
    set_admin_cookie(response)
    assert ADMIN_COOKIE_NAME in response.headers.get("set-cookie", "")
    login_page = _admin_login_page("/cnops")
    assert "需要验证 sk" in login_page.body.decode("utf-8")
    jobs_route = paths["/api/jobs"]
    dependency_calls = {dep.call for dep in jobs_route.dependant.dependencies}
    assert require_admin in dependency_calls


def test_protected_api_rejects_without_admin_cookie(monkeypatch, tmp_path: Path) -> None:
    from app.api.admin_auth import require_admin

    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    app = create_app(db_path=db_path)
    paths = {getattr(route, "path", ""): route for route in app.routes}

    assert not paths["/api/health"].dependant.dependencies
    assert require_admin in {dep.call for dep in paths["/api/jobs"].dependant.dependencies}
    assert require_admin in {
        dep.call for dep in paths["/api/github/probe"].dependant.dependencies
    }


def test_admin_auth_reads_dotenv_without_export(monkeypatch, tmp_path: Path) -> None:
    from app.api.admin_auth import admin_auth_enabled, admin_route_path

    monkeypatch.delenv("ADMIN_PATH_SUFFIX", raising=False)
    monkeypatch.delenv("ADMIN_SECRET_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ADMIN_PATH_SUFFIX=cnops-balatro-aadmin\n"
        "ADMIN_SECRET_KEY=secret-value\n",
        encoding="utf-8",
    )

    assert admin_auth_enabled() is True
    assert admin_route_path() == "/cnops-balatro-aadmin"


def test_mod_index_includes_cached_workflow_state_from_probe_report(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)

    report = {
        "items": [
            {
                "name": "Alpha Mod",
                "url": "https://github.com/example/alpha",
                "upstream": "example/alpha",
                "canonical_upstream": "example/alpha",
                "fork": "bot/alpha",
                "fork_status": "already_exists",
                "analysis": {
                    "status": "missing_keys",
                    "summary": {
                        "source_units": 10,
                        "zh_units": 8,
                        "missing_keys": 2,
                        "untranslated_keys": 0,
                        "residual_english": 0,
                    },
                },
            }
        ]
    }
    probe_report_path.write_text(json.dumps(report), encoding="utf-8")

    repo = ApiRepository(
        db_path,
        mod_index_path=mod_index_path,
        probe_report_path=probe_report_path,
    )
    assert repo.upsert_workflows_from_probe_report(report, job_id=12) == 1

    alpha = repo.mod_index(q="alpha")["items"][0]
    assert alpha["workflow_status"] == "forked"
    assert alpha["workflow_status_label"] == "已 Fork"
    assert alpha["next_action"] == "translate"
    assert alpha["next_action_label"] == "启动翻译"
    assert alpha["ai_translation_repo_url"] == "https://github.com/bot/alpha"


def test_mod_index_only_exposes_verified_fork_and_local_translation_source(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values (
                'alpha_local',
                '/repos/Alpha Mod',
                'localization/en-us.lua',
                'localization/zh_CN.lua'
            )
            """
        )
        db.commit()

    probe_report_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "Alpha Mod",
                        "url": "https://github.com/example/alpha",
                        "upstream": "example/alpha",
                        "canonical_upstream": "example/alpha",
                        "fork": "bot/alpha",
                        "fork_status": "not_requested",
                        "analysis": {
                            "status": "missing_keys",
                            "summary": {
                                "source_units": 10,
                                "zh_units": 8,
                                "missing_keys": 2,
                                "untranslated_keys": 0,
                                "residual_english": 0,
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repo = ApiRepository(
        db_path,
        mod_index_path=mod_index_path,
        probe_report_path=probe_report_path,
    )

    alpha = repo.mod_index(q="alpha")["items"][0]
    assert alpha["workflow_status"] == "probed"
    assert alpha["next_action"] == "fork"
    assert alpha["ai_translation_repo_url"] is None
    assert alpha["translation_available"] is True
    assert alpha["translation_mod_id"] == "alpha_local"

    beta = repo.mod_index(q="beta")["items"][0]
    assert beta["translation_available"] is False
    assert beta["translation_mod_id"] is None


def test_mod_index_reports_fork_committed_ai_status_without_overwriting_upstream_status(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    probe_report_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "name": "Alpha Mod",
                        "url": "https://github.com/example/alpha",
                        "fork": "bot/alpha",
                        "fork_status": "already_exists",
                        "analysis": {
                            "status": "missing_keys",
                            "summary": {
                                "source_units": 10,
                                "zh_units": 8,
                                "missing_keys": 2,
                                "untranslated_keys": 0,
                                "residual_english": 0,
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with connect(db_path) as db:
        db.execute(
            """
            insert into pull_requests(mod_id, repo_slug, branch, state, last_commit_sha)
            values ('Alpha Mod', 'bot/alpha', 'bot/zh-cn/alpha_mod', 'fork_committed', 'abc123')
            """
        )
        db.commit()

    repo = ApiRepository(
        db_path,
        mod_index_path=mod_index_path,
        probe_report_path=probe_report_path,
    )

    alpha = repo.mod_index(q="alpha")["items"][0]
    assert alpha["localization_status"] == "partial"
    assert alpha["ai_translation_status"] == "complete"
    assert alpha["ai_translation_status_label"] == "完全汉化"


def test_mod_index_ai_repo_url_prefers_latest_fork_branch(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_workflows(
                mod_id, upstream_url, fork_slug, fork_status, workflow_status, next_action
            ) values (
                'Alpha Mod', 'https://github.com/example/alpha',
                'bot/alpha', 'already_exists', 'committed', 'pr'
            )
            """
        )
        db.execute(
            """
            insert into pull_requests(mod_id, repo_slug, branch, state, last_commit_sha)
            values ('alpha_mod', 'bot/alpha', 'bot/zh-cn/alpha_mod', 'fork_committed', 'new-sha')
            """
        )
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', '/repos/Alpha Mod', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.commit()

    repo = ApiRepository(
        db_path,
        mod_index_path=mod_index_path,
        probe_report_path=probe_report_path,
    )
    alpha = repo.mod_index(q="alpha")["items"][0]

    assert (
        alpha["ai_translation_repo_url"]
        == "https://github.com/bot/alpha/tree/bot/zh-cn/alpha_mod"
    )
    assert (
        alpha["ai_translation_branch_url"]
        == "https://github.com/bot/alpha/tree/bot/zh-cn/alpha_mod"
    )
    assert alpha["ai_translation_status"] == "complete"
    assert alpha["workflow_status"] == "committed"


def test_admin_mods_summary_includes_review_queue_and_fork_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)
    repo = ApiRepository(
        db_path,
        mod_index_path=mod_index_path,
        probe_report_path=probe_report_path,
    )
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', '/repos/Alpha Mod', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.execute(
            """
            insert into review_items(mod_id, unit_key, source_text, status, reason)
            values ('alpha_mod', 'misc.dictionary.test', 'Test', 'pending', 'missing')
            """
        )
        db.execute(
            """
            insert into pull_requests(mod_id, repo_slug, branch, state, last_commit_sha)
            values ('alpha_mod', 'bot/alpha', 'bot/zh-cn/alpha_mod', 'fork_committed', 'sha')
            """
        )
        db.commit()

    alpha = next(item for item in repo.admin_mods() if item["name"] == "Alpha Mod")

    assert alpha["pending_review_items"] == 1
    assert alpha["queue_status"] == "queued"
    assert alpha["latest_fork_branch_url"] == "https://github.com/bot/alpha/tree/bot/zh-cn/alpha_mod"


def test_admin_settings_and_queue_routes_are_registered_and_protected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.api.admin_auth import require_admin

    monkeypatch.setenv("ADMIN_PATH_SUFFIX", "cnops")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "secret-value")
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    app = create_app(db_path=db_path)
    routes = {getattr(route, "path", ""): route for route in app.routes}

    for path in (
        "/api/admin/settings",
        "/api/admin/mods",
        "/api/translation-queue",
        "/api/translation-queue/{queue_id}/start",
        "/api/translation-queue/{queue_id}/retry",
    ):
        dependency_calls = {dep.call for dep in routes[path].dependant.dependencies}
        assert require_admin in dependency_calls


def test_github_probe_and_fork_jobs_run_injected_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    mod_index_path = tmp_path / "mods.json"
    probe_report_path = tmp_path / "report.json"
    _write_mod_index(mod_index_path)
    migrate(db_path)

    runner_calls: list[tuple[int, dict[str, Any]]] = []

    def fake_runner(db_path: Path, job_id: int, payload: dict[str, Any]) -> None:
        runner_calls.append((job_id, payload))

    client = TestClient(
        create_app(
            db_path=db_path,
            mod_index_path=mod_index_path,
            probe_report_path=probe_report_path,
            github_probe_runner=fake_runner,
        )
    )

    probe = client.post("/api/github/probe", json={"limit": 3})
    assert probe.status_code == 201
    assert probe.json()["type"] == "github_l10n_probe"
    assert probe.json()["payload"]["fork"] is False
    assert probe.json()["payload"]["index_path"] == str(mod_index_path)
    assert probe.json()["payload"]["report_path"] == str(probe_report_path)

    fork = client.post("/api/github/forks", json={"limit": 2})
    assert fork.status_code == 201
    assert fork.json()["type"] == "github_fork_probe"
    assert fork.json()["payload"]["fork"] is True

    assert [call[0] for call in runner_calls] == [probe.json()["id"], fork.json()["id"]]
    assert runner_calls[1][1]["fork"] is True


def test_github_probe_payload_can_target_selected_mod(tmp_path: Path) -> None:
    payload = github_probe_payload(
        index_path=tmp_path / "mods.json",
        report_path=tmp_path / "report.json",
        limit=1,
        fork=True,
        refresh_cache=False,
        mod_name="Balatro Draft",
        repo_url="https://github.com/spire-winder/Balatro-Draft",
    )

    assert payload["limit"] == 1
    assert payload["fork"] is True
    assert payload["mod_name"] == "Balatro Draft"
    assert payload["repo_url"] == "https://github.com/spire-winder/Balatro-Draft"


def test_repository_records_job_events(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)
    job, _created = repo.create_github_probe_job(
        job_type="github_l10n_probe",
        payload={"mod_name": "Alpha Mod"},
    )

    repo.log_job_event(
        job["id"],
        event="github.probe.start",
        message="Starting GitHub probe",
        payload={"mod_name": "Alpha Mod"},
    )
    repo.log_job_event(
        job["id"],
        level="warning",
        event="github.localization.missing_target",
        message="zh_CN.lua is missing",
    )

    events = repo.list_job_events(job["id"])
    assert [event["event"] for event in events] == [
        "github.probe.start",
        "github.localization.missing_target",
    ]
    assert events[0]["payload"] == {"mod_name": "Alpha Mod"}
    assert events[1]["level"] == "warning"


def test_materialize_probe_row_localization_downloads_only_locale_files(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str, str]] = []

        def file_text(self, owner: str, repo: str, path: str, ref: str) -> str | None:
            self.calls.append((owner, repo, path, ref))
            if path == "localization/en-us.lua":
                return 'return { descriptions = { Joker = { j_demo = { name = "Demo" } } } }\n'
            if path == "localization/zh_CN.lua":
                return None
            raise AssertionError(f"unexpected download: {path}")

    row = {
        "name": "HandsomeDevils",
        "url": "https://github.com/example/Handsome-Devils",
        "canonical_upstream": "example/Handsome-Devils",
        "default_branch": "main",
        "analysis": {
            "details": [
                {
                    "source": "localization/en-us.lua",
                    "zh": "localization/zh_CN.lua",
                    "source_units": 1,
                }
            ]
        },
    }

    mod = materialize_probe_row_localization(
        db_path=db_path,
        row=row,
        client=FakeClient(),
        local_root=tmp_path / "repos",
    )

    repo_path = Path(mod["repo_path"])
    assert mod["mod_id"] == "handsomedevils"
    assert mod["source_locale_path"] == "localization/en-us.lua"
    assert mod["target_locale_path"] == "localization/zh_CN.lua"
    assert (repo_path / "localization" / "en-us.lua").exists()
    assert not (repo_path / "README.md").exists()

    with connect(db_path) as db:
        saved = db.execute(
            "select mod_id, repo_path, source_locale_path, target_locale_path from mod_sources"
        ).fetchone()
    assert dict(saved) == {
        "mod_id": "handsomedevils",
        "repo_path": str(repo_path),
        "source_locale_path": "localization/en-us.lua",
        "target_locale_path": "localization/zh_CN.lua",
    }


def test_translation_job_records_failure_event(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)
    job, _created = repo.create_translation_job(
        mod_id="broken",
        payload={
            "mod_id": "broken",
            "repo_path": str(tmp_path / "missing-repo"),
            "source": "localization/en-us.lua",
            "output": str(tmp_path / "out.lua"),
            "work_dir": str(tmp_path / "work"),
            "limit": 1,
            "top_k": 1,
            "max_width": 18,
            "concurrency": None,
            "max_rounds": 1,
            "include_needs_review": False,
            "validate_lua": True,
        },
    )

    run_translation_job(db_path, job["id"], job["payload"])

    events = repo.list_job_events(job["id"])
    assert events[0]["event"] == "translation.loop.start"
    assert events[-1]["event"] == "translation.loop.failed"
    assert repo.get_job(job["id"])["status"] == "failed"


def test_translation_job_records_progress_events(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)
    job, _created = repo.create_translation_job(
        mod_id="demo",
        payload={
            "mod_id": "demo",
            "repo_path": str(tmp_path / "repo"),
            "source": "localization/en-us.lua",
            "output": str(tmp_path / "out.lua"),
            "work_dir": str(tmp_path / "work"),
            "limit": 2,
            "top_k": 1,
            "max_width": 18,
            "concurrency": None,
            "max_rounds": 1,
            "include_needs_review": False,
            "validate_lua": True,
        },
    )

    def fake_translate_entry_loop(**_kwargs: Any) -> None:
        from app.cli.main import _emit_translation_progress

        _emit_translation_progress(
            "translation.entry.done",
            "Translated [1/2] descriptions.Joker.j_demo",
            current=1,
            total=2,
            entry_key="descriptions.Joker.j_demo",
        )

    monkeypatch.setattr("app.api.translation_workflow.translate_entry_loop", fake_translate_entry_loop)
    monkeypatch.setattr(
        "app.api.translation_workflow.import_latest_preview_review_items",
        lambda **_kwargs: 0,
    )

    run_translation_job(db_path, job["id"], job["payload"])

    events = repo.list_job_events(job["id"])
    progress = [event for event in events if event["event"] == "translation.entry.done"]
    assert progress[0]["payload"] == {
        "current": 1,
        "entry_key": "descriptions.Joker.j_demo",
        "total": 2,
    }
    assert repo.get_job(job["id"])["status"] == "succeeded"


def test_review_workbench_groups_items_by_mod_and_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('familiar', '/repos/familiar', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.executemany(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text, status, reason
            ) values (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "familiar",
                    "descriptions.Booster.p_fam_pantheon_booster_3.name",
                    "Pantheon Pack",
                    "万神殿补充包",
                    "pending",
                    "ai_translation_review",
                ),
                (
                    "familiar",
                    "descriptions.Booster.p_fam_pantheon_booster_3.text[0]",
                    "Choose 1 of up to 3",
                    "从最多 3 张中选择 1 张",
                    "pending",
                    "ai_translation_review",
                ),
                (
                    "familiar",
                    "descriptions.Booster.p_fam_pantheon_booster_3.text[1]",
                    "Sacred cards",
                    "神圣牌",
                    "pending",
                    "ai_translation_review",
                ),
                (
                    "familiar",
                    "descriptions.Joker.j_fam_rna.name",
                    "RNA",
                    "RNA",
                    "approved",
                    "ai_translation_review",
                ),
            ],
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))

    review_mods = client.get("/api/review-mods?status=pending")
    assert review_mods.status_code == 200
    assert review_mods.json()["items"] == [
        {
            "mod_id": "familiar",
            "pending_items": 3,
            "entry_groups": 1,
            "latest_updated_at": review_mods.json()["items"][0]["latest_updated_at"],
        }
    ]

    review_groups = client.get(
        "/api/review-groups?status=pending&mod_id=familiar&page=1&page_size=10"
    )
    assert review_groups.status_code == 200
    payload = review_groups.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entry_key"] == "descriptions.Booster.p_fam_pantheon_booster_3"
    assert payload["items"][0]["item_count"] == 3
    assert [item["field"] for item in payload["items"][0]["items"]] == [
        "name",
        "text[0]",
        "text[1]",
    ]

    approved = client.patch(
        "/api/review-groups/approve",
        json={
            "item_ids": [item["id"] for item in payload["items"][0]["items"]],
            "edited_target_texts": {
                str(payload["items"][0]["items"][1]["id"]): "从最多三张中选择一张"
            },
            "reviewer": "human",
            "comment": "整组通过",
        },
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["updated"] == 3
    assert approved_payload["items"][1]["edited_target_text"] == "从最多三张中选择一张"
    assert {item["status"] for item in approved_payload["items"]} == {"approved"}

    pending_after = client.get(
        "/api/review-groups?status=pending&mod_id=familiar&page=1&page_size=10"
    )
    assert pending_after.json()["total"] == 0


def test_review_group_approval_allows_blank_target_text_for_omitted_output_line(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.executemany(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text, status, reason
            ) values (?, ?, ?, ?, 'pending', 'ai_translation_review')
            """,
            [
                (
                    "familiar",
                    "descriptions.Joker.j_blank.name",
                    "Blank",
                    "空白",
                ),
                (
                    "familiar",
                    "descriptions.Joker.j_blank.text[0]",
                    "Missing translation",
                    None,
                ),
            ],
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))
    group = client.get(
        "/api/review-groups?status=pending&mod_id=familiar&page=1&page_size=1"
    ).json()["items"][0]

    response = client.patch(
        "/api/review-groups/approve",
        json={
            "item_ids": [item["id"] for item in group["items"]],
            "edited_target_texts": {
                str(item["id"]): item["suggested_target_text"] or ""
                for item in group["items"]
            },
            "reviewer": "human",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == 2
    assert payload["items"][1]["edited_target_text"] == ""
    assert {item["status"] for item in payload["items"]} == {"approved"}

    approved = client.get(
        "/api/review-groups?status=approved&mod_id=familiar&page=1&page_size=10"
    )
    assert approved.json()["total"] == 1


def test_manual_translation_start_creates_job_and_runs_injected_runner(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "Familiar"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text(
        'return { descriptions = { Joker = { j_test = { name = "Test" } } } }\n',
        encoding="utf-8",
    )
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('familiar', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()

    runner_calls: list[tuple[int, dict[str, Any]]] = []

    def fake_runner(db_path: Path, job_id: int, payload: dict[str, Any]) -> None:
        runner_calls.append((job_id, payload))

    client = TestClient(create_app(db_path=db_path, translation_runner=fake_runner))
    response = client.post("/api/mods/familiar/translate", json={"limit": 20, "max_rounds": 2})

    assert response.status_code == 201
    payload = response.json()
    assert payload["type"] == "translate_entry_loop"
    assert payload["status"] == "pending"
    assert payload["payload"]["mod_id"] == "familiar"
    assert payload["payload"]["repo_path"] == str(repo_path)
    assert payload["payload"]["source"] == "localization/en-us.lua"
    assert payload["payload"]["target"] == "localization/zh_CN.lua"
    assert payload["payload"]["output"].endswith("candidate_zh_CN.lua")
    assert not payload["payload"]["output"].endswith("localization/zh_CN.lua")
    assert payload["payload"]["limit"] == 20
    assert payload["payload"]["max_rounds"] == 2
    assert len(runner_calls) == 1
    assert runner_calls[0][0] == payload["id"]
    assert runner_calls[0][1]["mod_id"] == "familiar"


def test_translation_preview_import_only_queues_rows_that_need_review(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    work_dir = tmp_path / "artifacts" / "familiar_entry_translate_loop"
    work_dir.mkdir(parents=True)
    preview = work_dir / "round_00_preview.jsonl"
    preview.write_text(
        """
{"entry_key":"descriptions.Joker.j_test","ok":true,"needs_review":false,"target_units":{"name":"descriptions.Joker.j_test.name","text":["descriptions.Joker.j_test.text[0]"],"unlock":[]},"name":"测试小丑","text":["获得筹码"],"unlock":[],"source":{"name":"Test Joker","text":["Gain Chips"],"unlock":[]}}
{"entry_key":"descriptions.Joker.j_review","ok":true,"needs_review":true,"target_units":{"name":"descriptions.Joker.j_review.name","text":["descriptions.Joker.j_review.text[0]"],"unlock":[]},"name":"待审小丑","text":["Review this"],"unlock":[],"source":{"name":"Review Joker","text":["Review this"],"unlock":[]}}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (work_dir / "manifest.json").write_text(
        json.dumps(
            {
                "rounds": [
                    {
                        "round_index": 0,
                        "preview": str(preview),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text, status, reason
            ) values (
                'familiar', 'old.key', 'Old', '旧', 'pending', 'stale'
            )
            """
        )
        db.commit()

    imported = import_latest_preview_review_items(
        db_path=db_path,
        mod_id="familiar",
        work_dir=work_dir,
    )

    assert imported == 2
    with connect(db_path) as db:
        rows = db.execute(
            "select unit_key, source_text, suggested_target_text, status from review_items order by id"
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "unit_key": "descriptions.Joker.j_review.name",
            "source_text": "Review Joker",
            "suggested_target_text": "待审小丑",
            "status": "pending",
        },
        {
            "unit_key": "descriptions.Joker.j_review.text[0]",
            "source_text": "Review this",
            "suggested_target_text": "Review this",
            "status": "pending",
        },
    ]


def test_translation_preview_import_queues_blocked_rows_for_review(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    work_dir = tmp_path / "artifacts" / "familiar_entry_translate_loop"
    work_dir.mkdir(parents=True)
    preview = work_dir / "round_00_preview.jsonl"
    preview.write_text(
        json.dumps(
            {
                "entry_key": "misc.v_text.ch_c_demo",
                "ok": True,
                "needs_review": False,
                "apply_mode": "blocked",
                "patchable": False,
                "patch_warnings": ["text line count mismatch: source=1, target=3"],
                "target_units": {"name": None, "text": ["misc.v_text.ch_c_demo[0]"], "unlock": []},
                "name": None,
                "text": ["经济小丑、", "金色蜡封和", "幸运牌被禁用"],
                "unlock": [],
                "source": {
                    "name": None,
                    "text": ["Economy Jokers, Gold Seal and Lucky Card are banned"],
                    "unlock": [],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (work_dir / "manifest.json").write_text(
        json.dumps({"rounds": [{"round_index": 0, "preview": str(preview)}]}),
        encoding="utf-8",
    )
    migrate(db_path)

    imported = import_latest_preview_review_items(
        db_path=db_path,
        mod_id="familiar",
        work_dir=work_dir,
    )

    assert imported == 1
    with connect(db_path) as db:
        row = db.execute(
            """
            select unit_key, source_text, suggested_target_text, status, reason
            from review_items
            """
        ).fetchone()
    assert dict(row) == {
        "unit_key": "misc.v_text.ch_c_demo[0]",
        "source_text": "Economy Jokers, Gold Seal and Lucky Card are banned",
        "suggested_target_text": "经济小丑、金色蜡封和幸运牌被禁用",
        "status": "pending",
        "reason": "ai_translation_blocked",
    }


def test_translation_preview_import_preserves_approved_review_items(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    work_dir = tmp_path / "artifacts" / "familiar_entry_translate_loop"
    work_dir.mkdir(parents=True)
    preview = work_dir / "round_00_preview.jsonl"
    preview.write_text(
        """
{"entry_key":"descriptions.Joker.j_done","ok":true,"needs_review":true,"target_units":{"name":"descriptions.Joker.j_done.name","text":[],"unlock":[]},"name":"已审小丑","text":[],"unlock":[],"source":{"name":"Done Joker","text":[],"unlock":[]}}
{"entry_key":"descriptions.Joker.j_new","ok":true,"needs_review":true,"target_units":{"name":"descriptions.Joker.j_new.name","text":[],"unlock":[]},"name":"新小丑","text":[],"unlock":[],"source":{"name":"New Joker","text":[],"unlock":[]}}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (work_dir / "manifest.json").write_text(
        json.dumps({"rounds": [{"round_index": 0, "preview": str(preview)}]}),
        encoding="utf-8",
    )
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text,
                edited_target_text, status, reason, reviewer
            ) values (
                'familiar', 'descriptions.Joker.j_done.name',
                'Done Joker', '已审小丑', '人工已审小丑',
                'approved', 'ai_translation_needs_review', 'human'
            )
            """
        )
        db.commit()

    imported = import_latest_preview_review_items(
        db_path=db_path,
        mod_id="familiar",
        work_dir=work_dir,
    )

    assert imported == 1
    with connect(db_path) as db:
        rows = db.execute(
            """
            select unit_key, edited_target_text, status
            from review_items
            order by unit_key, status
            """
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "unit_key": "descriptions.Joker.j_done.name",
            "edited_target_text": "人工已审小丑",
            "status": "approved",
        },
        {
            "unit_key": "descriptions.Joker.j_new.name",
            "edited_target_text": None,
            "status": "pending",
        },
    ]


def test_apply_approved_review_items_writes_target_and_omits_blank_text_lines(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "Familiar"
    localization = repo_path / "localization"
    localization.mkdir(parents=True)
    (localization / "en-us.lua").write_text(
        """
return {
    descriptions = {
        Back = {
            b_fam_topaz_deck = {
                name = "Topaz Deck",
                text = {
                    "{C:blue}+1{} hand every round,",
                    "{C:red}+1{} discard every round",
                    "{C:attention}-2{} hand size",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('familiar', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.executemany(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text,
                edited_target_text, status, reason, reviewer
            ) values ('familiar', ?, ?, ?, ?, 'approved', 'ai_translation_review', 'human')
            """,
            [
                (
                    "descriptions.Back.b_fam_topaz_deck.name",
                    "Topaz Deck",
                    "黄玉牌组",
                    "黄玉牌组",
                ),
                (
                    "descriptions.Back.b_fam_topaz_deck.text[0]",
                    "{C:blue}+1{} hand every round,",
                    "每回合{C:blue}+1{}次出牌，",
                    "每回合{C:blue}+1{}次出牌，",
                ),
                (
                    "descriptions.Back.b_fam_topaz_deck.text[1]",
                    "{C:red}+1{} discard every round",
                    "每回合{C:red}+1{}次弃牌",
                    "每回合{C:red}+1{}次弃牌",
                ),
                (
                    "descriptions.Back.b_fam_topaz_deck.text[2]",
                    "{C:attention}-2{} hand size",
                    None,
                    "",
                ),
            ],
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))
    response = client.post("/api/mods/familiar/apply-approved")

    assert response.status_code == 200
    payload = response.json()
    assert payload["applied_items"] == 4
    assert payload["applied_entries"] == 1
    output = (localization / "zh_CN.lua").read_text(encoding="utf-8")
    assert "黄玉牌组" in output
    assert "每回合{C:blue}+1{}次出牌，" in output
    assert "每回合{C:red}+1{}次弃牌" in output
    assert "{C:attention}-2{} hand size" not in output
    assert output.count("每回合") == 2


def test_apply_approved_review_items_uses_candidate_translation_as_base(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "Bakery"
    localization = repo_path / "localization"
    localization.mkdir(parents=True)
    (localization / "en-us.lua").write_text(
        """
return {
    descriptions = {
        Joker = {
            j_kept = {
                name = "Kept Joker",
                text = {
                    "Already translated by AI",
                },
            },
            j_review = {
                name = "Review Joker",
                text = {
                    "Needs human edit",
                },
            },
        },
    },
}
        """,
        encoding="utf-8",
    )
    migrate(db_path)
    monkeypatch.chdir(tmp_path)
    work_dir = Path("data/artifacts/bakery_entry_translate_loop")
    work_dir.mkdir(parents=True)
    candidate = work_dir / "candidate_zh_CN.lua"
    candidate.write_text(
        """
return {
    descriptions = {
        Joker = {
            j_kept = {
                name = "保留小丑",
                text = {
                    "AI 已经翻好的文本",
                },
            },
            j_review = {
                name = "待审小丑",
                text = {
                    "AI 初稿",
                },
            },
        },
    },
}
""",
        encoding="utf-8",
    )
    (work_dir / "manifest.json").write_text(
        json.dumps({"output": str(candidate.resolve()), "rounds": []}),
        encoding="utf-8",
    )
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('bakery', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.execute(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text,
                edited_target_text, status, reason, reviewer
            ) values (
                'bakery', 'descriptions.Joker.j_review.text[0]',
                'Needs human edit', 'AI 初稿', '人工修订',
                'approved', 'ai_translation_review', 'human'
            )
            """
        )
        db.commit()

    result = apply_approved_review_items(db_path, "bakery")

    assert result["base"] == str(candidate.resolve())
    output = (localization / "zh_CN.lua").read_text(encoding="utf-8")
    assert "保留小丑" in output
    assert "AI 已经翻好的文本" in output
    assert "人工修订" in output
    assert "Already translated by AI" not in output


def test_api_exposes_tm_vector_outbox_and_pull_request_status(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('sample_mod', '/repos/sample', 'localization/en-us.lua', 'localization/zh_CN.lua')
            """
        )
        db.execute(
            """
            insert into tm_entries(
                mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (
                'sample_mod', 'descriptions.Joker.j_test.name', 'joker_name',
                'Test Joker', '测试小丑', 'test joker', '',
                'imported_human', 'point-1', 'source-hash', 'target-hash'
            )
            """
        )
        tm_id = db.execute("select id from tm_entries").fetchone()["id"]
        db.execute(
            """
            insert into vector_outbox(tm_entry_id, operation, collection, status)
            values (?, 'upsert', 'tm_qwen3_embedding_8b_v1', 'pending')
            """,
            (tm_id,),
        )
        db.execute(
            """
            insert into pull_requests(
                mod_id, repo_slug, branch, pr_number, title, html_url, state
            ) values (
                'sample_mod', 'owner/repo', 'bot/zh-cn', 12,
                'Update zh_CN', 'https://github.com/owner/repo/pull/12', 'open'
            )
            """
        )
        db.commit()

    client = TestClient(create_app(db_path=db_path))

    tm_entries = client.get("/api/tm-entries?mod_id=sample_mod")
    assert tm_entries.status_code == 200
    assert tm_entries.json()["items"][0]["target_text"] == "测试小丑"

    outbox = client.get("/api/vector-outbox?status=pending")
    assert outbox.status_code == 200
    assert outbox.json()["items"][0]["collection"] == "tm_qwen3_embedding_8b_v1"

    prs = client.get("/api/pull-requests?mod_id=sample_mod")
    assert prs.status_code == 200
    assert prs.json()["items"][0]["html_url"].endswith("/pull/12")


def test_static_frontend_is_served(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)

    client = TestClient(create_app(db_path=db_path))
    response = client.get("/")

    assert response.status_code == 200
    assert "Balatro CN" in response.text
    assert 'data-page="home"' in response.text
    assert 'data-page="mods"' in response.text
    assert 'data-page="admin"' not in response.text
    assert 'id="refresh"' not in response.text
    assert 'id="language-select"' in response.text


def test_dashboard_and_mod_index_use_balatro_mod_index_data(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    index_path = tmp_path / "all.json"
    report_path = tmp_path / "report.json"
    migrate(db_path)
    _write_mod_index(index_path)
    _write_probe_report(report_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into review_items(
                mod_id, unit_key, source_text, suggested_target_text, status, reason
            ) values (
                'Alpha Mod', 'descriptions.Joker.j_alpha.name',
                'Alpha', '阿尔法', 'pending', 'ai_translation_review'
            )
            """
        )
        db.commit()

    client = TestClient(
        create_app(
            db_path=db_path,
            mod_index_path=index_path,
            probe_report_path=report_path,
        )
    )

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.json()
    assert dashboard_payload["collected_mods"] == 3
    assert dashboard_payload["localized_mods"] == 1
    assert dashboard_payload["ai_translated_mods"] == 1
    assert dashboard_payload["last_updated_at"]

    mod_index = client.get("/api/mod-index?q=alpha&category=Content&page=1&page_size=10")
    assert mod_index.status_code == 200
    payload = mod_index.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Alpha Mod"
    assert payload["items"][0]["repo_url"] == "https://github.com/example/alpha"
    assert payload["items"][0]["original_page_url"] == "https://github.com/example/alpha"
    assert payload["items"][0]["ai_translation_repo_url"] is None
    assert payload["items"][0]["stars"] == 42
    assert payload["items"][0]["categories"] == ["Content", "Joker"]
    assert payload["items"][0]["requires_steamodded"] is True
    assert payload["items"][0]["requires_talisman"] is False
    assert payload["items"][0]["localization_status"] == "partial"
    assert payload["items"][0]["localization_status_label"] == "汉化部分（90%）"
    assert payload["items"][0]["ai_translation_status"] == "translated_needs_review"
    assert payload["items"][0]["ai_translation_status_label"] == "已经汉化（未review）"

    skipped = client.get("/api/mod-index?ai_status=skipped")
    assert skipped.status_code == 200
    assert skipped.json()["items"][0]["name"] == "Beta Utility"

    unprobed = client.get("/api/mod-index?q=gamma&page=1&page_size=10")
    assert unprobed.status_code == 200
    unprobed_item = unprobed.json()["items"][0]
    assert unprobed_item["localization_status"] == "unknown"
    assert unprobed_item["localization_status_label"] == "未探测"
    assert unprobed_item["ai_translation_status"] == "unknown"
    assert unprobed_item["ai_translation_status_label"] == "未探测"
