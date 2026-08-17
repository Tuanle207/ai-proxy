"""Extract the answer markdown and the current thread reference."""

from __future__ import annotations

import asyncio
import re
import time

from playwright.async_api import Page

from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel

# Swaps in a stub for `navigator.clipboard.writeText` *before* clicking Copy, so the payload is
# captured in-page: no OS clipboard permissions (Camoufox/Firefox cannot grant `clipboard-read`
# in headless) and no race reading the real clipboard afterward.
_HOOK_COPY_JS = """() => {
  window.__pplx_copy = null;
  navigator.clipboard.writeText = (text) => {
    window.__pplx_copy = text;
    return Promise.resolve();
  };
}"""

_READ_COPY_JS = "() => window.__pplx_copy"
_CLEAR_COPY_JS = "() => { window.__pplx_copy = null; }"

_COPY_WAIT_SECONDS = 3.0
_COPY_POLL_SECONDS = 0.1

# Citation markers in the copied markdown: Perplexity serializes each chip as a numbered link
# (sometimes bare). UNVERIFIED against a live capture (2026-08-17) — adjust these once a real
# copied sample exists (`scripts/_dump_citations.py`).
_CITATION_LINK = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]\((?:https?://|/)[^)\s]*\)")
_BARE_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def strip_citations(markdown: str) -> str:
    """Remove citation markers from copied answer markdown, preserving indentation."""
    text = _CITATION_LINK.sub("", markdown)
    text = _BARE_CITATION.sub("", text)
    text = re.sub(r"(?<=\S) {2,}", " ", text)  # collapse holes left by removals
    text = re.sub(r" +([,.;:!?])", r"\1", text)  # unstick punctuation
    return text.strip()


async def extract_answer(page: Page) -> str:
    """Return the latest answer's markdown via its Copy button, citations stripped.

    An earlier innerText read lost markdown structure, and a P8 copy attempt failed on
    actionability (hover-to-reveal buttons made `.click()` hang). This retry avoids both:
    `dispatch_event` skips Playwright's visibility checks, and the `writeText` hook captures
    the payload without touching the OS clipboard. `.last` picks the most recent message's
    copy control (see `COPY_BUTTON` in selectors.py).
    """
    button = page.locator(sel.COPY_BUTTON).last
    if await button.count() == 0:
        raise PerplexityError("copy button not found (selector churn? see page/selectors.py)")
    await page.evaluate(_HOOK_COPY_JS)
    await button.dispatch_event("click")
    deadline = time.monotonic() + _COPY_WAIT_SECONDS
    while time.monotonic() < deadline:
        text = await page.evaluate(_READ_COPY_JS)
        if text:
            await page.evaluate(_CLEAR_COPY_JS)
            return strip_citations(str(text))
        await asyncio.sleep(_COPY_POLL_SECONDS)
    raise PerplexityError(f"copy button produced no text within {_COPY_WAIT_SECONDS}s")


async def extract_thread_ref(page: Page) -> str | None:
    """Return the current `/search/<uuid>` URL as an opaque workspace ref, if we're on one."""
    url = page.url
    if sel.SEARCH_URL_MARKER in url:
        return url
    return None
