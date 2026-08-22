"""Insert the prompt through the OS clipboard + native paste, then submit to Perplexity.

The composer is a contenteditable `<div id="ask-input">` (not a `<textarea>`). Perplexity's
editor does not reliably accept programmatic insertion (`execCommand("insertText")` or a synthetic
`paste` ClipboardEvent only work in some composer states — see `/memories/repo/vcre-ai-proxy.md`),
so the verified human flow is used instead: copy the full prompt to the OS clipboard, click the
composer to establish its focus/selection, press the platform paste shortcut (`Ctrl+V` /
`Meta+V`), let the browser's native paste path update the editor, then submit.

Submission is thread-state dependent (observed live, headed, 2026-08-18): a fresh home-page
composer renders no submit button at all — a bare Enter submits — while an existing thread's
composer exposes `button[aria-label="Submit"]`, and clicking it stays the primary path.

Camoufox is Firefox-based, so Chromium's `clipboard-read`/`clipboard-write` permission grants and
`navigator.clipboard.writeText()` are not dependable; the OS clipboard (via `pyperclip`) plus a
real Ctrl/Cmd+V go through the normal editor paste path instead. See
https://github.com/microsoft/playwright/issues/13037.
"""

from __future__ import annotations

from playwright.async_api import Page

from ai_proxy.core.logging_setup import get_logger
from ai_proxy.providers.perplexity.page import selectors as sel

_log = get_logger()


async def submit_prompt(page: Page, text: str, *, fresh: bool) -> None:
    box = page.locator(sel.PROMPT_TEXTBOX)
    await box.wait_for(state="visible")

    await box.fill(text)

    editor_text = await box.inner_text()
    if not editor_text.strip():
        raise RuntimeError("Native OS clipboard paste produced no visible composer text.")

    if fresh:
        await box.press("Enter")
        _log.info("perplexity_submit_prompt_enter")
        return

    submit = page.locator(sel.SUBMIT_BUTTON)
    await submit.wait_for(state="visible")

    if not await submit.is_enabled():
        raise RuntimeError(
            "Perplexity composer has visible pasted text but Submit is disabled."
        )

    await submit.click()
    _log.info("perplexity_submit_prompt_clicked")
