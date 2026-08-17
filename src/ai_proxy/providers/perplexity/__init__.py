"""Perplexity provider: page automation, auth, and self-registration.

Importing this module builds and `register()`s the `ProviderSpec` so `registry.discover()`
(and the built-in eager import in `providers/__init__.py`) surface it by name `"perplexity"`.
"""

from __future__ import annotations

from ai_proxy.core.models import TaskKind
from ai_proxy.core.provider.registry import register
from ai_proxy.core.provider.spec import Capabilities, ProviderSpec
from ai_proxy.providers.perplexity.adapter import PerplexityAdapter
from ai_proxy.providers.perplexity.api import router
from ai_proxy.providers.perplexity.auth import PerplexityAuth
from ai_proxy.providers.perplexity.cli import perplexity_app
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
        api_router=router,
        cli_app=perplexity_app,
    )
)
