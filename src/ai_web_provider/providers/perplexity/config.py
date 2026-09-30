"""Perplexity provider settings supplied by the embedding application."""

from __future__ import annotations

from ai_web_provider.core.config import ProviderSettings


class PerplexitySettings(ProviderSettings):
    """Perplexity-specific keys that never touch core config."""

    base_url: str = "https://www.perplexity.ai"
    login_timeout: float = 300.0
    delete_thread_after_job: bool = False
