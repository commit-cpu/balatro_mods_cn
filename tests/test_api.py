from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
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
    assert dashboard_payload["collected_mods"] == 2
    assert dashboard_payload["localized_mods"] == 1
    assert dashboard_payload["ai_translated_mods"] == 1
    assert dashboard_payload["last_updated_at"]

    mod_index = client.get("/api/mod-index?q=alpha&category=Content&page=1&page_size=10")
    assert mod_index.status_code == 200
    payload = mod_index.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Alpha Mod"
    assert payload["items"][0]["repo_url"] == "https://github.com/example/alpha"
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
