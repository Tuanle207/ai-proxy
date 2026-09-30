"""Public transport-neutral API for browser-backed AI providers."""

from ai_web_provider.core.config import BrowserSettings, Settings
from ai_web_provider.core.models import Artifact, TaskKind, TaskRequest, TaskResult
from ai_web_provider.runtime.container import ProviderRuntimeContainer
from ai_web_provider.runtime.executor import ProviderExecutor

__all__ = [
    "Artifact",
    "BrowserSettings",
    "ProviderExecutor",
    "ProviderRuntimeContainer",
    "Settings",
    "TaskKind",
    "TaskRequest",
    "TaskResult",
]
