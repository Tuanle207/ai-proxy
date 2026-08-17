"""Navigate to Perplexity and (optionally) resume an existing thread.

Perplexity creates a thread implicitly on the first submitted query (landing on a `/search/<uuid>`
URL); there is no explicit "new thread" control to click, so `open_thread` is just
`open_perplexity` + an optional `goto` of a previously recorded thread URL.
"""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.providers.perplexity.page import selectors as sel


async def open_perplexity(page: Page) -> None:
    await page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
    await human_delay()


async def open_thread(page: Page, ref: str | None) -> None:
    """Resume an existing thread by URL, or start fresh on the home page when `ref` is None."""
    if ref:
        await page.goto(ref, wait_until="domcontentloaded")
        await human_delay()
    else:
        await open_perplexity(page)
