"""Type the prompt (humanized), optionally attach reference images, and submit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import Page

from ai_web_provider.core.browser.humanize import human_delay
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.providers.google_flow.page import selectors as sel

if TYPE_CHECKING:
    from ai_web_provider.providers.google_flow.reference_cache import ReferenceCache

_log = get_logger()

async def attach_reference_images(
    page: Page,
    reference_images: list[Path],
    cache: ReferenceCache | None = None,
    account_email: str | None = None,
    workspace_ref: str | None = None,
) -> None:
    if not reference_images:
        return
    to_upload: list[Path] = []
    for img_path in reference_images:
        if cache is not None and account_email is not None and workspace_ref is not None:
            sha = cache.compute_sha256(img_path)
            if cache.is_uploaded(sha, account_email, workspace_ref):
                continue
            to_upload.append(img_path)
        else:
            to_upload.append(img_path)
    if not to_upload:
        return
    async with page.expect_file_chooser() as chooser_info:
        await page.locator(sel.REFERENCE_UPLOAD_INPUT).click()
    chooser = await chooser_info.value
    await chooser.set_files([str(p) for p in to_upload])
    await human_delay()
    if cache is not None and account_email is not None and workspace_ref is not None:
        for img_path in to_upload:
            sha = cache.compute_sha256(img_path)
            cache.mark_uploaded(sha, account_email, workspace_ref)


async def submit_prompt(
    page: Page,
    prompt: str,
    reference_images: list[Path] | None = None,
    cache: ReferenceCache | None = None,
    account_email: str | None = None,
    workspace_ref: str | None = None,
) -> None:
    try:
        await attach_reference_images(
            page, reference_images or [], cache, account_email, workspace_ref
        )
        await page.locator(sel.PROMPT_TEXTBOX).wait_for(state="visible", timeout=5000)
        await page.locator(sel.PROMPT_TEXTBOX).first.fill(prompt, force=True)
        await page.locator(sel.SUBMIT_BUTTON).last.click(force=True)
        _log.info(
            "google_flow_submit_prompt_succeeded",
            workspace_ref=workspace_ref,
            prompt_chars=len(prompt),
            reference_image_count=len(reference_images or []),
            page_url=page.url,
        )
    except Exception:
        _log.exception(
            "google_flow_submit_prompt_failed",
            workspace_ref=workspace_ref,
            prompt_chars=len(prompt),
            reference_image_count=len(reference_images or []),
            page_url=page.url,
        )
        raise
