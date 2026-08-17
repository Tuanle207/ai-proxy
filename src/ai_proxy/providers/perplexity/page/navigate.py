"""Navigate to Perplexity and (optionally) resume an existing thread.

Perplexity creates a thread implicitly on the first submitted query (landing on a `/search/<uuid>`
URL); there is no explicit "new thread" control to click, so `open_thread` is just
`open_perplexity` + an optional `goto` of a previously recorded thread URL.
"""

from __future__ import annotations

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel


async def open_perplexity(page: Page) -> None:
    await page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
    await human_delay()


def resolve_thread_ref(ref: str) -> str:
    """Normalize a bare thread id into a full `/search/<uuid>` URL; pass full URLs through."""
    if sel.SEARCH_URL_MARKER in ref:
        return ref
    return f"{sel.PERPLEXITY_URL}{sel.SEARCH_URL_MARKER}{ref}"


async def open_thread(page: Page, ref: str | None) -> None:
    """Resume an existing thread by id/URL, or start fresh on the home page when `ref` is None."""
    if ref:
        target = resolve_thread_ref(ref)
        await page.goto(target, wait_until="domcontentloaded")
        try:
            # Let the thread's prior message history finish loading before we return; otherwise
            # the caller's answer-count baseline can be taken mid-hydration (see page/wait.py).
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeoutError:
            pass
        if sel.SEARCH_URL_MARKER not in page.url:
            # Observed live: the site can silently redirect a direct deep-link to `/` instead of
            # erroring (rate-limit/anti-automation?). Fail loudly rather than silently continuing
            # on the home page, which would submit into a brand-new thread instead of resuming.
            raise PerplexityError(
                f"navigating to thread {target!r} did not land there (ended up at {page.url!r})"
            )
        await human_delay()
    else:
        await open_perplexity(page)
