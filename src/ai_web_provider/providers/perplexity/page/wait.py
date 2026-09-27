"""Wait for the answer to finish streaming and classify failures.

Completion = a **new** answer has appeared *and* streaming has stopped (the "Stop response"
control is no longer in its active/`data-state="open"` state) *and* the answer text is stable.

"New" matters: when resuming an existing thread, the prior answer already satisfies "not streaming
+ answer text present" the instant the new prompt is submitted (before the new stream even
starts), so a bare presence check would return the stale answer. `wait_for_answer` detects "new"
by the answer count growing past `baseline_count`, falling back to the last answer's text changing
from `baseline_text` (captured before submitting) — this also copes with fast answers on long
threads, where virtualized rendering can keep the DOM answer *count* from rising even though a new
answer rendered.

Streaming state uses the stop control's active selector (`STOP_BUTTON_ACTIVE`, `data-state="open"`)
rather than its bare presence: the button persists after completion with `data-state="closed"`, so
the bare `STOP_BUTTON` never reports zero once any answer has completed (observed 2026-08-18).

`count_answers` polls until the count is stable across consecutive reads before returning it,
because after navigating to an existing thread `domcontentloaded` fires before the SPA finishes
rendering the prior messages (an instantaneous count can undercount and lock onto old history).

Even with a correct baseline, "not streaming" is momentarily true right after the new answer
container is created but before the stop button has mounted, which can grab a mid-stream fragment
(e.g. just a heading). The answer text must therefore be unchanged across two consecutive polls
before completion is declared.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page

from ai_web_provider.core.errors import GenerationTimeoutError
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.providers.perplexity.page import selectors as sel

_log = get_logger()

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
            _log.info("perplexity_count_answers", baseline_count=current)
            return current
        previous = current
    _log.info("perplexity_count_answers", baseline_count=previous, settled=False)
    return previous


async def last_answer_text(page: Page) -> str:
    """Return the current last answer's text (citations stripped), or "" when there is none.

    Captured *before* submitting, alongside `count_answers`, as the text baseline for "a new
    answer appeared" (see `wait_for_answer`).
    """
    answers = page.locator(sel.ANSWER_BODY)
    if await answers.count() == 0:
        return ""
    return str(await answers.last.evaluate(_TEXT_SANS_CITATIONS_JS)).strip()


async def wait_for_answer(
    page: Page,
    *,
    timeout: float,
    baseline_count: int = 0,
    baseline_text: str = "",
) -> None:
    """Wait until a new answer (past the baseline) has finished streaming.

    "New" is detected by the answer count growing past `baseline_count` or, when that stays flat
    (fast answers on virtualized long threads), the last answer's text changing from
    `baseline_text`. Completion then requires the active stop control to be gone and the answer
    text to be unchanged across two consecutive polls.
    """
    active_stop = page.locator(sel.STOP_BUTTON_ACTIVE)
    answers = page.locator(sel.ANSWER_BODY)
    start = time.monotonic()
    deadline = start + timeout
    previous_text: str | None = None
    while time.monotonic() < deadline:
        count = await answers.count()
        new_answer = count > baseline_count
        if not new_answer and baseline_text and count > 0:
            last = (await answers.last.evaluate(_TEXT_SANS_CITATIONS_JS)).strip()
            new_answer = bool(last) and last != baseline_text
        if new_answer and await active_stop.count() == 0:
            text = (await answers.last.evaluate(_TEXT_SANS_CITATIONS_JS)).strip()
            if text and text == previous_text:
                _log.info(
                    "perplexity_wait_for_answer_done",
                    baseline_count=baseline_count,
                    final_count=count,
                    elapsed_seconds=round(time.monotonic() - start, 2),
                )
                return
            previous_text = text
        else:
            previous_text = None
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    _log.error(
        "perplexity_wait_for_answer_timeout",
        baseline_count=baseline_count,
        final_count=await answers.count(),
        timeout=timeout,
    )
    raise GenerationTimeoutError(f"answer did not complete within {timeout}s")
