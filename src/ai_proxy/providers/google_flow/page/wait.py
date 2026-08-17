"""Wait for generation to finish and classify failures.

Selectors used here are unverified placeholders — see `flowpage/selectors.py`.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from ai_proxy.core.errors import AuthError, GenerationTimeoutError, QuotaExceededError
from ai_proxy.providers.google_flow.page import selectors as sel

_POLL_INTERVAL_SECONDS = 0.25


def _classify_error(message: str) -> Exception:
    lowered = message.lower()
    if "quota" in lowered or "credit" in lowered:
        return QuotaExceededError(message)
    if "sign in" in lowered or "log in" in lowered or "session" in lowered:
        return AuthError(message)
    return GenerationTimeoutError(message)


async def wait_for_completion(
    page: Page, *, timeout: float, baseline_count: int = 0, target_count: int = 1
) -> None:
    """Wait until `target_count` generated thumbnails exist, or raise a classified error.

    `baseline_count` is how many thumbnails existed before this generation was submitted (nonzero
    when reusing a non-empty Flow project). If `target_count` isn't reached before `timeout` but
    at least one *new* thumbnail appeared (count > `baseline_count`), this returns normally
    instead of raising, so callers can save whatever finished (best-effort partial success).
    """
    thumbs = page.locator(sel.RESULT_IMAGE_THUMBNAIL)
    deadline = time.monotonic() + timeout
    while True:
        count = await thumbs.count()
        if count >= target_count:
            return
        if time.monotonic() >= deadline:
            if count > baseline_count:
                return
            error_text = None
            try:
                error_text = await page.locator(sel.ERROR_BANNER).first.text_content(timeout=2000)
            except Exception:
                pass
            if error_text:
                raise _classify_error(error_text)
            raise GenerationTimeoutError(f"generation did not complete within {timeout}s")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

