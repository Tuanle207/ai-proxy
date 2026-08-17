"""Set generation parameters (model, aspect ratio, count) via the "tune" settings panel.

Opening the settings panel (`SETTINGS_BUTTON`) is verified against a live session. Count
options are verified (2026-08-15) to be `role="tab"` elements reading "x1".. "x4" (a Radix
UI tab list, class `flow_tab_slider_trigger`) inside that panel — NOT `role="button"` as
first assumed, which is why the original `set_count` timed out live. Aspect-ratio options
are assumed to use the same tab-slider component (same panel, same visual style) but this
is inferred, not itself directly verified — both setters swallow a missing/mismatched
option instead of failing the whole generation, since Flow will just keep its current
default for that parameter.
"""

from __future__ import annotations

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.providers.google_flow.page import selectors as sel


async def _open_settings(page: Page) -> None:
    await page.locator(sel.SETTINGS_BUTTON).first.click(timeout=5000)
    await human_delay()


async def set_model(page: Page, model: str | None) -> None:
    if not model:
        return
    await _open_settings(page)
    try:
        await page.locator("button[aria-haspopup]").first.click(timeout=5000)
        await page.get_by_text(model, exact=False).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await page.keyboard.press("Escape")
    await human_delay()


async def set_aspect_ratio(page: Page, aspect_ratio: str | None) -> None:
    if not aspect_ratio:
        return
    await _open_settings(page)
    try:
        await page.get_by_role("tab", name=aspect_ratio, exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await page.keyboard.press("Escape")
    await human_delay()


async def set_count(page: Page, count: int) -> None:
    """Click the "x{count}" tab in the settings panel, if it exists."""
    await _open_settings(page)
    try:
        await page.get_by_role("tab", name=f"x{count}", exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await page.keyboard.press("Escape")
    await human_delay()

