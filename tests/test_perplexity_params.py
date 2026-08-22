"""Perplexity page-params tests: Model dropdown selection before submit (no browser).

Fake page/locators only — the flow under test is `set_model`: click the Model button, click the
`menuitemradio` matching the requested name, Escape the dropdown. A missing option times out
(Playwright) and is swallowed, keeping the site default ("Claude Sonnet 5").
"""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.providers.perplexity.page import params as params_module
from ai_proxy.providers.perplexity.page import selectors as sel


class _FakeModelButton:
    def __init__(self) -> None:
        self.clicked = 0

    @property
    def first(self) -> _FakeModelButton:
        return self

    async def click(self, timeout: int = 0) -> None:
        self.clicked += 1


class _FakeOptionLocator:
    """Backs `get_by_role("menuitemradio", ...)`: `.first.click()` succeeds or times out."""

    def __init__(self, *, times_out: bool) -> None:
        self._times_out = times_out
        self.clicked = 0

    @property
    def first(self) -> _FakeOptionLocator:
        return self

    async def click(self, timeout: int = 0) -> None:
        if self._times_out:
            raise PlaywrightTimeoutError("no matching menuitemradio")
        self.clicked += 1


class _FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakePage:
    def __init__(self, *, option_found: bool = True) -> None:
        self.model_button = _FakeModelButton()
        self.option = _FakeOptionLocator(times_out=not option_found)
        self.keyboard = _FakeKeyboard()
        self.role_queries: list[dict[str, Any]] = []

    def locator(self, selector: str) -> _FakeModelButton:
        assert selector == sel.MODEL_BUTTON
        return self.model_button

    def get_by_role(self, role: str, *, name: str, exact: bool) -> _FakeOptionLocator:
        self.role_queries.append({"role": role, "name": name, "exact": exact})
        return self.option


def _patch_delays(monkeypatch: Any) -> None:
    async def _no_delay(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(params_module, "human_delay", _no_delay)


def test_set_model_noop_when_unset(monkeypatch: Any) -> None:
    _patch_delays(monkeypatch)
    page = _FakePage()

    asyncio.run(params_module.set_model(page, None))

    assert page.model_button.clicked == 0
    assert page.option.clicked == 0
    assert page.keyboard.pressed == []


def test_set_model_opens_dropdown_and_clicks_matching_option(monkeypatch: Any) -> None:
    _patch_delays(monkeypatch)
    page = _FakePage()

    asyncio.run(params_module.set_model(page, "GPT-5.6 Terra"))

    assert page.model_button.clicked == 1
    assert page.option.clicked == 1
    assert page.role_queries == [
        {"role": "menuitemradio", "name": "GPT-5.6 Terra", "exact": True}
    ]
    assert page.keyboard.pressed == ["Escape"]


def test_set_model_missing_option_keeps_site_default(monkeypatch: Any) -> None:
    _patch_delays(monkeypatch)
    page = _FakePage(option_found=False)

    asyncio.run(params_module.set_model(page, "Nonexistent Model"))

    assert page.model_button.clicked == 1
    assert page.option.clicked == 0
    assert page.keyboard.pressed == ["Escape"]  # closes the still-open dropdown
