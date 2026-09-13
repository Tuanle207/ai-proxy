"""Set Perplexity composer options (the model) before a prompt is submitted.

The model picker (`MODEL_BUTTON`, see selectors.py) opens a Radix dropdown whose options are
`role="menuitemradio"` items carrying the model name as their accessible name (e.g. "GPT-5.6
Terra"; the site default is "Claude Sonnet 5"). Options are matched by accessible name via
`get_by_role` rather than by anchoring on the dropdown's `div[data-radix-popper-content-wrapper]`
host, which is a generic Radix popper wrapper shared by every dropdown on the page.

Best-effort (mirrors `google_flow/page/params.py`): when the requested model name is not among
the options, the miss is logged and the site default is kept — the job still runs, just on the
default model. A missing Model *button* still fails loudly, though: that means selector churn
worth surfacing, not a user typo.
"""

from __future__ import annotations

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.providers.perplexity.page import selectors as sel

_log = get_logger()


async def set_model(page: Page, model: str | None) -> None:
    """Pick `model` in the composer's Model dropdown; keep the site default when it's missing.

    `None`/`""` means "use the site default" and skips the dropdown entirely. Selecting an
    option closes the dropdown; the trailing Escape is therefore a no-op then, but closes the
    still-open menu after a miss.
    """
    if not model:
        return
    # The model button is verified to always be the 3rd aria-haspopup="menu" match in the
    # container (see selectors.py) — its aria-label mirrors current selection, not a fixed name.
    button = page.locator(sel.MODEL_BUTTON).nth(2)
    # Skip the open+reselect if it's already the requested model (also avoids re-resolving a
    # resumed thread's non-default pick).
    if await button.get_attribute("aria-label") == model:
        return
    await button.click(timeout=5000)
    await human_delay()
    try:
        await page.get_by_role("menuitemradio", name=model, exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        _log.error("perplexity_model_not_found", model=model, page_url=page.url)
    await page.keyboard.press("Escape")
    await human_delay()
