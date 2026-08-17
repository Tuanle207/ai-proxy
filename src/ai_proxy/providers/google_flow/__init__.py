"""Google Flow provider: page automation, auth, Flow-specific persistence, and self-registration.

Importing this module builds and `register()`s the `ProviderSpec` so `registry.discover()`
(and the built-in eager import in `providers/__init__.py`) surface it by name `"google_flow"`.
"""

from __future__ import annotations

from ai_proxy.core.models import TaskKind
from ai_proxy.core.provider.registry import register
from ai_proxy.core.provider.spec import Capabilities, ProviderSpec
from ai_proxy.providers.google_flow.adapter import GoogleFlowAdapter
from ai_proxy.providers.google_flow.api import router
from ai_proxy.providers.google_flow.auth import GoogleFlowAuth
from ai_proxy.providers.google_flow.cli import google_flow_app
from ai_proxy.providers.google_flow.config import GoogleFlowSettings
from ai_proxy.providers.google_flow.db.schema import GOOGLE_FLOW_MIGRATIONS, archive_orphan_project
from ai_proxy.providers.google_flow.params import GoogleFlowParams

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
        migrations=GOOGLE_FLOW_MIGRATIONS,
        api_router=router,
        cli_app=google_flow_app,
        on_orphan=archive_orphan_project,
    )
)
