"""Type the prompt (humanized), optionally attach reference images, and submit.

Verified 2026-08-14: the prompt box is a Slate.js rich-text editor. Typing via
`press_sequentially` without first explicitly clicking/focusing the box leaves Slate's
internal selection state unset — the DOM text looks correct but the submit button stays
`aria-disabled` forever. An explicit `.click()` before typing fixes this.

Verified 2026-08-15: once a (reused) project already has prior agent messages, `SUBMIT_BUTTON`
(`button:has-text('arrow_forward')`) matches *two* elements — an unrelated "show thinking
process" chat-log toggle (DOM order: first) and the real submit/Create button (DOM order:
last), both apparently rendering the same icon glyph as text. `.last` reliably picks the real
submit button.

`paste_text` (execCommand insertText) was tried here 2026-08-18 alongside the same change in
Perplexity's prompt.py, then reverted proactively (Perplexity's own e2e run showed it left the
submit control permanently disabled on a resumed thread). Independently e2e-verified here too on
2026-08-18: on a fresh project, `paste_text` inserts a raw text node alongside Slate's own
placeholder (Slate's internal editor state never sees the change, since `execCommand` bypasses
its controlled update path) and `SUBMIT_BUTTON` never enables. Do not use `paste_text` here at
all, fresh or resumed — `human_type` is the only mechanism proven to work with this editor.
"""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

from ai_proxy.core.browser.humanize import human_delay, human_type
from ai_proxy.providers.google_flow.page import selectors as sel


async def attach_reference_images(page: Page, reference_images: list[Path]) -> None:
    if not reference_images:
        return
    async with page.expect_file_chooser() as chooser_info:
        await page.locator(sel.REFERENCE_UPLOAD_INPUT).click()
    chooser = await chooser_info.value
    await chooser.set_files([str(p) for p in reference_images])
    await human_delay()


async def submit_prompt(
    page: Page, prompt: str, reference_images: list[Path] | None = None
) -> None:
    await attach_reference_images(page, reference_images or [])
    box = page.locator(sel.PROMPT_TEXTBOX)
    await box.click()
    await human_delay(0.1, 0.3)
    await human_type(box, prompt)
    await human_delay()
    await page.locator(sel.SUBMIT_BUTTON).last.click()
