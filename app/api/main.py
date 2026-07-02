from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.admin_auth import (
    ADMIN_COOKIE_NAME,
    admin_auth_enabled,
    admin_route_path,
    require_admin,
    set_admin_cookie,
    validate_admin_secret,
)
from app.api.repositories import ApiRepository
from app.api.github_workflow import (
    github_probe_payload,
    materialize_github_localization_source,
    run_github_probe_job,
)
from app.api.publish_workflow import publish_mod_to_fork
from app.api.queue_workflow import run_translation_queue_tick
from app.api.queue_workflow import start_translation_queue_item
from app.api.schemas import (
    AdminModListResponse,
    AdminModOut,
    AdminSettingsOut,
    AdminSettingsUpdate,
    ApplyApprovedResponse,
    DashboardResponse,
    FeedbackCreate,
    FeedbackCreated,
    FeedbackListResponse,
    FeedbackOut,
    GitHubProbeStart,
    JobListResponse,
    JobOut,
    JobEventListResponse,
    JobEventOut,
    ModIndexItemOut,
    ModIndexResponse,
    ModListResponse,
    ModSourceOut,
    PullRequestListResponse,
    PullRequestOut,
    PublishForkResponse,
    ReviewGroupApprove,
    ReviewGroupListResponse,
    ReviewGroupOut,
    ReviewGroupUpdateResponse,
    ReviewItemListResponse,
    ReviewItemOut,
    ReviewItemUpdate,
    ReviewModListResponse,
    ReviewModOut,
    SummaryResponse,
    TmEntryListResponse,
    TmEntryOut,
    TranslationStart,
    TranslationQueueCreate,
    TranslationQueueListResponse,
    TranslationQueueOut,
    TranslationQueueReorder,
    VectorOutboxListResponse,
    VectorOutboxOut,
)
from app.api.translation_workflow import (
    apply_approved_review_items,
    run_translation_job,
    translation_payload,
)
from app.config import load_settings
from app.db.migrate import migrate


STATIC_DIR = Path(__file__).with_name("static")


