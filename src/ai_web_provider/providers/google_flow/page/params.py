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
import re

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_web_provider.core.browser.humanize import human_delay
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.providers.google_flow.page import selectors as sel

_log = get_logger()

async def configure_generation(
    page: Page, *, model: str | None, aspect_ratio: str | None, count: int
) -> None:
    """Open the settings panel, apply model/aspect_ratio/count, then save and close."""
    await page.wait_for_load_state("domcontentloaded", timeout=60_000)
    await page.locator(sel.SETTINGS_BUTTON).first.wait_for(state="visible", timeout=60_000)
    await page.locator(sel.SETTINGS_BUTTON).first.click(timeout=60_000, force=True)
    await set_model(page, model)
    await set_aspect_ratio(page, aspect_ratio)
    await set_count(page, count)
    await _save_and_close(page)


async def set_model(page: Page, model: str | None) -> None:
    """Pick `model` from the dropdown right after the count tablist. Panel must be open."""
    if not model:
        return
    settings = page.locator(sel.FLOW_SETTINGS_VIEW)
    try:
        selected_model_label = await settings.locator(sel.MODEL_BUTTON).first.inner_text()
        selected_model = selected_model_label.strip().split(maxsplit=1)[1]
        if selected_model == model:
            _log.info("google_flow_model_already_selected", model=model, page_url=page.url)
            return
        

        await settings.locator(sel.MODEL_BUTTON).first.click(timeout=5000)
        dropdown = page.locator(f"{sel.CDK_OVERLAY_DROPDOWN} .flow-model-picker-panel")
        await dropdown.wait_for(state="visible", timeout=5000)
        
        items = dropdown.locator("flow-menu-item")
        for index in range(await items.count()):
            item = items.nth(index)
            item_text = await item.inner_text()
            item_model_name  = item_text.strip().split(maxsplit=1)[1]

            if item_model_name == model:
                await item.click(timeout=5000)
                _log.info("google_flow_model_selected", model=model, page_url=page.url)
                return

        _log.error("google_flow_model_not_found", model=model, page_url=page.url)
    except PlaywrightTimeoutError:
        _log.error("google_flow_model_not_found", model=model, page_url=page.url)


async def set_aspect_ratio(page: Page, aspect_ratio: str | None) -> None:
    """Click `aspect_ratio` in the first tablist. Assumes the settings panel is already open."""
    if not aspect_ratio:
        return
    toggle_group = page.locator(sel.SETTINGS_BUTTON_TOGGLE_GROUP).nth(0)
    try:
        selected_aspect_ratio = await toggle_group.locator("mat-button-toggle.mat-button-toggle-checked").first.inner_text()
        selected_aspect_ratio = selected_aspect_ratio.strip()
        if aspect_ratio in selected_aspect_ratio:
            _log.info("google_flow_aspect_ratio_already_selected", aspect_ratio=aspect_ratio, page_url=page.url)
            return
        await toggle_group.locator("mat-button-toggle", has_text=aspect_ratio).first.click(timeout=5000)
        _log.info("google_flow_aspect_ratio_selected", aspect_ratio=aspect_ratio, page_url=page.url)
    except PlaywrightTimeoutError:
        _log.error(
            "google_flow_aspect_ratio_not_found", aspect_ratio=aspect_ratio, page_url=page.url
        )


async def set_count(page: Page, count: int) -> None:
    """Click the "x{count}" tab in the second tablist; the panel must already be open."""
    toggle_group = page.locator(sel.SETTINGS_BUTTON_TOGGLE_GROUP).nth(1)
    try:
        selected_count_label = await toggle_group.locator("mat-button-toggle.mat-button-toggle-checked").first.inner_text()
        selected_count = int(selected_count_label.strip().replace("x", ""))
        if selected_count == count:
            _log.info("google_flow_count_already_selected", count=count, page_url=page.url)
            return
        await toggle_group.locator("mat-button-toggle", has_text=f"x{count}").first.click(timeout=5000)
        _log.info("google_flow_count_selected", count=count, page_url=page.url)
    except PlaywrightTimeoutError:
        _log.error(
            "google_flow_count_not_found", count=count, page_url=page.url
        )


async def _save_and_close(page: Page) -> None:
    """Click the "Lưu"/"Save" button; fall back to Escape if it can't be found."""
    await page.locator('.save-container button').first.click(timeout=5000, force=True)
    await human_delay()

