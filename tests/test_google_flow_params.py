"""Google Flow page-params tests: settings panel (model/aspect_ratio/count) before submit.

Fake page/locators only — `configure_generation` opens the "tune" panel once, applies model
(dropdown), aspect_ratio (1st tablist tab), count (2nd tablist tab), then saves via the
"Lưu"/"Save" button. A missing option times out (Playwright) and is swallowed, keeping the
site default.
"""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_web_provider.providers.google_flow.page import params as params_module
from ai_web_provider.providers.google_flow.page import selectors as sel


class _FakeClickable:
    def __init__(self, *, times_out: bool = False, text: str = "") -> None:
        self._times_out = times_out
        self._text = text
        self.clicked = 0
        self.click_forces: list[bool] = []

    @property
    def first(self) -> _FakeClickable:
        return self

    async def click(self, timeout: int = 0, force: bool = False) -> None:
        if self._times_out:
            raise PlaywrightTimeoutError("not found")
        self.clicked += 1
        self.click_forces.append(force)

    async def inner_text(self) -> str:
        return self._text


class _FakeTablist:
    """Backs `page.locator(SETTINGS_TABLIST).nth(i)`: records the `get_by_role("tab", ...)` call."""

    def __init__(self, *, option_found: bool) -> None:
        self.tab = _FakeClickable(times_out=not option_found)
        self.role_queries: list[dict[str, Any]] = []
        self.model_button = _FakeClickable(text="🍌 Nano Banana Lite")
        self.selected = _FakeClickable(text="16:9" if option_found else "x1")

    def get_by_role(self, role: str, *, name: str, exact: bool) -> _FakeClickable:
        self.role_queries.append({"role": role, "name": name, "exact": exact})
        return self.tab

    def locator(self, selector: str, **kwargs: Any) -> _FakeClickable:
        if selector == sel.MODEL_BUTTON:
            return self.model_button
        if selector == "mat-button-toggle.mat-button-toggle-checked":
            return self.selected
        assert selector == "mat-button-toggle"
        return self.tab


class _FakeTablistLocator:
    def __init__(self, ratio_tablist: _FakeTablist, count_tablist: _FakeTablist) -> None:
        self._tablists = [ratio_tablist, count_tablist]

    def nth(self, index: int) -> _FakeTablist:
        return self._tablists[index]


class _FakeSaveButton:
    def __init__(self, *, label: str | None) -> None:
        self._label = label
        self.clicked = 0

    @property
    def first(self) -> _FakeSaveButton:
        return self

    async def inner_text(self) -> str:
        return self._label or ""

    async def click(self, timeout: int = 0, force: bool = False) -> None:
        self.clicked += 1


class _FakeButtons:
    """Backs `page.get_by_role("button")`: iterated by index like `navigate._confirm_dialog_button`."""

    def __init__(self, buttons: list[_FakeSaveButton]) -> None:
        self._buttons = buttons

    async def count(self) -> int:
        return len(self._buttons)

    def nth(self, index: int) -> _FakeSaveButton:
        return self._buttons[index]


class _FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakeDropdown:
    """Backs `page.locator(RADIX_POPPER_DROPDOWN)`: records the `get_by_role("menuitem", ...)` call."""

    def __init__(self, *, option_found: bool) -> None:
        self.option = _FakeClickable(times_out=not option_found)
        self.role_queries: list[dict[str, Any]] = []

    def get_by_role(self, role: str, *, name: str, exact: bool) -> _FakeClickable:
        self.role_queries.append({"role": role, "name": name, "exact": exact})
        return self.option

    async def wait_for(self, *, state: str, timeout: int = 0) -> None:
        assert state == "visible"

    def locator(self, selector: str, *, has_text: str) -> _FakeClickable:
        assert selector == "flow-menu-item"
        self.role_queries.append({"selector": selector, "has_text": has_text})
        return self.option


