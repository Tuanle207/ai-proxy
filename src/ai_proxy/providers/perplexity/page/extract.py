"""Extract the answer markdown and the current thread reference."""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel


async def extract_answer(page: Page) -> str:
    """Return the latest answer's text (markdown).

    A Copy-button + clipboard-intercept approach was tried (P8 live testing) but proved less
    reliable than this (hover-to-reveal requirement, clicks hanging) — reverted. `.last` picks
    the most recent assistant message.
    """
    answer = page.locator(sel.ANSWER_BODY).last
    if await answer.count() == 0:
        raise PerplexityError("answer body not found (selector churn? see page/selectors.py)")
    return (await answer.inner_text()).strip()



async def extract_thread_ref(page: Page) -> str | None:
    """Return the current `/search/<uuid>` URL as an opaque workspace ref, if we're on one."""
    url = page.url
    if sel.SEARCH_URL_MARKER in url:
        return url
    return None

