"""Navigate to Flow and reach the image-generation surface.

`open_flow`/`ensure_project` are verified against a live session (see `selectors.py` for
details). Flow's default UI is already an agent-style prompt box — there is no separate
"image mode" tab to switch to, so `switch_to_image_mode` is a documented no-op kept for
interface stability (client.py calls it unconditionally).

`create_project`/`delete_project` implement the service's fresh-project-per-image model (§S-02).
Project deletion (§6.2) is **best-effort**: callers catch and log, never converting a successful
generation into a failure. Verified live 2026-08-15: the per-card ancestor scoping works and the
list renders any newly-created project within ~1s (not instantly); the confirm dialog is
identified by clicking its last button rather than matching a label (see `selectors.py` for why).
"""

from __future__ import annotations

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.browser.humanize import human_delay
from ai_proxy.core.errors import SelectorNotFoundError
from ai_proxy.providers.google_flow.page import selectors as sel

_PROJECT_URL_MARKER = "/project/"


async def open_flow(page: Page) -> None:
    await page.goto(sel.FLOW_URL)
    await human_delay()


async def ensure_project(page: Page, *, timeout: float = 20.0, reuse_latest: bool = True) -> None:
    """Open the most recent existing project (if any and `reuse_latest`), else create one.

    Confirms success via the resulting URL either way. Raises `SelectorNotFoundError` if we
    can't confirm we're in a project within `timeout` seconds, instead of silently continuing
    to a guaranteed-to-fail prompt submission.
    """
    if _PROJECT_URL_MARKER in page.url:
        return
    if reuse_latest and await _open_latest_project(page, timeout=timeout):
        return
    await _click_new_project(page, timeout=timeout)


async def create_project(page: Page, *, timeout: float = 20.0) -> str:
    """Always create a **new** Flow project and return its id, parsed from the resulting URL."""
    if _PROJECT_URL_MARKER in page.url:
        return _project_id_from_url(page.url)
    await _click_new_project(page, timeout=timeout)
    return _project_id_from_url(page.url)


async def _click_new_project(page: Page, *, timeout: float) -> None:
    await page.locator(sel.NEW_PROJECT_BUTTON).first.click(timeout=5000)
    try:
        await page.wait_for_url(lambda url: _PROJECT_URL_MARKER in url, timeout=timeout * 1000)
    except PlaywrightTimeoutError as exc:
        raise SelectorNotFoundError(
            f"clicked {sel.NEW_PROJECT_BUTTON!r} but never reached a project URL "
            f"(stayed at {page.url!r})"
        ) from exc
    await human_delay()


def _project_id_from_url(url: str) -> str:
    idx = url.find(_PROJECT_URL_MARKER)
    if idx == -1:
        raise SelectorNotFoundError(f"not in a project URL: {url!r}")
    tail = url[idx + len(_PROJECT_URL_MARKER):]
    project_id = tail.split("/", 1)[0].split("?", 1)[0]
    if not project_id:
        raise SelectorNotFoundError(f"could not parse a project id from URL {url!r}")
    return project_id


async def delete_project(page: Page, project_id: str, *, timeout: float = 20.0) -> None:
    """Navigate back to the project list and delete `project_id` (best-effort, §6.2).

    Raises `SelectorNotFoundError` if the delete trigger or confirmation dialog cannot be
    resolved; callers treat this as non-fatal cleanup.
    """
    await page.goto(sel.FLOW_URL)
    await human_delay()
    try:
        await page.wait_for_url(lambda url: _PROJECT_URL_MARKER not in url, timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        pass  # already on the list is fine; proceed to locate the card

    trigger = await _project_delete_button(page, project_id)
    if trigger is None:
        raise SelectorNotFoundError(
            f"delete button for project {project_id!r} not found on the project list"
        )

    await trigger.click()
    dialog = page.locator(sel.CONFIRM_DIALOG).last
    try:
        await dialog.wait_for(state="visible", timeout=timeout * 1000)
    except PlaywrightTimeoutError as exc:
        raise SelectorNotFoundError("confirmation dialog did not appear") from exc
    # Matched by known label text (sel.CONFIRM_BUTTON_LABELS), not by copying the trigger's
    # sr-only label: a freshly-created project's trigger can momentarily render that label in
    # the wrong locale, which raced and failed live (see selectors.py for the full rationale).
    confirm_button = await _confirm_dialog_button(dialog)
    if confirm_button is None:
        raise SelectorNotFoundError(
            f"no button in the confirmation dialog matched a known label "
            f"({sel.CONFIRM_BUTTON_LABELS!r})"
        )
    await confirm_button.click()
    await human_delay()


async def _confirm_dialog_button(dialog: Locator) -> Locator | None:
    """Find the dialog button whose text matches a known confirm label (case-insensitive)."""
    buttons = dialog.get_by_role("button")
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        text = (await button.inner_text()).strip().lower()
        if any(label in text for label in sel.CONFIRM_BUTTON_LABELS):
            return button
    return None


async def _project_delete_button(page: Page, project_id: str) -> Locator | None:
    """Find the delete trigger scoped to the card holding this project's link.

    `sel.PROJECT_DELETE_BUTTON` is the single source of truth for *what* a delete button looks
    like; only the ancestor scoping (which card it belongs to) is expressed here, so a
    concurrent job's project is never mistakenly deleted. Returns `None` if no delete button
    is scoped to `project_id`'s card.
    """
    buttons = page.locator(sel.PROJECT_DELETE_BUTTON)
    try:
        await buttons.first.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        return None
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        card_link = button.locator(
            f"xpath=ancestor::*[.//a[contains(@href, '/project/{project_id}')]][1]"
        )
        if await card_link.count() > 0:
            return button
    return None


async def _open_latest_project(page: Page, *, timeout: float) -> bool:
    """Click the first (most recent) existing project card, if any. Returns whether it worked."""
    projects = page.locator(sel.PROJECT_LINK)
    if await projects.count() == 0:
        return False
    await projects.first.click(timeout=5000)
    try:
        await page.wait_for_url(lambda url: _PROJECT_URL_MARKER in url, timeout=timeout * 1000)
    except PlaywrightTimeoutError:
        return False
    await human_delay()
    return True


async def switch_to_image_mode(page: Page) -> None:
    """No-op: Flow has no separate image-mode tab (see module docstring)."""
    return
