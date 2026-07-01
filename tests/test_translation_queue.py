from pathlib import Path
from typing import Any

from app.api.repositories import ApiRepository
from app.db.connection import connect
from app.db.migrate import migrate


def test_repository_adds_lists_reorders_and_cancels_queue_items(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)

    first = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )
    second = repo.enqueue_translation(
        mod_id="beta_mod",
        source_name="Beta Mod",
        repo_url="https://github.com/example/beta",
    )

    assert [item["id"] for item in repo.list_translation_queue(status="queued")] == [
        first["id"],
        second["id"],
    ]

    repo.reorder_translation_queue(second["id"], direction="up")
    assert repo.list_translation_queue(status="queued")[0]["id"] == second["id"]

    cancelled = repo.cancel_translation_queue_item(first["id"])
    assert cancelled["status"] == "cancelled"


def test_repository_rejects_duplicate_active_queue_item(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    try:
        repo.enqueue_translation(
            mod_id="alpha_mod",
            source_name="Alpha Mod",
            repo_url="https://github.com/example/alpha",
        )
    except ValueError as exc:
        assert "already queued" in str(exc)
    else:
        raise AssertionError("duplicate active queue item was accepted")


def test_repository_settings_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    migrate(db_path)
    repo = ApiRepository(db_path)

    settings = repo.get_admin_settings()
    assert settings["auto_translate_enabled"] is False
    assert settings["auto_translate_interval_hours"] == 5

    updated = repo.update_admin_settings(
        {
            "auto_translate_enabled": True,
            "auto_translate_interval_hours": 7,
        }
    )
    assert updated["auto_translate_enabled"] is True
    assert updated["auto_translate_interval_hours"] == 7


def test_start_queue_item_creates_translation_job(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    item = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import start_translation_queue_item

    job = start_translation_queue_item(
        db_path=db_path,
        queue_id=item["id"],
        background_tasks=None,
        translation_runner=lambda db_path, job_id, payload: None,
    )

    assert job["type"] == "translate_entry_loop"
    assert repo.get_translation_queue_item(item["id"])["status"] == "running"
    assert repo.get_translation_queue_item(item["id"])["locked_job_id"] == job["id"]


def test_scheduler_starts_one_due_item_when_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    repo.update_admin_settings(
        {
            "auto_translate_enabled": True,
            "last_auto_translate_at": None,
        }
    )
    repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import run_translation_queue_tick

    started = run_translation_queue_tick(
        db_path=db_path,
        translation_runner=lambda db_path, job_id, payload: None,
    )

    assert started is not None
    assert started["job"]["type"] == "translate_entry_loop"


def test_queue_item_syncs_to_succeeded_after_runner_finishes(tmp_path: Path) -> None:
    db_path = tmp_path / "balatro_cn.db"
    repo_path = tmp_path / "repos" / "alpha"
    (repo_path / "localization").mkdir(parents=True)
    (repo_path / "localization" / "en-us.lua").write_text("return {}\n", encoding="utf-8")
    (repo_path / "localization" / "zh_CN.lua").write_text("return {}\n", encoding="utf-8")
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into mod_sources(mod_id, repo_path, source_locale_path, target_locale_path)
            values ('alpha_mod', ?, 'localization/en-us.lua', 'localization/zh_CN.lua')
            """,
            (str(repo_path),),
        )
        db.commit()
    repo = ApiRepository(db_path)
    item = repo.enqueue_translation(
        mod_id="alpha_mod",
        source_name="Alpha Mod",
        repo_url="https://github.com/example/alpha",
    )

    from app.api.queue_workflow import start_translation_queue_item

    def finish_job(db_path: Path, job_id: int, payload: dict[str, Any]) -> None:
        ApiRepository(db_path).update_job_status(job_id, "succeeded")

    start_translation_queue_item(
        db_path=db_path,
        queue_id=item["id"],
        background_tasks=None,
        translation_runner=finish_job,
    )

    assert repo.get_translation_queue_item(item["id"])["status"] == "succeeded"
