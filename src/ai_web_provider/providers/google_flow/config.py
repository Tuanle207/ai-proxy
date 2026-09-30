"""Google Flow provider settings supplied by the embedding application."""

from __future__ import annotations

from ai_web_provider.core.config import ProviderSettings


class GoogleFlowSettings(ProviderSettings):
    """Flow-specific keys that left core config in Phase 3.6."""

    logo_path: str | None = None
    quota_cooldown_minutes: int = 120
    overlay_logo: bool = True
    model_fallback_order: list[str] = ["Nano Banana 2", "Nano Banana Pro", "Nano Banana 2 Lite"]
    projects_by_account: dict[str, list[str]] = {}
