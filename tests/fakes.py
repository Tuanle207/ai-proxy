"""Fake provider fixture: exercises the provider seam without a real destination.

Used by every later phase to test multi-provider machinery before a second real provider exists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import BrowserContext

from ai_proxy.core.config import ProviderSettings
from ai_proxy.core.models import Account, Artifact, TaskKind, TaskRequest, TaskResult, WorkspaceRef
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.provider.params import ProviderParams
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.core.provider.spec import Capabilities, ProviderSpec
from ai_proxy.core.service.storage import StoredObject
from ai_proxy.core.worker.failure import FailurePolicy


class FakeParams(ProviderParams):
    mode: str = "fast"
    count_hint: int = 1


class FakeSettings(ProviderSettings):
    pass


class FakeAdapter:
    def __init__(self, deps: ProviderRuntimeDeps):
        self.deps = deps

    async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult:
        text = f"fake:{request.kind.value}:{request.prompt}"
        return TaskResult(
            request=request,
            account_email=session.account.email,
            artifacts=[Artifact(kind=request.kind, mime="text/plain", text=text, bytes=len(text))],
        )

    def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
        return None

    async def health_check(self, session: ProviderSession) -> bool:
        return True

    async def cleanup(self, session: ProviderSession, ref: WorkspaceRef | None) -> None:
        return None


class FakeAuth:
    def __init__(self, deps: ProviderRuntimeDeps):
        self.deps = deps

    @property
    def login_url(self) -> str:
        return "https://fake.example/login"

    async def is_logged_in(self, session: ProviderSession) -> bool:
        return True

    async def interactive_login(self, session: ProviderSession) -> bool:
        return True

    async def probe_session(self, session: ProviderSession) -> bool:
        return True


class NullBackend:
    @asynccontextmanager
    async def browser_context(
        self, account: Account, *, headless: bool = True
    ) -> AsyncIterator[BrowserContext]:
        raise NotImplementedError("NullBackend is not a real browser")


@dataclass(frozen=True)
class NullStorage:
    @property
    def name(self) -> str:
        return "null"

    async def save(self, data: bytes, key: str) -> StoredObject:
        return StoredObject(key=key, bytes=len(data), content_type="application/octet-stream")

    def resolve(self, key: str) -> Path:
        return Path(key)

    def public_url(self, key: str) -> str | None:
        return None


def make_spec(
    *,
    name: str = "fake",
    task_kinds: frozenset[TaskKind] = frozenset({TaskKind.TEXT}),
    max_outputs_per_request: int = 1,
) -> ProviderSpec:
    return ProviderSpec(
        name=name,
        display_name="Fake Provider",
        capabilities=Capabilities(
            task_kinds=task_kinds,
            max_outputs_per_request=max_outputs_per_request,
            supports_reference_inputs=False,
            supports_workspace_reuse=False,
            requires_browser=False,
        ),
        params_model=FakeParams,
        settings_model=FakeSettings,
        build_adapter=FakeAdapter,
        build_auth=FakeAuth,
    )


def make_deps(paths: DataPaths) -> ProviderRuntimeDeps:
    return ProviderRuntimeDeps(
        settings=FakeSettings(),
        paths=paths,
        backend=NullBackend(),  # type: ignore[arg-type]
        storage=NullStorage(),  # type: ignore[arg-type]
        logger=structlog.get_logger(),
    )


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def make_session(
    paths: DataPaths,
    *,
    email: str = "fake@example.com",
    deps: ProviderRuntimeDeps | None = None,
) -> ProviderSession:
    deps = deps or make_deps(paths)
    return ProviderSession(
        account=Account(email=email),
        page=None,
        http=None,
        paths=paths,
        output_dir=paths.outputs_dir,
        settings=deps.settings,
        emit=_noop,
        on_workspace_created=_noop,
    )
