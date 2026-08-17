"""Google Flow `ProviderAdapter`: the Flow page-driving body lifted from `GenerationRunner`.

Core owns the account slot, browser context, timing and persistence; this adapter drives the
Flow page sequence (open flow → project → prompt → wait → collect → download → overlay) and
returns artifacts. Flow options travel in `GoogleFlowParams`; Flow settings in `GoogleFlowSettings`.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import cast

from ai_proxy.core.models import Artifact, TaskRequest, TaskResult, WorkspaceRef
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.core.worker.failure import FailurePolicy
from ai_proxy.core.worker.metadata import extract_image_metadata
from ai_proxy.providers.google_flow.config import GoogleFlowSettings
from ai_proxy.providers.google_flow.page import download, navigate, prompt, wait
from ai_proxy.providers.google_flow.page.selectors import LOGIN_REDIRECT_HOST
from ai_proxy.providers.google_flow.params import GoogleFlowParams
from ai_proxy.providers.google_flow.postprocess import logo_overlay

# Flow's settings panel was only ever observed offering "x1".."x4" (see page/selectors.py).
_MAX_UI_SUPPORTED_COUNT = 4


class GoogleFlowAdapter:
    """Site-driving body for Flow, behind the `ProviderAdapter` protocol."""

    def __init__(self, deps: ProviderRuntimeDeps):
        self._deps = deps

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

        await navigate.open_flow(page)
        baseline_urls: frozenset[str]
        if params.reuse_latest_project:
            await navigate.ensure_project(page, reuse_latest=True)
            baseline_urls = await download.collect_existing_image_urls(page)
        else:
            workspace_ref = await navigate.create_project(page)
            await session.on_workspace_created(workspace_ref)
            baseline_urls = frozenset()
        await navigate.switch_to_image_mode(page)
        await prompt.submit_prompt(page, request.prompt, request.inputs)
        await wait.wait_for_completion(
            page,
            timeout=request.timeout,
            baseline_count=len(baseline_urls),
            target_count=len(baseline_urls) + effective_count,
        )
        urls = await download.collect_image_urls(page, effective_count, exclude=baseline_urls)
        artifacts = await download.download_images(
            page, urls, session.output_dir, timestamp=run_started_at
        )
        await self._finalize_metadata(artifacts, session)
        if params.overlay_logo:
            await self._apply_logo_overlay(artifacts, session)

        return TaskResult(
            request=request,
            account_email=session.account.email,
            artifacts=artifacts,
            duration_seconds=time.monotonic() - start,
            workspace_ref=workspace_ref,
        )

    def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
        # Delegate to the core default table; Flow adds no site-specific mapping yet.
        return None

    async def health_check(self, session: ProviderSession) -> bool:
        if session.page is not None:
            await navigate.open_flow(session.page)
            return LOGIN_REDIRECT_HOST not in session.page.url
        async with self._deps.backend.browser_context(session.account, headless=True) as context:
            page = await context.new_page()
            try:
                await navigate.open_flow(page)
                return LOGIN_REDIRECT_HOST not in page.url
            finally:
                await page.close()

    async def cleanup(self, session: ProviderSession, ref: WorkspaceRef | None) -> None:
        if not self._settings.delete_project_after_job or ref is None or session.page is None:
            return
        try:
            await navigate.delete_project(session.page, ref)
        except Exception:
            pass  # best-effort; a failed cleanup must never fail an otherwise-successful job

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

    async def _apply_logo_overlay(
        self, artifacts: list[Artifact], session: ProviderSession
    ) -> None:
        logo_setting = self._settings.logo_path
        logo_path = Path(logo_setting) if logo_setting else session.paths.assets_dir / "logo.png"
        if not logo_path.is_file():
            return
        for artifact in artifacts:
            if artifact.rel_path is None:
                continue
            image_path = session.paths.outputs_dir / artifact.rel_path
            try:
                await asyncio.to_thread(logo_overlay.overlay_logo_in_place, image_path, logo_path)
            except logo_overlay.LogoOverlayError:
                # Cosmetic step; never fail an otherwise-successful generation.
                continue
