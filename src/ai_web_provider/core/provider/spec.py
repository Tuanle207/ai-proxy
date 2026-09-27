"""ProviderSpec and Capabilities: declarative provider description."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_web_provider.core.config import ProviderSettings
from ai_web_provider.core.models import TaskKind
from ai_web_provider.core.provider.adapter import ProviderAdapter
from ai_web_provider.core.provider.auth import AuthHandler
from ai_web_provider.core.provider.params import ProviderParams
from ai_web_provider.core.provider.session import ProviderRuntimeDeps


@dataclass(frozen=True)
class Capabilities:
    """What a provider can do — the API/CLI discovery surface."""

    task_kinds: frozenset[TaskKind]
    max_outputs_per_request: int
    supports_reference_inputs: bool
    supports_workspace_reuse: bool
    requires_browser: bool


@dataclass(frozen=True)
class ProviderSpec:
    """Self-description a provider registers so core can resolve it by name."""

    name: str
    display_name: str
    capabilities: Capabilities
    params_model: type[ProviderParams]
    settings_model: type[ProviderSettings]
    build_adapter: Callable[[ProviderRuntimeDeps], ProviderAdapter]
    build_auth: Callable[[ProviderRuntimeDeps], AuthHandler]
