"""ProviderAdapter protocol: the one method that matters."""

from __future__ import annotations

from typing import Protocol

from ai_proxy.core.models import TaskRequest, TaskResult, WorkspaceRef
from ai_proxy.core.provider.session import ProviderSession
from ai_proxy.core.worker.failure import FailurePolicy


class ProviderAdapter(Protocol):
    """A provider's site-driving body.

    Core owns everything around `execute` (account slot, browser context, timing, persistence,
    events); the adapter is handed a live `ProviderSession` and returns artifacts.
    """

    async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult: ...

    def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
        """Map a provider exception to a policy; return `None` to use the core default."""
        ...

    async def health_check(self, session: ProviderSession) -> bool: ...

    async def cleanup(self, session: ProviderSession, ref: WorkspaceRef | None) -> None: ...
