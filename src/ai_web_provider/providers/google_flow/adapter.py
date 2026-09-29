"""Google Flow `ProviderAdapter`: the Flow page-driving body lifted from `GenerationRunner`.

Core owns the account slot, browser context, timing and persistence; this adapter drives the
Flow page sequence (open flow → project → prompt → wait → collect → download → overlay) and
returns artifacts. Flow options travel in `GoogleFlowParams`; Flow settings in `GoogleFlowSettings`.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import cast

from ai_web_provider.core.diagnostics import mark_step
from ai_web_provider.core.errors import QuotaExceededError
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.core.models import Artifact, TaskRequest, TaskResult, WorkspaceRef
from ai_web_provider.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_web_provider.core.failure import FailurePolicy
from ai_web_provider.core.metadata import extract_image_metadata
from ai_web_provider.providers.google_flow.config import GoogleFlowSettings
from ai_web_provider.providers.google_flow.page import download, navigate, prompt, wait
from ai_web_provider.providers.google_flow.page import params as page_params
from ai_web_provider.providers.google_flow.page.selectors import LOGIN_REDIRECT_HOST
from ai_web_provider.providers.google_flow.params import GoogleFlowParams
from ai_web_provider.providers.google_flow.project_pool import GoogleFlowProjectPool, ProjectLease
from ai_web_provider.providers.google_flow.reference_cache import ReferenceCache

_log = get_logger()

# Flow's settings panel was only ever observed offering "x1".."x4" (see page/selectors.py).
_MAX_UI_SUPPORTED_COUNT = 4


class GoogleFlowAdapter:
    """Site-driving body for Flow, behind the `ProviderAdapter` protocol."""

    def __init__(self, deps: ProviderRuntimeDeps):
        self._deps = deps
        self._cache = ReferenceCache(
            deps.paths.provider_dir("google_flow") / "reference_cache.json"
        )
        self._projects = GoogleFlowProjectPool(self._settings.projects_by_account)

    @property
    def _settings(self) -> GoogleFlowSettings:
        # `settings_model` is GoogleFlowSettings, so core always injects the typed subclass.
        return cast(GoogleFlowSettings, self._deps.settings)

    async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult:
        params = GoogleFlowParams.model_validate(request.params)
        effective_count = min(request.count, _MAX_UI_SUPPORTED_COUNT)
        page = session.page
        if page is None:
            raise RuntimeError("google_flow requires a browser page (ProviderSession.page is None)")

        start = time.monotonic()
        run_started_at = datetime.now().strftime("%y%m%d%H%M%S")
        workspace_ref: WorkspaceRef | None = None
        existing_image_urls: frozenset[str] = frozenset()
        lease: ProjectLease | None = None

        _log.info(
            "google_flow_execute_start",
            prompt_chars=len(request.prompt),
            account_email=session.account.email,
        )
        try:
            step = mark_step("open_flow")
            lease = await self._projects.acquire(session.account.email)
            workspace_ref = lease.project_id
            step = mark_step("open_project", workspace_ref=workspace_ref)
            await navigate.open_project(page, workspace_ref)
            step = mark_step("collect_existing_image_urls")
            existing_image_urls = await download.collect_existing_image_urls(page)
            step = mark_step("switch_to_image_mode")
            await navigate.switch_to_image_mode(page)
            step = mark_step("configure_generation")
            await page_params.configure_generation(
                page,
                model=params.model,
                aspect_ratio=params.aspect_ratio,
                count=effective_count,
            )
            step = mark_step("submit_prompt")
            await prompt.submit_prompt(
                page, request.prompt, request.inputs,
                cache=self._cache,
                account_email=session.account.email,
                workspace_ref=workspace_ref,
            )
            step = mark_step("wait_for_completion")
            await wait.wait_for_completion(page, timeout=request.timeout)
            step = mark_step("collect_image_urls")
            urls = await download.collect_image_urls(page, effective_count, exclude=existing_image_urls)
            step = mark_step("download_images")
            artifacts = await download.download_images(
                page, urls, session.output_dir, timestamp=run_started_at
            )
            step = mark_step("finalize_metadata")
            await self._finalize_metadata(artifacts, session)
        except QuotaExceededError as error:
            error.model = params.model
            _log.exception(
                "google_flow_step_failed",
                step=step,
                workspace_ref=workspace_ref,
                model=params.model,
                aspect_ratio=params.aspect_ratio,
                count=effective_count,
                page_url=page.url,
            )
            raise
        except Exception:
            _log.exception(
                "google_flow_step_failed",
                step=step,
                workspace_ref=workspace_ref,
                count=effective_count,
                page_url=page.url,
            )
            raise
        finally:
            if lease is not None:
                await lease.release()

        duration = time.monotonic() - start
        _log.info(
            "google_flow_execute_done",
            workspace_ref=workspace_ref,
            artifact_count=len(artifacts),
            duration_seconds=round(duration, 2),
        )
        return TaskResult(
            request=request,
            account_email=session.account.email,
            artifacts=artifacts,
            duration_seconds=duration,
            workspace_ref=workspace_ref,
        )

    def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
        # Delegate to the core default table; Flow adds no site-specific mapping yet.
        return None

    async def health_check(self, session: ProviderSession) -> bool:
        if session.page is not None:
            await navigate.open_flow(session.page)
            return LOGIN_REDIRECT_HOST not in session.page.url
        async with self._deps.backend.browser_context(session.account) as context:
            page = await context.new_page()
            try:
                await navigate.open_flow(page)
                return LOGIN_REDIRECT_HOST not in page.url
            finally:
                await page.close()

    async def cleanup(self, session: ProviderSession, ref: WorkspaceRef | None) -> None:
        return

    async def _finalize_metadata(
        self, artifacts: list[Artifact], session: ProviderSession
    ) -> None:
        """Sniff true metadata and re-root `rel_path` under `outputs_dir` (Phase 5 seam)."""
        for artifact in artifacts:
            local_path = artifact.rel_path
            if local_path is None:
                continue
            meta = await asyncio.to_thread(extract_image_metadata, local_path)
            artifact.bytes = meta.bytes
            artifact.width = meta.width
            artifact.height = meta.height
            artifact.sha256 = meta.sha256
            artifact.mime = meta.content_type
            artifact.rel_path = local_path.relative_to(session.paths.outputs_dir)

