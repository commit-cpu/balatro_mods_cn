from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FeedbackType = Literal[
    "semantic_error",
    "term_inconsistent",
    "unnatural",
    "format_error",
    "untranslated",
    "other",
]
FeedbackStatus = Literal["pending", "accepted", "rejected", "applied"]
JobStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]
ReviewStatus = Literal["pending", "approved", "rejected", "needs_changes"]
LocalizationStatus = Literal["none", "partial", "complete"]
AiTranslationStatus = Literal[
    "skipped",
    "running",
    "translated_needs_review",
    "complete",
    "merged_upstream",
]


class SummaryResponse(BaseModel):
    counts: dict[str, int]


class DashboardResponse(BaseModel):
    collected_mods: int
    localized_mods: int
    ai_translated_mods: int
    last_updated_at: str | None


class ModIndexItemOut(BaseModel):
    name: str
    repo_url: str | None
    stars: int
    categories: list[str]
    requires_steamodded: bool
    requires_talisman: bool
    localization_status: LocalizationStatus
    localization_status_label: str
    localization_progress: int
    ai_translation_status: AiTranslationStatus
    ai_translation_status_label: str
    source_units: int
    zh_units: int
    missing_keys: int
    untranslated_keys: int
    residual_english: int


class ModIndexResponse(BaseModel):
    items: list[ModIndexItemOut]
    total: int
    page: int
    page_size: int
    categories: list[str]


class ModSourceOut(BaseModel):
    id: int
    mod_id: str
    repo_path: str
    source_locale_path: str
    target_locale_path: str
    import_enabled: bool
    created_at: str


class ModListResponse(BaseModel):
    items: list[ModSourceOut]


class JobOut(BaseModel):
    id: int
    type: str
    status: JobStatus
    idempotency_key: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    last_error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class JobListResponse(BaseModel):
    items: list[JobOut]


class ReviewItemOut(BaseModel):
    id: int
    mod_id: str
    unit_key: str
    source_text: str
    current_target_text: str | None
    suggested_target_text: str | None
    edited_target_text: str | None
    reason: str
    status: ReviewStatus
    reviewer: str | None
    comment: str | None
    created_at: str
    updated_at: str
    reviewed_at: str | None


class ReviewItemListResponse(BaseModel):
    items: list[ReviewItemOut]
    total: int = 0
    page: int = 1
    page_size: int = 100


class ReviewItemUpdate(BaseModel):
    status: ReviewStatus | None = None
    edited_target_text: str | None = None
    reviewer: str | None = None
    comment: str | None = None


class FeedbackCreate(BaseModel):
    mod_id: str = Field(min_length=1)
    unit_key: str = Field(min_length=1)
    translation_id: str | None = None
    feedback_type: FeedbackType
    suggested_text: str | None = None
    comment: str | None = None


class FeedbackOut(BaseModel):
    id: int
    mod_id: str
    unit_key: str
    translation_id: str | None
    feedback_type: FeedbackType
    suggested_text: str | None
    comment: str | None
    status: FeedbackStatus
    created_at: str
    updated_at: str


class FeedbackCreated(BaseModel):
    id: int
    status: FeedbackStatus
    feedback: FeedbackOut
    job: JobOut


class FeedbackListResponse(BaseModel):
    items: list[FeedbackOut]


class TmEntryOut(BaseModel):
    id: int
    mod_id: str
    unit_key: str
    context_type: str
    source_text: str
    target_text: str
    quality: str
    qdrant_point_id: str
    source_hash: str
    target_hash: str
    created_at: str
    updated_at: str


class TmEntryListResponse(BaseModel):
    items: list[TmEntryOut]


class VectorOutboxOut(BaseModel):
    id: int
    tm_entry_id: int
    operation: str
    collection: str
    status: str
    attempts: int
    last_error: str | None
    created_at: str
    updated_at: str


class VectorOutboxListResponse(BaseModel):
    items: list[VectorOutboxOut]


class PullRequestOut(BaseModel):
    id: int
    mod_id: str
    repo_slug: str
    branch: str
    pr_number: int | None
    title: str | None
    html_url: str | None
    state: str
    last_commit_sha: str | None
    created_at: str
    updated_at: str


class PullRequestListResponse(BaseModel):
    items: list[PullRequestOut]
