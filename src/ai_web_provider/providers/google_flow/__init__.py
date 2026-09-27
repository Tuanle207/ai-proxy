"""Google Flow provider: page automation, auth, and self-registration."""

from __future__ import annotations

from ai_web_provider.core.models import TaskKind
from ai_web_provider.core.provider.registry import register
from ai_web_provider.core.provider.spec import Capabilities, ProviderSpec
from ai_web_provider.providers.google_flow.adapter import GoogleFlowAdapter
from ai_web_provider.providers.google_flow.auth import GoogleFlowAuth
from ai_web_provider.providers.google_flow.config import GoogleFlowSettings
from ai_web_provider.providers.google_flow.params import GoogleFlowParams

register(
    ProviderSpec(
        name="google_flow",
        display_name="Google Flow",
        capabilities=Capabilities(
            task_kinds=frozenset({TaskKind.IMAGE}),
            max_outputs_per_request=4,
            supports_reference_inputs=True,
            supports_workspace_reuse=True,
            requires_browser=True,
        ),
        params_model=GoogleFlowParams,
        settings_model=GoogleFlowSettings,
        build_adapter=GoogleFlowAdapter,
        build_auth=GoogleFlowAuth,
    )
)
