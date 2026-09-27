"""Wait for generation to finish and classify failures.

Selectors used here are unverified placeholders — see `flowpage/selectors.py`.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from ai_web_provider.core.errors import AuthError, GenerationTimeoutError, QuotaExceededError
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.providers.google_flow.page import selectors as sel

_log = get_logger()
_POLL_INTERVAL_SECONDS = 0.25


def _classify_error(message: str) -> Exception:
    lowered = message.lower()
    if "quota" in lowered or "credit" in lowered:
        return QuotaExceededError(message)
    if "sign in" in lowered or "log in" in lowered or "session" in lowered:
        return AuthError(message)
    return GenerationTimeoutError(message)

"""
<flow-stop-icon-button _ngcontent-ng-c2423509130="" _nghost-ng-c1546265201=""><button _ngcontent-ng-c1546265201="" flow-icon-button="" maticonbutton="" type="button" class="mdc-icon-button mat-mdc-icon-button mat-mdc-button-base mat-mdc-tooltip-trigger stop-icon-button stop-button mat-unthemed flow-icon-button-secondary flow-button-small" mat-ripple-loader-class-name="mat-mdc-button-ripple" mat-ripple-loader-centered="" aria-label="Dừng"><span class="mat-mdc-button-persistent-ripple mdc-icon-button__ripple"></span><mat-icon _ngcontent-ng-c1546265201="" role="img" class="mat-icon notranslate flow-icon-s fill google-symbols mat-icon-no-color" aria-hidden="true" data-mat-icon-type="font">stop</mat-icon><!----><span class="mat-focus-indicator"></span><span class="mat-mdc-button-touch-target"></span><span class="mat-ripple mat-mdc-button-ripple"></span></button><!----></flow-stop-icon-button>
"""


async def wait_for_completion(
    page: Page, *, timeout: float
) -> None:
    """Wait for the generation to complete or timeout."""
    _log.info("google_flow_wait_for_completion_started", page_url=page.url)
    current_latest_media_id = await page.locator(sel.RESULT_IMAGE_THUMBNAIL).first.get_attribute("data-media-id")
    stop_button = page.locator("flow-stop-icon-button button:has(mat-icon:has-text('stop'))")
    
    deadline = time.monotonic() + timeout
    while True:
        latest_media_id = await page.locator(sel.RESULT_IMAGE_THUMBNAIL).first.get_attribute("data-media-id")
        stop_button_hidden = await stop_button.is_hidden()
        if stop_button_hidden and latest_media_id != current_latest_media_id:
            _log.info("google_flow_generation_completed")
            return
        
        # Check if the timeout has been reached
        if time.monotonic() >= deadline:
            if stop_button_hidden and latest_media_id != current_latest_media_id:
                _log.info("google_flow_generation_completed")
                return
            error_text = None
            try:
                error_text = await page.locator(sel.ERROR_BANNER).first.text_content(timeout=2000)
            except Exception:
                _log.exception("google_flow_error_banner_read_failed", page_url=page.url)
            if error_text:
                _log.error(
                    "google_flow_generation_error_banner",
                    error_text=error_text,
                    page_url=page.url,
                )
                raise _classify_error(error_text)
            _log.error(
                "google_flow_wait_for_completion_timeout",
                timeout=timeout,
                page_url=page.url,
            )
            raise GenerationTimeoutError(f"generation did not complete within {timeout}s")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

