"""Perplexity request params: Perplexity-specific options that never touch core."""

from __future__ import annotations

from ai_proxy.core.provider.params import ProviderParams


class PerplexityParams(ProviderParams):
    """Per-task options for a Perplexity text answer.

    `focus`/`model`/`search_mode` default to `None` ("use the site default") and are left as
    open strings until reconnaissance (plan P3.1) confirms the real control names and values;
    then they can be tightened to a `Literal`/enum. `extra="forbid"` (inherited) makes an
    unknown or misspelled param fail fast at the CLI/API instead of being silently ignored.
    """

    focus: str | None = None
    model: str | None = None
    search_mode: str | None = None
    include_citations: bool = True
