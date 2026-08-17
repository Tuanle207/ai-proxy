"""Wait for the answer to finish streaming and classify failures.

Completion is detected by the streaming "stop" button disappearing *after* a **new** answer body
has appeared. "New" matters: when resuming an existing thread, the prior answer already satisfies
"stop button absent + answer text present" the instant the new prompt is submitted (before the new
stream even starts), so a bare presence check would return the stale answer. `wait_for_answer`
therefore takes a `baseline_count` (the answer count observed before submitting) and requires the
count to grow past it.

That baseline itself needs care: after navigating to an existing thread, `domcontentloaded` fires
before the SPA finishes hydrating/rendering the thread's prior messages, so an instantaneous count
can undercount and let `wait_for_answer` lock onto old history as it finishes rendering.
`count_answers` polls until the count is stable across consecutive reads before returning it.

Even with a correct baseline, "stop button absent" is momentarily true right after the new answer
container is created but before the stop button has mounted, which can grab a mid-stream fragment
(e.g. just a heading). `wait_for_answer` therefore also requires the answer text itself to be
unchanged across two consecutive polls before treating it as complete.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from ai_proxy.core.errors import GenerationTimeoutError
from ai_proxy.providers.perplexity.page import selectors as sel

_POLL_INTERVAL_SECONDS = 0.25
_SETTLE_POLL_INTERVAL_SECONDS = 0.2
_SETTLE_TIMEOUT_SECONDS = 5.0

# Text-only (no layout) so it's cheap to run every poll; unlike `extract.extract_answer`'s
# formatting-faithful version, this only needs to be stable-comparable, not well-formatted.
_TEXT_SANS_CITATIONS_JS = f"""(el) => {{
  const clone = el.cloneNode(true);
  clone.querySelectorAll('{sel.CITATION_NODES}').forEach((node) => node.remove());
  return clone.textContent;
}}"""


async def count_answers(page: Page) -> int:
    """Answer count once stable; call before submitting a new prompt (see module docstring)."""
    answers = page.locator(sel.ANSWER_BODY)
    deadline = time.monotonic() + _SETTLE_TIMEOUT_SECONDS
    previous = await answers.count()
    while time.monotonic() < deadline:
        await asyncio.sleep(_SETTLE_POLL_INTERVAL_SECONDS)
        current = await answers.count()
        if current == previous:
            return current
        previous = current
    return previous


async def wait_for_answer(page: Page, *, timeout: float, baseline_count: int = 0) -> None:
    """Wait until a new answer (past `baseline_count`) has finished streaming.

    Returns once a new answer body is present, the stop button is gone, and its text is unchanged
    across two consecutive polls (still-streaming text keeps growing between polls).
    """
    stop = page.locator(sel.STOP_BUTTON)
    answers = page.locator(sel.ANSWER_BODY)
    deadline = time.monotonic() + timeout
    previous_text: str | None = None
    while time.monotonic() < deadline:
        if await answers.count() > baseline_count and await stop.count() == 0:
            text = (await answers.last.evaluate(_TEXT_SANS_CITATIONS_JS)).strip()
            if text and text == previous_text:
                return
            previous_text = text
        else:
            previous_text = None
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise GenerationTimeoutError(f"answer did not complete within {timeout}s")
