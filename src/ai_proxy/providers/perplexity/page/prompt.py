"""Type the prompt (humanized) and submit it to Perplexity.

The composer is a contenteditable `<div id="ask-input">` (not a `<textarea>`); submit via the
`button[aria-label="Submit"]` control (verified 2026-08-16). Click-to-focus first, matching the
same discipline as `google_flow/page/prompt.py`, so the editor's internal selection state is set
before typing.
"""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.core.browser.humanize import human_delay, human_type
from ai_proxy.providers.perplexity.page import selectors as sel


async def submit_prompt(page: Page, text: str) -> None:
    box = page.locator(sel.PROMPT_TEXTBOX)
    await box.click()
    await human_delay(0.1, 0.3)
    await human_type(box, text)
    await human_delay()
    await page.locator(sel.SUBMIT_BUTTON).click()
