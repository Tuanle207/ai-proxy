"""Google Flow provider settings (AI_PROXY_GOOGLE_FLOW_*), resolved from env + YAML."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from ai_proxy.core.config import ProviderSettings


class GoogleFlowSettings(ProviderSettings):
    """Flow-specific keys that left core config in Phase 3.6."""

    model_config = SettingsConfigDict(env_prefix="AI_PROXY_GOOGLE_FLOW_", extra="ignore")

    logo_path: str | None = None
    delete_project_after_job: bool = False
    quota_cooldown_minutes: int = 120
    overlay_logo: bool = True
