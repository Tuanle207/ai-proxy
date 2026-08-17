"""Domain models for accounts and generation requests/results."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel, Field, field_validator


class TaskKind(enum.StrEnum):
    """The artifact modality a provider can produce for a task."""

    IMAGE = "image"
    TEXT = "text"
    VIDEO = "video"
    FILE = "file"


# A provider-owned, opaque handle to a destination "workspace" (Flow project, Perplexity thread).
# Stored on jobs as ``workspace_ref`` and passed back to the provider's cleanup hook.
WorkspaceRef: TypeAlias = str


class AccountStatus(enum.StrEnum):
    """Lifecycle status of a managed Google account."""

    ACTIVE = "active"
    DISABLED = "disabled"
    NEEDS_LOGIN = "needs_login"
    COOLDOWN = "cooldown"


class JobStatus(enum.StrEnum):
    """Lifecycle status of a single generation job (§4.6)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class BatchStatus(enum.StrEnum):
    """Derived lifecycle status of a batch of jobs (§4.6)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELED = "canceled"


class Account(BaseModel):
    """A registered Google account used to drive Flow generations."""

    email: str
    label: str | None = None
    proxy: str | None = None
    status: AccountStatus = AccountStatus.NEEDS_LOGIN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    success_count: int = 0
    fail_count: int = 0
    cooldown_until: datetime | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError(f"invalid email address: {value!r}")
        return value

    def is_available(self, now: datetime | None = None) -> bool:
        """Whether this account can currently accept a new job."""
        now = now or datetime.now(UTC)
        if self.status not in (AccountStatus.ACTIVE, AccountStatus.COOLDOWN):
            return False
        if self.status is AccountStatus.COOLDOWN:
            return self.cooldown_until is not None and now >= self.cooldown_until
        return True


class TaskRequest(BaseModel):
    """Provider-agnostic request for one task.

    Provider-specific options (Flow's `model`/`aspect_ratio`/`reuse_latest_project`,
    Perplexity's `focus`/`search_mode`, ...) travel opaquely in `params` and are validated
    against the provider's params model — they are never core columns or core fields.
    """

    provider: str
    kind: TaskKind
    prompt: str
    inputs: list[Path] = Field(default_factory=list)
    count: int = Field(default=1, ge=1)
    timeout: float = 180.0
    params: dict[str, Any] = Field(default_factory=dict)
    workspace_ref: WorkspaceRef | None = None

    @field_validator("prompt")
    @classmethod
    def _non_empty_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty")
        return value


class Artifact(BaseModel):
    """A single generated output (image/video/file stored on disk, or inline text).

    `rel_path` is relative to `paths.outputs_dir` in the final design; during the interim
    (Phases 3–5) the Flow runner still stores the absolute download path here until the
    adapter seam lands.
    """

    kind: TaskKind
    mime: str
    rel_path: Path | None = None
    text: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Outcome of a provider task."""

    request: TaskRequest
    account_email: str
    artifacts: list[Artifact] = Field(default_factory=list)
    duration_seconds: float = 0.0
    workspace_ref: WorkspaceRef | None = None
    provider_state: dict[str, Any] = Field(default_factory=dict)
