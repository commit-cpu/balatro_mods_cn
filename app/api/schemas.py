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
LocalizationStatus = Literal["unknown", "none", "partial", "complete"]
AiTranslationStatus = Literal[
    "unknown",
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
    original_page_url: str | None
    ai_translation_repo_url: str | None
    ai_translation_branch_url: str | None = None
    stars: int
    categories: list[str]
    requires_steamodded: bool
    requires_talisman: bool
    localization_status: LocalizationStatus
    localization_status_label: str
    localization_progress: int
    ai_translation_status: AiTranslationStatus
    ai_translation_status_label: str
    translation_available: bool
    translation_mod_id: str | None
    workflow_status: str
    workflow_status_label: str
    next_action: str
    next_action_label: str
    workflow_updated_at: str | None = None
    cache_expires_at: str | None = None
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


class JobEventOut(BaseModel):
    id: int
    job_id: int
    level: str
    event: str
    message: str
    payload: dict[str, Any]
    created_at: str


class JobEventListResponse(BaseModel):
    items: list[JobEventOut]


class AdminSettingsOut(BaseModel):
    auto_translate_enabled: bool
    auto_translate_interval_hours: int = Field(ge=1)
    last_auto_translate_at: str | None = None


class AdminSettingsUpdate(BaseModel):
    auto_translate_enabled: bool | None = None
    auto_translate_interval_hours: int | None = Field(default=None, ge=1)


class TranslationQueueCreate(BaseModel):
    mod_id: str = Field(min_length=1)
    source_name: str | None = None
    repo_url: str | None = None


class TranslationQueueReorder(BaseModel):
    direction: Literal["up", "down"]


class TranslationQueueOut(BaseModel):
    id: int
    mod_id: str
    source_name: str | None
    repo_url: str | None
    priority: int
    status: str
    locked_job_id: int | None
    last_error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class TranslationQueueListResponse(BaseModel):
    items: list[TranslationQueueOut]


class AdminModOut(BaseModel):
    name: str
    repo_url: str | None
    translation_mod_id: str | None
    translation_available: bool
    localization_status: LocalizationStatus
    localization_status_label: str
    ai_translation_status: AiTranslationStatus
    ai_translation_status_label: str
    workflow_status: str
    workflow_status_label: str
    next_action: str
    next_action_label: str
    pending_review_items: int
    approved_review_items: int
    queue_status: str | None
    queue_id: int | None
    latest_job_status: str | None
    fork_slug: str | None
    latest_fork_branch_url: str | None


class AdminModListResponse(BaseModel):
    items: list[AdminModOut]


class TranslationStart(BaseModel):
    limit: int = Field(default=9999, ge=1)
    top_k: int = Field(default=5, ge=1)
    max_width: int = Field(default=25, ge=4)
    concurrency: int | None = Field(default=None, ge=1)
    max_rounds: int = Field(default=3, ge=1)
    include_needs_review: bool = False
    validate_lua: bool = True


class GitHubProbeStart(BaseModel):
    limit: int = Field(default=500, ge=1)
    mod_name: str | None = None
    repo_url: str | None = None
    refresh_cache: bool = False
    cache_ttl_seconds: int = Field(default=6 * 60 * 60, ge=0)


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


class ReviewModOut(BaseModel):
    mod_id: str
    pending_items: int
    entry_groups: int
    latest_updated_at: str | None


class ReviewModListResponse(BaseModel):
    items: list[ReviewModOut]


class ReviewGroupItemOut(ReviewItemOut):
    field: str


class ReviewGroupOut(BaseModel):
    mod_id: str
    entry_key: str
    item_count: int
    status: ReviewStatus
    latest_updated_at: str | None
    items: list[ReviewGroupItemOut]


class ReviewGroupListResponse(BaseModel):
    items: list[ReviewGroupOut]
    total: int = 0
    page: int = 1
    page_size: int = 100


class ReviewGroupApprove(BaseModel):
    item_ids: list[int] = Field(min_length=1)
    edited_target_texts: dict[str, str] = Field(default_factory=dict)
    reviewer: str | None = None
    comment: str | None = None


class ReviewGroupUpdateResponse(BaseModel):
    updated: int
    items: list[ReviewItemOut]


class ApplyApprovedResponse(BaseModel):
    mod_id: str
    output: str
    applied_items: int
    applied_entries: int
    applied_units: int


class PublishForkResponse(BaseModel):
    mod_id: str
    repo_slug: str
    branch: str
    commit_sha: str
    target_path: str
    html_url: str


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
