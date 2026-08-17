"""Perplexity `ProviderAdapter` — the site-driving body.

The page sequence mirrors `GoogleFlowAdapter`:
`open_thread → submit → wait_for_answer → extract_answer → TaskResult(TEXT artifact)`. `focus`/
`model`/`search_mode` are validated but not yet applied — they need recon of the corresponding
controls before the adapter can set them.
"""

from __future__ import annotations

import time
from typing import cast

from ai_proxy.core.models import Artifact, TaskKind, TaskRequest, TaskResult, WorkspaceRef
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.core.worker.failure import AccountEffect, FailurePolicy
from ai_proxy.providers.perplexity.auth import probe_logged_in
from ai_proxy.providers.perplexity.config import PerplexitySettings
from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import extract, navigate, prompt, wait
from ai_proxy.providers.perplexity.params import PerplexityParams


class PerplexityAdapter:
    """Site-driving body for Perplexity, behind the `ProviderAdapter` protocol."""

    def __init__(self, deps: ProviderRuntimeDeps):
        self._deps = deps

    @property
    def _settings(self) -> PerplexitySettings:
        return cast(PerplexitySettings, self._deps.settings)

    async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult:
        PerplexityParams.model_validate(request.params)
        page = session.page
        if page is None:
            raise RuntimeError("perplexity requires a browser page (ProviderSession.page is None)")

        start = time.monotonic()
        await navigate.open_thread(page, request.workspace_ref)
        baseline_count = await wait.count_answers(page)
        await prompt.submit_prompt(page, request.prompt)
        await wait.wait_for_answer(page, timeout=request.timeout, baseline_count=baseline_count)
        answer = await extract.extract_answer(page)
        workspace_ref = await extract.extract_thread_ref(page)
        if workspace_ref is not None:
            await session.on_workspace_created(workspace_ref)

        artifact = Artifact(
            kind=TaskKind.TEXT,
            mime="text/markdown",
            text=answer,
            bytes=len(answer.encode("utf-8")),
        )
        return TaskResult(
            request=request,
            account_email=session.account.email,
            artifacts=[artifact],
            duration_seconds=time.monotonic() - start,
            workspace_ref=workspace_ref,
        )

    def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
        if isinstance(exc, PerplexityError):
            return FailurePolicy(False, "perplexity_automation_error", AccountEffect.NONE)
        return None  # delegate to the core default table

    async def health_check(self, session: ProviderSession) -> bool:
        if session.page is not None:
            await navigate.open_perplexity(session.page)
            return await probe_logged_in(session.page)
        async with self._deps.backend.browser_context(session.account, headless=True) as context:
            page = await context.new_page()
            try:
                await navigate.open_perplexity(page)
                return await probe_logged_in(page)
            finally:
                await page.close()

    async def cleanup(self, session: ProviderSession, ref: WorkspaceRef | None) -> None:
        if not self._settings.delete_thread_after_job or ref is None:
            return
        # TODO(P6.4): delete the thread once the delete control is recon'd (plan P3.1).
        return None
