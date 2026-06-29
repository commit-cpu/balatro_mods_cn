from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.repositories import ApiRepository
from app.api.schemas import (
    DashboardResponse,
    FeedbackCreate,
    FeedbackCreated,
    FeedbackListResponse,
    FeedbackOut,
    JobListResponse,
    JobOut,
    ModIndexItemOut,
    ModIndexResponse,
    ModListResponse,
    ModSourceOut,
    PullRequestListResponse,
    PullRequestOut,
    ReviewItemListResponse,
    ReviewItemOut,
    ReviewItemUpdate,
    SummaryResponse,
    TmEntryListResponse,
    TmEntryOut,
    VectorOutboxListResponse,
    VectorOutboxOut,
)
from app.config import load_settings


STATIC_DIR = Path(__file__).with_name("static")


def create_app(
    db_path: Path | str | None = None,
    *,
    mod_index_path: Path | str | None = None,
    probe_report_path: Path | str | None = None,
) -> FastAPI:
    settings = load_settings()
    resolved_db_path = Path(db_path or settings.sqlite.database_path)
    app = FastAPI(title="Balatro CN API", version="0.1.0")
    repository_kwargs = {}
    if mod_index_path is not None:
        repository_kwargs["mod_index_path"] = mod_index_path
    if probe_report_path is not None:
        repository_kwargs["probe_report_path"] = probe_report_path
    app.state.repository = ApiRepository(resolved_db_path, **repository_kwargs)

    def get_repository() -> ApiRepository:
        return app.state.repository

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="frontend not built")
        return FileResponse(index_path)

    @app.get("/admin", include_in_schema=False)
    @app.get("/about", include_in_schema=False)
    @app.get("/mods", include_in_schema=False)
    def frontend_page() -> FileResponse:
        return index()

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
        repo: ApiRepository = Depends(get_repository),
    ) -> ModListResponse:
        return ModListResponse(items=[ModSourceOut(**item) for item in repo.list_mods(limit=limit)])

    @app.get("/api/mods/{mod_id}", response_model=ModSourceOut)
    def get_mod(
        mod_id: str,
        repo: ApiRepository = Depends(get_repository),
    ) -> ModSourceOut:
        item = repo.get_mod(mod_id)
        if item is None:
            raise HTTPException(status_code=404, detail="mod not found")
        return ModSourceOut(**item)

    @app.get("/api/jobs", response_model=JobListResponse)
    def list_jobs(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
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
        repo: ApiRepository = Depends(get_repository),
    ) -> JobOut:
        item = repo.get_job(job_id)
        if item is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobOut(**item)

    @app.get("/api/review-items", response_model=ReviewItemListResponse)
    def list_review_items(
        status_filter: str | None = Query(default=None, alias="status"),
        mod_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        page: int = Query(default=1, ge=1),
        page_size: int | None = Query(default=None, ge=1, le=500),
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

    @app.get("/api/review-items/{item_id}", response_model=ReviewItemOut)
    def get_review_item(
        item_id: int,
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
app = create_app()
