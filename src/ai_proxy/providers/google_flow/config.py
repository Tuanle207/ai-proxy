"""Google Flow provider settings (AI_PROXY_GOOGLE_FLOW_*), resolved from env + YAML."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from ai_proxy.core.config import ProviderSettings


class GoogleFlowSettings(ProviderSettings):
    """Flow-specific keys that left core config in Phase 3.6."""

    model_config = SettingsConfigDict(env_prefix="AI_PROXY_GOOGLE_FLOW_", extra="ignore")

    logo_path: str | None = None
    quota_cooldown_minutes: int = 120
    overlay_logo: bool = True
    model_fallback_order: list[str] = ["Nano Banana 2", "Nano Banana Pro", "Nano Banana 2 Lite"]
    # Flow accounts are Google sessions: two concurrent browsers on the same account can
    # invalidate each other's cookies (and, with `reuse_default_project`, race on one project),
    # so same-account concurrency is serialized by default. Override via env if desired.
    per_account_concurrency: int | None = 4
    # When > 1, up to this many concurrent jobs on one account share a single browser as
    # separate tabs (one cookie jar, no cross-browser session conflict). Requires jobs to set
    # `reuse_default_project=false` so each tab works in its own project.
    max_tabs_per_session: int = 4
