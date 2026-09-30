"""Application settings supplied explicitly by the embedding application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_web_provider.core.paths import DataPaths


class BrowserSettings(BaseModel):
    """Ungoogled Chromium runtime options owned by the embedding application."""

    ungoogled_chromium_executable: Path = Path("ungoogled-chromium")
    viewport_width: int = 1280
    viewport_height: int = 720
    startup_timeout_seconds: float = 15.0
    shutdown_timeout_seconds: float = 10.0
    login_timeout_seconds: float = 300.0
    idle_timeout_seconds: float = 600.0
    process_environment: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: str = "data"
    per_account_concurrency: int = 2
    max_retries: int = 3
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)

    max_concurrent_jobs: int = 4
    cooldown_minutes: int = 5
    quota_cooldown_minutes: int = 120
    # Failure captures are always written on failed attempts; these only bound disk usage.
    failure_retention_days: int = 7
    failure_retention_max_mb: int = 500

    @property
    def paths(self) -> DataPaths:
        return DataPaths(self.data_dir)

    def provider_settings(self, provider: str) -> dict[str, Any]:
        return self.providers.get(provider, {})


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
