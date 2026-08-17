"""Wait for the answer to finish streaming and classify failures.

Completion is detected by the streaming "stop" button disappearing *after* an answer body has
appeared — never by a fixed sleep. The exact signal is unverified (plan P3.1); `STOP_BUTTON` and
`ANSWER_BODY` may change.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from ai_proxy.core.errors import AuthError, GenerationTimeoutError, QuotaExceededError
from ai_proxy.providers.perplexity.page import selectors as sel

_POLL_INTERVAL_SECONDS = 0.25


def _classify_error(message: str) -> Exception:
    lowered = message.lower()
    if "rate limit" in lowered or "quota" in lowered or "too many" in lowered:
        return QuotaExceededError(message)
    if "sign in" in lowered or "log in" in lowered or "session" in lowered:
        return AuthError(message)
    return GenerationTimeoutError(message)


async def _answer_ready(page: Page) -> bool:
    answer = page.locator(sel.ANSWER_BODY).last
    if await answer.count() == 0:
        return False
    text = (await answer.inner_text()).strip()
    return bool(text)


async def wait_for_answer(page: Page, *, timeout: float) -> None:
    """Wait until the answer has finished streaming, or raise a classified error.

    Returns once an answer body is present and the stop button (streaming indicator) is gone.
    """
    stop = page.locator(sel.STOP_BUTTON)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await stop.count() == 0 and await _answer_ready(page):
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise GenerationTimeoutError(f"answer did not complete within {timeout}s")
