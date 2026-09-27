"""`navigate.delete_project` tests: delete the current project via its own header menu.

Fake page/locators only — the flow under test: click the header menu, click the "delete"
menuitem in the resulting Radix popper, wait for the confirm dialog, click its known-label
button, then wait for the URL to leave the project. Every failure point raises
`SelectorNotFoundError` (never converted into a silent no-op), since callers are expected to
catch it themselves for best-effort cleanup.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_web_provider.core.errors import SelectorNotFoundError
from ai_web_provider.providers.google_flow.page import navigate as navigate_module
from ai_web_provider.providers.google_flow.page import selectors as sel

_PROJECT_ID = "abc123"
_PROJECT_URL = f"https://labs.google/fx/tools/flow/project/{_PROJECT_ID}"
_LIST_URL = "https://labs.google/fx/tools/flow"


class _FakeClickable:
    def __init__(self, *, times_out: bool = False) -> None:
        self._times_out = times_out
        self.clicked = 0

    @property
    def first(self) -> _FakeClickable:
        return self

    async def click(self, timeout: int = 0) -> None:
        if self._times_out:
            raise PlaywrightTimeoutError("not found")
        self.clicked += 1


class _FakeDropdown:
    def __init__(self, *, menu_item_found: bool) -> None:
        self.menu_item = _FakeClickable(times_out=not menu_item_found)
        self.locator_calls: list[str] = []

    def locator(self, selector: str) -> _FakeClickable:
        self.locator_calls.append(selector)
        return self.menu_item


class _FakeButton:
    def __init__(self, text: str) -> None:
        self._text = text
        self.clicked = 0

    async def inner_text(self) -> str:
        return self._text

    async def click(self, timeout: int = 0) -> None:
        self.clicked += 1


class _FakeButtonsQuery:
    def __init__(self, buttons: list[_FakeButton]) -> None:
        self._buttons = buttons

    async def count(self) -> int:
        return len(self._buttons)

    def nth(self, index: int) -> _FakeButton:
        return self._buttons[index]


class _FakeDialog:
    def __init__(self, *, visible: bool, button_labels: list[str]) -> None:
        self._visible = visible
        self.buttons = [_FakeButton(label) for label in button_labels]

    async def wait_for(self, *, state: str, timeout: float) -> None:
        if not self._visible:
            raise PlaywrightTimeoutError("dialog never appeared")

    def get_by_role(self, role: str) -> _FakeButtonsQuery:
        assert role == "button"
        return _FakeButtonsQuery(self.buttons)


class _FakeDialogLocator:
    def __init__(self, dialog: _FakeDialog) -> None:
        self._dialog = dialog

    @property
    def last(self) -> _FakeDialog:
        return self._dialog


class _FakePage:
    def __init__(
        self,
        *,
        url: str = _PROJECT_URL,
        menu_item_found: bool = True,
        dialog_visible: bool = True,
        confirm_labels: list[str] | None = None,
        redirect_succeeds: bool = True,
    ) -> None:
        self.url = url
        self.header_menu_button = _FakeClickable()
        self.dropdown = _FakeDropdown(menu_item_found=menu_item_found)
        self.dialog = _FakeDialog(
            visible=dialog_visible, button_labels=confirm_labels or ["Hủy", "Xoá dự án"]
        )
        self._redirect_succeeds = redirect_succeeds
        self.wait_for_url_calls = 0

    def locator(self, selector: str) -> Any:
        if selector == sel.HEADER_MENU_BUTTON:
            return self.header_menu_button
        if selector == sel.RADIX_POPPER_DROPDOWN:
            return self.dropdown
        if selector == sel.CONFIRM_DIALOG:
            return _FakeDialogLocator(self.dialog)
        raise AssertionError(f"unexpected selector {selector!r}")

    async def wait_for_url(self, predicate: Callable[[str], bool], timeout: float) -> None:
        self.wait_for_url_calls += 1
        if not self._redirect_succeeds:
            raise PlaywrightTimeoutError("no redirect")
        self.url = _LIST_URL


@pytest.fixture
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(navigate_module, "human_delay", _noop)


def test_delete_project_wrong_page_raises(_no_delay: None) -> None:
    page = _FakePage(url=_LIST_URL)

    with pytest.raises(SelectorNotFoundError):
        asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))

    assert page.header_menu_button.clicked == 0


def test_delete_project_happy_path(_no_delay: None) -> None:
    page = _FakePage()

    asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))

    assert page.header_menu_button.clicked == 1
    assert page.dropdown.locator_calls == [sel.DELETE_MENU_ITEM]
    assert page.dropdown.menu_item.clicked == 1
    assert page.dialog.buttons[1].clicked == 1  # "Xoá dự án", not "Hủy"
    assert page.wait_for_url_calls == 1


def test_delete_project_missing_delete_menu_item_raises(_no_delay: None) -> None:
    page = _FakePage(menu_item_found=False)

    with pytest.raises(SelectorNotFoundError):
        asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))

    assert page.header_menu_button.clicked == 1


def test_delete_project_dialog_never_appears_raises(_no_delay: None) -> None:
    page = _FakePage(dialog_visible=False)

    with pytest.raises(SelectorNotFoundError):
        asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))


def test_delete_project_no_confirm_button_match_raises(_no_delay: None) -> None:
    page = _FakePage(confirm_labels=["Hủy", "unrelated"])

    with pytest.raises(SelectorNotFoundError):
        asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))

    for button in page.dialog.buttons:
        assert button.clicked == 0


def test_delete_project_no_redirect_raises(_no_delay: None) -> None:
    page = _FakePage(redirect_succeeds=False)

    with pytest.raises(SelectorNotFoundError):
        asyncio.run(navigate_module.delete_project(page, _PROJECT_ID))

    assert page.dialog.buttons[1].clicked == 1
