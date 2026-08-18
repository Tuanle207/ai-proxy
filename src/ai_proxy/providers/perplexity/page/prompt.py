"""Type/paste the prompt and submit it to Perplexity.

The composer is a contenteditable `<div id="ask-input">` (not a `<textarea>`); submit via the
`button[aria-label="Submit"]` control (verified 2026-08-16). Click-to-focus first, matching the
same discipline as `google_flow/page/prompt.py`, so the editor's internal selection state is set
before typing.

Fill mechanism is fresh-vs-resumed gated (both `execCommand` paste and a synthetic `paste`
ClipboardEvent were e2e-verified 2026-08-18 to only work, or not work at all, in some composer
states — see `/memories/repo/vcre-ai-proxy.md`): fresh threads use the fast `paste_text`
(`execCommand`), resumed threads keep the slower but universally-reliable char-by-char
`human_type`, since only that mechanism is proven to work when resuming.
"""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.core.browser.humanize import human_delay, human_type, paste_text
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.providers.perplexity.page import selectors as sel

_log = get_logger()


async def submit_prompt(page: Page, text: str, *, fresh: bool) -> None:
    _log.info(
        "perplexity_submit_prompt",
        prompt_chars=len(text),
        newline_count=text.count("\n"),
        fresh=fresh,
    )
    box = page.locator(sel.PROMPT_TEXTBOX)
    await box.click()
    await human_delay(0.1, 0.3)
    # if fresh:
    await paste_text(box, text)
    # else:
        # await human_type(box, text)
    await human_delay()
    await page.locator(sel.SUBMIT_BUTTON).click()
    _log.info("perplexity_submit_prompt_clicked")
