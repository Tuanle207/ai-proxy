"""Perplexity provider settings (AI_PROXY_PERPLEXITY_*), resolved from env + YAML."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from ai_proxy.core.config import ProviderSettings


class PerplexitySettings(ProviderSettings):
    """Perplexity-specific keys that never touch core config."""

    model_config = SettingsConfigDict(env_prefix="AI_PROXY_PERPLEXITY_", extra="ignore")

    base_url: str = "https://www.perplexity.ai"
    login_timeout: float = 300.0
    delete_thread_after_job: bool = False
