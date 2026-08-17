"""Pydantic request/response models (API contract only).

Event payload models (§3.3) are built by the worker and serialized with `model_dump(mode="json")`
before being persisted, so every stored value is JSON-safe (ISO timestamps, not `datetime`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

# --- Event payloads (§3.3) ---


class JobQueuedEvent(BaseModel):
    job_id: str
    batch_id: str
    status: str = "queued"
    queue_position: int | None = None
    at: datetime


class JobStatusEvent(BaseModel):
    job_id: str
    batch_id: str
    status: str
    account_email: str | None = None
    attempt: int | None = None
    at: datetime


class JobProgressEvent(BaseModel):
    job_id: str
    batch_id: str
    stage: str
    elapsed_seconds: float | None = None
    eta_seconds: float | None = None


class JobCompletedEvent(BaseModel):
    job_id: str
    batch_id: str
    image_count: int
    duration_seconds: float | None = None
    at: datetime


class JobFailedEvent(BaseModel):
    job_id: str
    batch_id: str
    error_code: str | None = None
    error_message: str | None = None
    attempt: int | None = None
    at: datetime


class JobCanceledEvent(BaseModel):
    job_id: str
    batch_id: str
    at: datetime


class BatchStatusEvent(BaseModel):
    batch_id: str
    status: str
    progress: float | None = None
    at: datetime


class BatchCompletedEvent(BaseModel):
    batch_id: str
    status: str
    at: datetime


class QueueStatsEvent(BaseModel):
    queued: int
    running: int
    free_slots: int
    total_slots: int
    throughput_jobs_per_hour: float | None = None
    avg_duration_seconds: float | None = None
    eta_seconds: float | None = None
    at: datetime


class StreamOverflowEvent(BaseModel):
    message: str


# --- Task submit (§2.8 / Phase 7) ---


class TaskSubmitRequest(BaseModel):
    provider: str = "google_flow"
    kind: str = "image"
    prompts: list[str] = Field(min_length=1)
    count: int = Field(default=1, ge=1)
    priority: int = 0
    timeout_seconds: float = Field(default=180.0, gt=0)
    params: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    # Resume an existing provider workspace/thread; only valid for single-prompt requests.
    workspace_ref: str | None = None

    @field_validator("prompts")
    @classmethod
    def _non_empty_prompts(cls, value: list[str]) -> list[str]:
        if any(not prompt.strip() for prompt in value):
            raise ValueError("prompts must not contain empty strings")
        return value


class JobRef(BaseModel):
    job_id: str
    prompt: str
    status: str
    queue_position: int | None = None


class TaskSubmitResponse(BaseModel):
    batch_id: str
    status: str
    jobs: list[JobRef]
    estimated_start_at: datetime | None = None
    estimated_finish_at: datetime | None = None
    warnings: list[str] = []


# --- Job & batch queries (§2.8) ---


class ArtifactResponse(BaseModel):
    id: str
    job_id: str | None
    kind: str
    mime: str | None
    text: str | None
    prompt: str | None
    created_at: datetime
    bytes: int | None
    width: int | None
    height: int | None
    format: str | None
    sha256: str | None
    meta: dict[str, Any]
    url: str | None
    thumbnail_url: str | None


class JobResponse(BaseModel):
    id: str
    batch_id: str
    provider: str
    kind: str
    prompt: str
    count: int
    timeout_seconds: float
    params: dict[str, Any]
    priority: int
    status: str
    attempt: int
    max_attempts: int
    attempted_emails: list[str]
    account_email: str | None
    workspace_ref: str | None
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = []
    artifacts: list[ArtifactResponse] = []
    elapsed_seconds: float | None = None
    eta_seconds: float | None = None


class RunningJobResponse(BaseModel):
    id: str
    batch_id: str
    prompt: str
    account_email: str | None
    started_at: datetime | None
    elapsed_seconds: float | None
    eta_seconds: float | None


class BatchResponse(BaseModel):
    id: str
    status: str
    job_count: int
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    counts: dict[str, int]
    progress: float
    estimated_finish_at: datetime | None = None
    warnings: list[str] = []


# --- Provider discovery (§2.8 / Phase 7) ---


class CapabilitiesResponse(BaseModel):
    task_kinds: list[str]
    max_outputs_per_request: int
    supports_reference_inputs: bool
    supports_workspace_reuse: bool
    requires_browser: bool


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    capabilities: CapabilitiesResponse


class ProviderDetail(BaseModel):
    name: str
    display_name: str
    capabilities: CapabilitiesResponse
    params_schema: dict[str, Any]


# --- Operations (§3.6) ---


class AccountStatusResponse(BaseModel):
    email: str
    status: str
    in_flight: int
    limit: int
    success_count: int
    fail_count: int
    cooldown_until: datetime | None
    last_used_at: datetime | None


class StatsResponse(BaseModel):
    queued: int
    running: int
    completed: int
    failed: int
    canceled: int
    total_slots: int
    free_slots: int
    throughput_jobs_per_hour: float | None
    avg_duration_seconds: float | None
    eta_seconds: float | None
    images_total: int
    bytes_total: int


# --- Pagination envelope (§3.5) ---

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_next: bool
