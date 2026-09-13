"""Perplexity provider: page automation, auth, and self-registration."""

from __future__ import annotations

from ai_proxy.core.models import TaskKind
from ai_proxy.core.provider.registry import register
from ai_proxy.core.provider.spec import Capabilities, ProviderSpec
from ai_proxy.providers.perplexity.adapter import PerplexityAdapter
from ai_proxy.providers.perplexity.auth import PerplexityAuth
from ai_proxy.providers.perplexity.config import PerplexitySettings
from ai_proxy.providers.perplexity.params import PerplexityParams

register(
    ProviderSpec(
        name="perplexity",
        display_name="Perplexity",
        capabilities=Capabilities(
            task_kinds=frozenset({TaskKind.TEXT}),
            max_outputs_per_request=1,
            supports_reference_inputs=False,
            supports_workspace_reuse=True,
            requires_browser=True,
        ),
        params_model=PerplexityParams,
        settings_model=PerplexitySettings,
        build_adapter=PerplexityAdapter,
        build_auth=PerplexityAuth,
    )
)
