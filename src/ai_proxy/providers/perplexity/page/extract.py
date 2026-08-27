"""Extract the answer markdown and the current thread reference."""

from __future__ import annotations

import asyncio
import re
import time

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.logging_setup import get_logger
from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import selectors as sel

_log = get_logger()

# Swaps in a stub for `navigator.clipboard.writeText` *before* clicking Copy, so the payload is
# captured in-page: no OS clipboard permissions (Camoufox/Firefox cannot grant `clipboard-read`
# in headless) and no race reading the real clipboard afterward. Uses `Object.defineProperty` to
# replace the whole `navigator.clipboard` object rather than assigning `.writeText` directly,
# since Camoufox's anti-fingerprinting hardening can make the live property non-writable (a plain
# assignment then silently no-ops and the hook never fires).
_HOOK_COPY_JS = """() => {
  window.__pplx_copy = null;
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: (text) => { window.__pplx_copy = text; return Promise.resolve(); } },
    configurable: true,
  });
}"""

_READ_COPY_JS = "() => window.__pplx_copy"
_CLEAR_COPY_JS = "() => { window.__pplx_copy = null; }"

_COPY_WAIT_SECONDS = 6.0
_COPY_POLL_SECONDS = 0.1

_STREAM_STOP_TIMEOUT_SECONDS = 120.0
_STREAM_STOP_POLL_SECONDS = 0.25

_ARTIFACT_PANEL_WAIT_SECONDS = 10.0

# Citation markers in the copied markdown: Perplexity serializes each chip as a numbered link
# (sometimes bare). UNVERIFIED against a live capture (2026-08-17) — adjust these once a real
# copied sample exists (`scripts/_dump_citations.py`).
_CITATION_LINK = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]\((?:https?://|/)[^)\s]*\)")
_BARE_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.DOTALL)


def strip_citations(markdown: str) -> str:
    """Remove citation markers from copied answer markdown, preserving indentation."""
    text = _CITATION_LINK.sub("", markdown)
    text = _BARE_CITATION.sub("", text)
    text = re.sub(r"(?<=\S) {2,}", " ", text)  # collapse holes left by removals
    text = re.sub(r" +([,.;:!?])", r"\1", text)  # unstick punctuation
    return text.strip()


def strip_json_fence(text: str) -> str:
    """Remove a wrapping ```json ... ``` code fence from copied content, if present."""
    match = _JSON_FENCE.match(text)
    return match.group(1).strip() if match else text


async def _wait_stream_stopped(page: Page) -> None:
    """Block until the response has finished streaming (stop control no longer active).

    The Copy button renders for a still-streaming answer too, so relying on it alone can capture
    a truncated response. Gate on the stop control entering its closed/removed state instead.
    """
    stop = page.locator(sel.STOP_BUTTON_ACTIVE)
    deadline = time.monotonic() + _STREAM_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if await stop.count() == 0:
            return
        await asyncio.sleep(_STREAM_STOP_POLL_SECONDS)
    raise PerplexityError(
        f"response still streaming (stop control active) after {_STREAM_STOP_TIMEOUT_SECONDS}s"
    )


def _latest_turn(page: Page) -> Locator:
    """The last request/response turn item, so a content-block lookup under it can't match a
    stale item from an earlier turn (a turn can render more than one content block).
    """
    return page.locator(sel.RESPONSE_LIST_CONTAINER).first.locator("> div").last


async def _extract_file_artifact(page: Page) -> str:
    """Return a generated file's text via the panel opened by its file-icon indicator."""
    icon = _latest_turn(page).locator(sel.FILE_ARTIFACT_ICON).last
    await icon.dispatch_event("click")
    panel = page.locator(sel.ARTIFACT_PANEL).last
    try:
        await panel.wait_for(state="visible", timeout=int(_ARTIFACT_PANEL_WAIT_SECONDS * 1000))
    except PlaywrightTimeoutError as exc:
        raise PerplexityError(
            f"artifact panel did not open within {_ARTIFACT_PANEL_WAIT_SECONDS}s"
        ) from exc
    text = await panel.inner_text()
    _log.info("perplexity_extract_file_artifact", answer_chars=len(text))
    return text


async def extract_answer(page: Page) -> str:
    """Return the latest answer's markdown via its Copy button, citations stripped.

    An earlier innerText read lost markdown structure, and a P8 copy attempt failed on
    actionability (hover-to-reveal buttons made `.click()` hang). This retry avoids both:
    `dispatch_event` skips Playwright's visibility checks, and the `writeText` hook captures
    the payload without touching the OS clipboard. `.last` picks the most recent message's
    copy control (see `COPY_BUTTON` in selectors.py). The stream must have stopped first
    (`_wait_stream_stopped`) so a mid-stream copy can't truncate the answer.

    When the answer is a generated file instead (see `FILE_ARTIFACT_ICON`), the Copy flow is
    skipped entirely in favor of reading the file's own side panel.
    """
    await _wait_stream_stopped(page)
    if await _latest_turn(page).locator(sel.FILE_ARTIFACT_ICON).count() > 0:
        return await _extract_file_artifact(page)
    button = page.locator(sel.COPY_BUTTON).last
    if await button.count() == 0:
        raise PerplexityError("copy button not found (selector churn? see page/selectors.py)")
    for click_attempt in range(2):
        await page.evaluate(_HOOK_COPY_JS)
        await button.dispatch_event("click")
        deadline = time.monotonic() + _COPY_WAIT_SECONDS
        while time.monotonic() < deadline:
            text = await page.evaluate(_READ_COPY_JS)
            if text:
                await page.evaluate(_CLEAR_COPY_JS)
                answer = strip_json_fence(strip_citations(str(text)))
                _log.info("perplexity_extract_answer", answer_chars=len(answer))
                return answer
            await asyncio.sleep(_COPY_POLL_SECONDS)
        _log.warning("perplexity_copy_click_no_text", click_attempt=click_attempt)
    raise PerplexityError(f"copy button produced no text within {_COPY_WAIT_SECONDS}s")


async def extract_thread_ref(page: Page) -> str | None:
    """Return the current `/search/<uuid>` URL as an opaque workspace ref, if we're on one."""
    url = page.url
    ref = url if sel.SEARCH_URL_MARKER in url else None
    _log.info("perplexity_extract_thread_ref", workspace_ref=ref)
    return ref
