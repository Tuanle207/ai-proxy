"""Set generation parameters (model, aspect ratio, count) via the "tune" settings panel.

Verified 2026-08-22 (live, Vietnamese UI): the panel exposes two `[role="tablist"]` elements —
the first is aspect ratio (default "16:9"), the second is count (default "x1") — and is closed
via a "Lưu"/"Save" button, not Escape. The model dropdown trigger sits right after the count
tablist's parent element and opens a Radix popper listing `role="menuitem"` options (default
"Nano Banana Lite"). `configure_generation` opens the panel once, applies all three settings
(each best-effort — a missing option keeps Flow's current default instead of failing the whole
generation), then saves and closes; the individual setters assume the panel is already open.
"""

from __future__ import annotations

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.providers.google_flow.page import selectors as sel


async def configure_generation(
    page: Page, *, model: str | None, aspect_ratio: str | None, count: int
) -> None:
    """Open the settings panel, apply model/aspect_ratio/count, then save and close."""
    await page.locator(sel.SETTINGS_BUTTON).first.click(timeout=5000)
    await human_delay()
    await set_model(page, model)
    await set_aspect_ratio(page, aspect_ratio)
    await set_count(page, count)
    await _save_and_close(page)


async def set_model(page: Page, model: str | None) -> None:
    """Pick `model` from the dropdown right after the count tablist. Panel must be open."""
    if not model:
        return
    tablist = page.locator(sel.SETTINGS_TABLIST).nth(1)
    try:
        await tablist.locator(sel.MODEL_BUTTON_XPATH).first.click(timeout=5000)
        dropdown = page.locator(sel.RADIX_POPPER_DROPDOWN)
        await dropdown.get_by_role("menuitem", name=model, exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await human_delay()


async def set_aspect_ratio(page: Page, aspect_ratio: str | None) -> None:
    """Click `aspect_ratio` in the first tablist. Assumes the settings panel is already open."""
    if not aspect_ratio:
        return
    tablist = page.locator(sel.SETTINGS_TABLIST).nth(0)
    try:
        await tablist.get_by_role("tab", name=aspect_ratio, exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await human_delay()


async def set_count(page: Page, count: int) -> None:
    """Click the "x{count}" tab in the second tablist. Assumes the settings panel is already open."""
    tablist = page.locator(sel.SETTINGS_TABLIST).nth(1)
    try:
        await tablist.get_by_role("tab", name=f"x{count}", exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    await human_delay()


async def _save_and_close(page: Page) -> None:
    """Click the "Lưu"/"Save" button; fall back to Escape if it can't be found."""
    buttons = page.get_by_role("button")
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        text = (await button.inner_text()).strip().lower()
        if any(label in text for label in sel.SETTINGS_SAVE_BUTTON_LABELS):
            await button.click(timeout=5000)
            await human_delay()
            return
    await page.keyboard.press("Escape")
    await human_delay()