class _FakePage:
    def __init__(
        self,
        *,
        ratio_found: bool = True,
        count_found: bool = True,
        model_found: bool = True,
        save_label: str | None = "Lưu",
    ) -> None:
        self.url = "https://labs.google/fx/tools/flow/project/test"
        self.settings_button = _FakeClickable()
        self.ratio_tablist = _FakeTablist(option_found=ratio_found)
        self.count_tablist = _FakeTablist(option_found=count_found)
        self.count_tablist.selected = _FakeClickable(text="x1")
        self.model_dropdown = _FakeDropdown(option_found=model_found)
        self.save_button = _FakeSaveButton(label=save_label)
        self.keyboard = _FakeKeyboard()

    def locator(self, selector: str) -> _FakeClickable | _FakeTablistLocator | _FakeDropdown:
        if selector == sel.SETTINGS_BUTTON:
            return self.settings_button
        if selector == sel.SETTINGS_BUTTON_TOGGLE_GROUP:
            return _FakeTablistLocator(self.ratio_tablist, self.count_tablist)
        if selector == f"{sel.CDK_OVERLAY_DROPDOWN} .flow-model-picker-panel":
            return self.model_dropdown
        if selector == sel.FLOW_SETTINGS_VIEW:
            return self.count_tablist
        if selector == ".save-container button":
            return self.save_button
        raise AssertionError(f"unexpected selector {selector!r}")

    def get_by_role(self, role: str, *, name: str | None = None) -> _FakeButtons:
        assert role == "button"
        return _FakeButtons([self.save_button])


def test_set_aspect_ratio_noop_when_unset() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_aspect_ratio(page, None))

    assert page.ratio_tablist.tab.clicked == 0


def test_set_aspect_ratio_clicks_tab_in_first_tablist() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_aspect_ratio(page, "9:16"))

    assert page.ratio_tablist.tab.clicked == 1
    assert page.ratio_tablist.role_queries == []


def test_set_aspect_ratio_missing_option_keeps_default() -> None:
    page = _FakePage(ratio_found=False)

    asyncio.run(params_module.set_aspect_ratio(page, "1:1"))

    assert page.ratio_tablist.tab.clicked == 0


def test_set_count_clicks_tab_in_second_tablist() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_count(page, 3))

    assert page.count_tablist.tab.clicked == 1
    assert page.count_tablist.role_queries == []


def test_set_model_noop_when_unset() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_model(page, None))

    assert page.count_tablist.model_button.clicked == 0


def test_set_model_opens_dropdown_and_clicks_matching_option() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_model(page, "Nano Banana 2"))

    assert page.count_tablist.model_button.clicked == 1
    assert page.model_dropdown.option.clicked == 1
    assert page.model_dropdown.role_queries == [
        {"selector": "flow-menu-item", "has_text": "🍌 Nano Banana 2 Lite"}
    ]
    assert page.ratio_tablist.model_button.clicked == 0


def test_set_model_maps_legacy_nano_banana_2_name() -> None:
    page = _FakePage()

    asyncio.run(params_module.set_model(page, "Nano Banana 2"))

    assert page.model_dropdown.role_queries == [
        {"selector": "flow-menu-item", "has_text": "🍌 Nano Banana 2 Lite"}
    ]


def test_set_model_missing_option_keeps_default() -> None:
    page = _FakePage(model_found=False)

    asyncio.run(params_module.set_model(page, "Nonexistent Model"))

    assert page.count_tablist.model_button.clicked == 1
    assert page.model_dropdown.option.clicked == 0


def test_configure_generation_opens_once_applies_all_then_saves() -> None:
    page = _FakePage()

    asyncio.run(
        params_module.configure_generation(
            page, model="Nano Banana 2", aspect_ratio="4:3", count=2
        )
    )

    assert page.settings_button.clicked == 1
    assert page.settings_button.click_forces == [True]
    assert page.count_tablist.model_button.clicked == 1
    assert page.model_dropdown.option.clicked == 1
    assert page.ratio_tablist.tab.clicked == 1
    assert page.count_tablist.tab.clicked == 1
    assert page.save_button.clicked == 1
    assert page.keyboard.pressed == []


def test_configure_generation_clicks_save_button() -> None:
    page = _FakePage(save_label="unrelated button")

    asyncio.run(
        params_module.configure_generation(page, model=None, aspect_ratio=None, count=1)
    )

    assert page.save_button.clicked == 1
    assert page.keyboard.pressed == []
