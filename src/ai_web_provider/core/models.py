"""Domain models for accounts and generation requests/results."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel, Field, field_validator


class TaskKind(enum.StrEnum):
    IMAGE = "image"
    TEXT = "text"
    VIDEO = "video"
    FILE = "file"


WorkspaceRef: TypeAlias = str


class AccountStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    NEEDS_LOGIN = "needs_login"
    COOLDOWN = "cooldown"


class Account(BaseModel):
    email: str
    label: str | None = None
    proxy: str | None = None
    status: AccountStatus = AccountStatus.NEEDS_LOGIN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    success_count: int = 0
    fail_count: int = 0
    cooldown_until: datetime | None = None
    model_cooldowns: dict[str, datetime] = Field(default_factory=dict)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError(f"invalid email address: {value!r}")
        return value

    def is_available(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if self.status not in (AccountStatus.ACTIVE, AccountStatus.COOLDOWN):
            return False
        if self.status is AccountStatus.COOLDOWN:
            return self.cooldown_until is not None and now >= self.cooldown_until
        return True

    def is_model_available(self, model: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        cooldown = self.model_cooldowns.get(model)
        if cooldown is None:
            return True
        if now >= cooldown:
            del self.model_cooldowns[model]
            return True
        return False


class TaskRequest(BaseModel):
    provider: str
    kind: TaskKind
    prompt: str
    inputs: list[Path] = Field(default_factory=list)
    count: int = Field(default=1, ge=1)
    timeout: float = 180.0
    params: dict[str, Any] = Field(default_factory=dict)
    workspace_ref: str | None = None

    @field_validator("prompt")
    @classmethod
    def _non_empty_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty")
        return value


class Artifact(BaseModel):
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
    request: TaskRequest
    account_email: str
    artifacts: list[Artifact] = Field(default_factory=list)
    duration_seconds: float = 0.0
    workspace_ref: str | None = None
    provider_state: dict[str, Any] = Field(default_factory=dict)