def create_app(
    db_path: Path | str | None = None,
    *,
    mod_index_path: Path | str | None = None,
    probe_report_path: Path | str | None = None,
    translation_runner: Callable[[Path, int, dict[str, Any]], None] = run_translation_job,
    github_probe_runner: Callable[[Path, int, dict[str, Any]], None] = run_github_probe_job,
) -> FastAPI:
    settings = load_settings()
    resolved_db_path = Path(db_path or settings.sqlite.database_path)
    migrate(resolved_db_path)
    app = FastAPI(title="Balatro CN API", version="0.1.0")
    repository_kwargs = {}
    if mod_index_path is not None:
        repository_kwargs["mod_index_path"] = mod_index_path
    if probe_report_path is not None:
        repository_kwargs["probe_report_path"] = probe_report_path
    app.state.repository = ApiRepository(resolved_db_path, **repository_kwargs)
    app.state.translation_runner = translation_runner
    app.state.github_probe_runner = github_probe_runner
    app.state.queue_scheduler_stop = False

    def get_repository() -> ApiRepository:
        return app.state.repository

    @app.on_event("startup")
    async def start_translation_queue_scheduler() -> None:
        app.state.repository.mark_interrupted_translation_jobs_failed(
            "server restarted before translation job completed; start translation again to resume from artifacts"
        )
        if not settings.scheduler.enabled:
            return
        app.state.queue_scheduler_stop = False
        app.state.queue_scheduler_task = asyncio.create_task(
            _queue_scheduler_loop(app, resolved_db_path)
        )

    @app.on_event("shutdown")
    async def stop_translation_queue_scheduler() -> None:
        app.state.queue_scheduler_stop = True
        task = getattr(app.state, "queue_scheduler_task", None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="frontend not built")
        return FileResponse(index_path)

    @app.get("/about", include_in_schema=False)
    @app.get("/mods", include_in_schema=False)
    def frontend_page() -> FileResponse:
        return index()

    if not admin_auth_enabled():
        app.get("/admin", include_in_schema=False)(frontend_page)

    @app.get(admin_route_path(), include_in_schema=False, response_model=None)
    def admin_page(request: Request, sk: str | None = None) -> Response:
        cookie_value = request.cookies.get(ADMIN_COOKIE_NAME)
        if sk:
            try:
                validate_admin_secret(sk)
            except HTTPException:
                return _admin_login_page(admin_route_path(), error="invalid sk", status_code=401)
            page = index()
            set_admin_cookie(page)
            return page
        try:
            validate_admin_secret(cookie_value)
        except HTTPException:
            return _admin_login_page(admin_route_path())
        page = index()
        set_admin_cookie(page)
        return page

    @app.post(admin_route_path(), include_in_schema=False, response_model=None)
    async def admin_login(request: Request) -> Response:
        body = (await request.body()).decode("utf-8", errors="replace")
        values = parse_qs(body)
        sk = values.get("sk", [""])[0]
        try:
            validate_admin_secret(sk)
        except HTTPException:
            return _admin_login_page(admin_route_path(), error="invalid sk", status_code=401)
        response = RedirectResponse(admin_route_path(), status_code=303)
        set_admin_cookie(response)
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/summary", response_model=SummaryResponse)
    def summary(repo: ApiRepository = Depends(get_repository)) -> SummaryResponse:
        return SummaryResponse(counts=repo.summary())

    @app.get("/api/dashboard", response_model=DashboardResponse)
    def dashboard(repo: ApiRepository = Depends(get_repository)) -> DashboardResponse:
        return DashboardResponse(**repo.dashboard())

    @app.get("/api/mod-index", response_model=ModIndexResponse)
    def mod_index(
        q: str | None = None,
        category: str | None = None,
        localization_status: str | None = Query(default=None, alias="l10n_status"),
        ai_status: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        repo: ApiRepository = Depends(get_repository),
    ) -> ModIndexResponse:
        payload = repo.mod_index(
            q=q,
            category=category,
            localization_status=localization_status,
            ai_status=ai_status,
            page=page,
            page_size=page_size,
        )
        return ModIndexResponse(
            items=[ModIndexItemOut(**item) for item in payload["items"]],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            categories=payload["categories"],
        )

    @app.get("/api/mods", response_model=ModListResponse)
    def list_mods(
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ModListResponse:
        return ModListResponse(items=[ModSourceOut(**item) for item in repo.list_mods(limit=limit)])

    @app.get("/api/mods/{mod_id}", response_model=ModSourceOut)
    def get_mod(
        mod_id: str,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ModSourceOut:
        item = repo.get_mod(mod_id)
        if item is None:
            raise HTTPException(status_code=404, detail="mod not found")
        return ModSourceOut(**item)

    @app.post(
        "/api/github/probe",
        response_model=JobOut,
        status_code=status.HTTP_201_CREATED,
    )
    def start_github_probe(
        request: GitHubProbeStart,
        background_tasks: BackgroundTasks,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobOut:
        payload = github_probe_payload(
            index_path=repo.mod_index_path,
            report_path=repo.probe_report_path,
            limit=request.limit,
            fork=False,
            refresh_cache=request.refresh_cache,
            mod_name=request.mod_name,
            repo_url=request.repo_url,
            cache_ttl_seconds=request.cache_ttl_seconds,
        )
        job, created = repo.create_github_probe_job(
            job_type="github_l10n_probe",
            payload=payload,
        )
        if created:
            background_tasks.add_task(
                app.state.github_probe_runner,
                resolved_db_path,
                job["id"],
                job["payload"],
            )
        return JobOut(**job)

    @app.post(
        "/api/github/forks",
        response_model=JobOut,
        status_code=status.HTTP_201_CREATED,
    )
    def start_github_forks(
        request: GitHubProbeStart,
        background_tasks: BackgroundTasks,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobOut:
        payload = github_probe_payload(
            index_path=repo.mod_index_path,
            report_path=repo.probe_report_path,
            limit=request.limit,
            fork=True,
            refresh_cache=request.refresh_cache,
            mod_name=request.mod_name,
            repo_url=request.repo_url,
            cache_ttl_seconds=request.cache_ttl_seconds,
        )
        job, created = repo.create_github_probe_job(
            job_type="github_fork_probe",
            payload=payload,
        )
        if created:
            background_tasks.add_task(
                app.state.github_probe_runner,
                resolved_db_path,
                job["id"],
                job["payload"],
            )
        return JobOut(**job)

    @app.post("/api/github/localization-source", response_model=ModSourceOut)
    def prepare_github_localization_source(
        request: GitHubProbeStart,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ModSourceOut:
        try:
            mod = materialize_github_localization_source(
                db_path=resolved_db_path,
                index_path=repo.mod_index_path,
                mod_name=request.mod_name,
                repo_url=request.repo_url,
                refresh_cache=request.refresh_cache,
                cache_ttl_seconds=request.cache_ttl_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ModSourceOut(**mod)

    @app.post(
        "/api/mods/{mod_id}/translate",
        response_model=JobOut,
        status_code=status.HTTP_201_CREATED,
    )
    def start_mod_translation(
        mod_id: str,
        request: TranslationStart,
        background_tasks: BackgroundTasks,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobOut:
        mod = repo.get_mod(mod_id)
        if mod is None:
            raise HTTPException(status_code=404, detail="mod not found")
        job, created = repo.create_translation_job(
            mod_id=mod_id,
            payload=translation_payload(mod, request),
        )
        if created:
            background_tasks.add_task(
                app.state.translation_runner,
                resolved_db_path,
                job["id"],
                job["payload"],
            )
        return JobOut(**job)

    @app.post("/api/mods/{mod_id}/apply-approved", response_model=ApplyApprovedResponse)
    def apply_mod_approved_reviews(
        mod_id: str,
        _admin: None = Depends(require_admin),
    ) -> ApplyApprovedResponse:
        try:
            payload = apply_approved_review_items(resolved_db_path, mod_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="mod not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ApplyApprovedResponse(**payload)

    @app.post("/api/mods/{mod_id}/publish-fork", response_model=PublishForkResponse)
    def publish_mod_fork(
        mod_id: str,
        _admin: None = Depends(require_admin),
    ) -> PublishForkResponse:
        try:
            payload = publish_mod_to_fork(db_path=resolved_db_path, mod_id=mod_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="mod not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return PublishForkResponse(**payload)

    @app.get("/api/jobs", response_model=JobListResponse)
    def list_jobs(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobListResponse:
        return JobListResponse(
            items=[
                JobOut(**item)
                for item in repo.list_jobs(status=status_filter, limit=limit)
            ]
        )

    @app.get("/api/jobs/{job_id}", response_model=JobOut)
    def get_job(
        job_id: int,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobOut:
        item = repo.get_job(job_id)
        if item is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobOut(**item)

    @app.get("/api/jobs/{job_id}/events", response_model=JobEventListResponse)
    def list_job_events(
        job_id: int,
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> JobEventListResponse:
        if repo.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobEventListResponse(
            items=[JobEventOut(**item) for item in repo.list_job_events(job_id, limit=limit)]
        )

    @app.get("/api/admin/settings", response_model=AdminSettingsOut)
    def get_admin_settings(
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> AdminSettingsOut:
        return AdminSettingsOut(**repo.get_admin_settings())

    @app.patch("/api/admin/settings", response_model=AdminSettingsOut)
    def update_admin_settings(
        update: AdminSettingsUpdate,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> AdminSettingsOut:
        return AdminSettingsOut(
            **repo.update_admin_settings(update.model_dump(exclude_none=True))
        )

    @app.get("/api/admin/mods", response_model=AdminModListResponse)
    def list_admin_mods(
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> AdminModListResponse:
        return AdminModListResponse(
            items=[AdminModOut(**item) for item in repo.admin_mods()]
        )

    @app.get("/api/translation-queue", response_model=TranslationQueueListResponse)
    def list_translation_queue(
        status_filter: str | None = Query(default=None, alias="status"),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TranslationQueueListResponse:
        return TranslationQueueListResponse(
            items=[
                TranslationQueueOut(**item)
                for item in repo.list_translation_queue(status=status_filter)
            ]
        )

    @app.post(
        "/api/translation-queue",
        response_model=TranslationQueueOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_translation_queue_item(
        request: TranslationQueueCreate,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TranslationQueueOut:
        try:
            item = repo.enqueue_translation(
                mod_id=request.mod_id,
                source_name=request.source_name,
                repo_url=request.repo_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TranslationQueueOut(**item)

    @app.patch("/api/translation-queue/{queue_id}", response_model=TranslationQueueOut)
    def reorder_translation_queue_item(
        queue_id: int,
        request: TranslationQueueReorder,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TranslationQueueOut:
        try:
            item = repo.reorder_translation_queue(queue_id, direction=request.direction)
        except KeyError:
            raise HTTPException(status_code=404, detail="queue item not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TranslationQueueOut(**item)

    @app.post("/api/translation-queue/{queue_id}/start", response_model=JobOut)
    def start_translation_queue(
        queue_id: int,
        background_tasks: BackgroundTasks,
        _admin: None = Depends(require_admin),
    ) -> JobOut:
        try:
            job = start_translation_queue_item(
                db_path=resolved_db_path,
                queue_id=queue_id,
                background_tasks=background_tasks,
                translation_runner=app.state.translation_runner,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="queue item not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return JobOut(**job)

    @app.post("/api/translation-queue/{queue_id}/retry", response_model=TranslationQueueOut)
    def retry_translation_queue(
        queue_id: int,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TranslationQueueOut:
        try:
            item = repo.retry_translation_queue_item(queue_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="queue item not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TranslationQueueOut(**item)

    @app.delete("/api/translation-queue/{queue_id}", response_model=TranslationQueueOut)
    def delete_translation_queue(
        queue_id: int,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TranslationQueueOut:
        try:
            item = repo.cancel_translation_queue_item(queue_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="queue item not found") from None
        return TranslationQueueOut(**item)

    @app.get("/api/review-items", response_model=ReviewItemListResponse)
    def list_review_items(
        status_filter: str | None = Query(default=None, alias="status"),
        mod_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewItemListResponse:
        resolved_page_size = page_size or limit
        total = repo.count_review_items(status=status_filter, mod_id=mod_id)
        return ReviewItemListResponse(
            items=[
                ReviewItemOut(**item)
                for item in repo.list_review_items(
                    status=status_filter,
                    mod_id=mod_id,
                    limit=resolved_page_size,
                    offset=(page - 1) * resolved_page_size,
                )
            ],
            total=total,
            page=page,
            page_size=resolved_page_size,
        )

    @app.get("/api/review-mods", response_model=ReviewModListResponse)
    def list_review_mods(
        status_filter: str | None = Query(default=None, alias="status"),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewModListResponse:
        return ReviewModListResponse(
            items=[
                ReviewModOut(**item)
                for item in repo.list_review_mods(status=status_filter)
            ]
        )

    @app.get("/api/review-groups", response_model=ReviewGroupListResponse)
    def list_review_groups(
        status_filter: str | None = Query(default=None, alias="status"),
        mod_id: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewGroupListResponse:
        payload = repo.list_review_groups(
            status=status_filter,
            mod_id=mod_id,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return ReviewGroupListResponse(
            items=[ReviewGroupOut(**item) for item in payload["items"]],
            total=payload["total"],
            page=page,
            page_size=page_size,
        )

    @app.patch("/api/review-groups/approve", response_model=ReviewGroupUpdateResponse)
    def approve_review_group(
        update: ReviewGroupApprove,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewGroupUpdateResponse:
        try:
            items = repo.approve_review_group(update)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if len(items) != len(update.item_ids):
            raise HTTPException(status_code=404, detail="review item not found")
        return ReviewGroupUpdateResponse(
            updated=len(items),
            items=[ReviewItemOut(**item) for item in items],
        )

    @app.get("/api/review-items/{item_id}", response_model=ReviewItemOut)
    def get_review_item(
        item_id: int,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewItemOut:
        item = repo.get_review_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="review item not found")
        return ReviewItemOut(**item)

    @app.patch("/api/review-items/{item_id}", response_model=ReviewItemOut)
    def update_review_item(
        item_id: int,
        update: ReviewItemUpdate,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> ReviewItemOut:
        item = repo.update_review_item(item_id, update)
        if item is None:
            raise HTTPException(status_code=404, detail="review item not found")
        return ReviewItemOut(**item)

    @app.get("/api/feedback", response_model=FeedbackListResponse)
    def list_feedback(
        status_filter: str | None = Query(default=None, alias="status"),
        mod_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> FeedbackListResponse:
        return FeedbackListResponse(
            items=[
                FeedbackOut(**item)
                for item in repo.list_feedback(
                    status=status_filter,
                    mod_id=mod_id,
                    limit=limit,
                )
            ]
        )

    @app.get("/api/feedback/{feedback_id}", response_model=FeedbackOut)
    def get_feedback(
        feedback_id: int,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> FeedbackOut:
        item = repo.get_feedback(feedback_id)
        if item is None:
            raise HTTPException(status_code=404, detail="feedback not found")
        return FeedbackOut(**item)

    @app.get("/api/tm-entries", response_model=TmEntryListResponse)
    def list_tm_entries(
        mod_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> TmEntryListResponse:
        return TmEntryListResponse(
            items=[
                TmEntryOut(**item)
                for item in repo.list_tm_entries(mod_id=mod_id, limit=limit)
            ]
        )

    @app.get("/api/vector-outbox", response_model=VectorOutboxListResponse)
    def list_vector_outbox(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> VectorOutboxListResponse:
        return VectorOutboxListResponse(
            items=[
                VectorOutboxOut(**item)
                for item in repo.list_vector_outbox(
                    status=status_filter,
                    limit=limit,
                )
            ]
        )

    @app.get("/api/pull-requests", response_model=PullRequestListResponse)
    def list_pull_requests(
        mod_id: str | None = None,
        state: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> PullRequestListResponse:
        return PullRequestListResponse(
            items=[
                PullRequestOut(**item)
                for item in repo.list_pull_requests(
                    mod_id=mod_id,
                    state=state,
                    limit=limit,
                )
            ]
        )

    @app.post(
        "/api/feedback",
        response_model=FeedbackCreated,
        status_code=status.HTTP_201_CREATED,
    )
    def create_feedback(
        feedback: FeedbackCreate,
        _admin: None = Depends(require_admin),
        repo: ApiRepository = Depends(get_repository),
    ) -> FeedbackCreated:
        feedback_row, job_row = repo.create_feedback_with_job(feedback)
        return FeedbackCreated(
            id=feedback_row["id"],
            status=feedback_row["status"],
            feedback=FeedbackOut(**feedback_row),
            job=JobOut(**job_row),
        )

    return app


async def _queue_scheduler_loop(app: FastAPI, db_path: Path) -> None:
    while not getattr(app.state, "queue_scheduler_stop", False):
        try:
            run_translation_queue_tick(
                db_path=db_path,
                translation_runner=app.state.translation_runner,
            )
        except Exception:
            pass
        await asyncio.sleep(60)


def _admin_login_page(action: str, *, error: str = "", status_code: int = 200) -> HTMLResponse:
    error_html = f'<div class="error">{error}</div>' if error else ""
    return HTMLResponse(
        f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Admin Verify</title>
    <style>
      body {{
        align-items: center;
        background: #110f1a;
        color: #fff3cf;
        display: grid;
        font-family: system-ui, sans-serif;
        min-height: 100vh;
        margin: 0;
      }}
      form {{
        border: 2px solid rgba(255, 243, 207, 0.32);
        display: grid;
        gap: 12px;
        margin: auto;
        max-width: 360px;
        padding: 24px;
        width: calc(100% - 48px);
      }}
      input, button {{
        box-sizing: border-box;
        font: inherit;
        padding: 10px 12px;
        width: 100%;
      }}
      button {{
        background: #ffd85a;
        border: 0;
        color: #1b1308;
        cursor: pointer;
        font-weight: 700;
      }}
      .error {{ color: #ff817a; }}
    </style>
  </head>
  <body>
    <form method="post" action="{action}">
      <strong>需要验证 sk</strong>
      {error_html}
      <input name="sk" type="password" autocomplete="current-password" autofocus placeholder="输入 ADMIN_SECRET_KEY" />
      <button type="submit">进入管理员页面</button>
    </form>
  </body>
</html>""",
        status_code=status_code,
    )


class LazyApp:
    def __init__(self) -> None:
        self._app: FastAPI | None = None

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = LazyApp()
