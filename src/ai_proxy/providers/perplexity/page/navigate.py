"""Navigate to Perplexity and (optionally) resume an existing thread.

Perplexity creates a thread implicitly on the first submitted query (landing on a `/search/<uuid>`
URL); there is no explicit "new thread" control to click, so `open_thread` is just
`open_perplexity` + an optional `goto` of a previously recorded thread URL.

A resumed thread's message history is paginated and lazily loaded on scroll (only the newest page
renders initially), which can undercount `wait.count_answers`'s baseline. `open_thread` scrolls the
thread body and tracks the paginated history API until it reports no more pages before returning.
"""

from __future__ import annotations

import time

from playwright.async_api import Page, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel

_log = get_logger()

_THREAD_LOAD_TIMEOUT_SECONDS = 20.0
_PAGE_RESPONSE_TIMEOUT_MS = 5_000

_SCROLL_TO_BOTTOM_JS = """(sel) => {
  const el = document.querySelector(sel);
  if (el) el.scrollTop = el.scrollHeight;
}"""


async def open_perplexity(page: Page) -> None:
    await page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
    await human_delay()


def resolve_thread_ref(ref: str) -> str:
    """Normalize a bare thread id into a full `/search/<uuid>` URL; pass full URLs through."""
    if sel.SEARCH_URL_MARKER in ref:
        return ref
    return f"{sel.PERPLEXITY_URL}{sel.SEARCH_URL_MARKER}{ref}"


def _is_thread_history_response(response: Response) -> bool:
    return sel.THREAD_REST_PATH_MARKER in response.url


async def _has_next_page(response: Response) -> bool:
    try:
        return bool((await response.json()).get("has_next_page", False))
    except Exception:
        # Unexpected/changed response shape — treat as "no more pages" rather than failing the job.
        _log.warning("perplexity_thread_history_bad_response", url=response.url)
        return False


async def _wait_for_thread_history_loaded(page: Page, target: str) -> None:
    """Scroll the thread body until the paginated history API reports no more pages.

    Best-effort: a missing/changed API response or a stalled scroll just stops the loop (the
    caller's answer-count baseline may then undercount) rather than failing the job.
    """
    try:
        async with page.expect_response(
            _is_thread_history_response, timeout=_PAGE_RESPONSE_TIMEOUT_MS
        ) as info:
            await page.goto(target, wait_until="domcontentloaded")
            await page.locator(sel.PROMPT_TEXTBOX).wait_for(state="visible")
        has_more = await _has_next_page(await info.value)
    except PlaywrightTimeoutError:
        _log.error("perplexity_thread_history_no_response", target=target, page_url=page.url)
        return

    deadline = time.monotonic() + _THREAD_LOAD_TIMEOUT_SECONDS
    while has_more and time.monotonic() < deadline:
        try:
            async with page.expect_response(
                _is_thread_history_response, timeout=_PAGE_RESPONSE_TIMEOUT_MS
            ) as info:
                await page.evaluate(_SCROLL_TO_BOTTOM_JS, sel.THREAD_SCROLL_CONTAINER)
            has_more = await _has_next_page(await info.value)
        except PlaywrightTimeoutError:
            _log.error(
                "perplexity_thread_history_scroll_timed_out", target=target, page_url=page.url
            )
            break


async def open_thread(page: Page, ref: str | None) -> None:
    """Resume an existing thread by id/URL, or start fresh on the home page when `ref` is None."""
    if ref:
        target = resolve_thread_ref(ref)
        _log.info("perplexity_open_thread", mode="resume", workspace_ref=ref, target=target)
        await _wait_for_thread_history_loaded(page, target)
        if sel.SEARCH_URL_MARKER not in page.url:
            # Observed live: the site can silently redirect a direct deep-link to `/` instead of
            # erroring (rate-limit/anti-automation?). Fail loudly rather than silently continuing
            # on the home page, which would submit into a brand-new thread instead of resuming.
            _log.warning(
                "perplexity_open_thread_redirect_mismatch", target=target, landed_at=page.url
            )
            raise PerplexityError(
                f"navigating to thread {target!r} did not land there (ended up at {page.url!r})"
            )
        await human_delay()
    else:
        _log.info("perplexity_open_thread", mode="fresh", workspace_ref=None)
        await open_perplexity(page)
