"""Extract the answer markdown, citations, and the current thread reference."""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel


async def extract_answer(page: Page) -> tuple[str, list[dict[str, str]]]:
    """Return the answer text and its citations (title/url).

    The answer body selector is unverified (plan P3.1); citation extraction is best-effort.
    """
    answer = page.locator(sel.ANSWER_BODY).last
    if await answer.count() == 0:
        raise PerplexityError("answer body not found (selector churn? see page/selectors.py)")
    text = (await answer.inner_text()).strip()
    citations = await _extract_citations(page)
    return text, citations


async def _extract_citations(page: Page) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    links = page.locator(sel.CITATION_LINK)
    for index in range(await links.count()):
        link = links.nth(index)
        href = await link.get_attribute("href") or ""
        if not href.startswith("http"):
            continue
        title = (await link.inner_text()).strip()
        citations.append({"url": href, "title": title})
    return citations


async def extract_thread_ref(page: Page) -> str | None:
    """Return the current `/search/<uuid>` URL as an opaque workspace ref, if we're on one."""
    url = page.url
    if sel.SEARCH_URL_MARKER in url:
        return url
    return None
