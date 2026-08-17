"""Perplexity auth-probe and answer-wait tests (fake page/locators, no browser).

The probe regression tests encode the live bug (2026-08-17): the old "Sign In is absent"
check read 0 right after `domcontentloaded`, before React mounted the sidebar, calling a
logged-out session "logged in" (`interactive_login` succeeded instantly with nothing
typed). The probe now keys on the positive bell marker (`#pplx-icon-bell`), which only
renders for authenticated users.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_proxy.core.errors import AuthError
from ai_proxy.providers.perplexity import auth as auth_module
from ai_proxy.providers.perplexity.page import selectors as sel
from ai_proxy.providers.perplexity.page import wait as wait_module


class FakeLocator:
    """Yields each scheduled `count()` value once, then repeats the last."""

    def __init__(self, counts: list[int]):
        self._counts = counts
        self._reads = 0

    async def count(self) -> int:
        value = self._counts[min(self._reads, len(self._counts) - 1)]
        self._reads += 1
        return value


class FakePage:
    def __init__(self, url: str, locators: dict[str, FakeLocator]):
        self.url = url
        self._locators = locators

    def locator(self, selector: str) -> FakeLocator:
        return self._locators[selector]

    async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
        return None


def _fast_probe(monkeypatch: Any) -> None:
    monkeypatch.setattr(auth_module, "_SETTLE_POLL_SECONDS", 0.0)


def test_probe_true_when_bell_renders_late(monkeypatch: Any) -> None:
    """Hydration delay: the bell only mounts after the first read — still logged in."""
    _fast_probe(monkeypatch)
    page = FakePage(
        "https://www.perplexity.ai/",
        {sel.LOGGED_IN_BELL: FakeLocator([0, 1])},
    )
    assert asyncio.run(auth_module.probe_logged_in(page)) is True


def test_probe_true_when_bell_present(monkeypatch: Any) -> None:
    _fast_probe(monkeypatch)
    page = FakePage(
        "https://www.perplexity.ai/",
        {sel.LOGGED_IN_BELL: FakeLocator([1])},
    )
    assert asyncio.run(auth_module.probe_logged_in(page)) is True


def test_probe_false_when_bell_never_appears(monkeypatch: Any) -> None:
    """The exact live bug: absent "Sign In" used to count as logged in. It no longer does."""
    _fast_probe(monkeypatch)
    page = FakePage(
        "https://www.perplexity.ai/",
        {sel.LOGGED_IN_BELL: FakeLocator([0])},
    )
    assert asyncio.run(auth_module.probe_logged_in(page)) is False


def test_probe_false_off_perplexity(monkeypatch: Any) -> None:
    _fast_probe(monkeypatch)
    page = FakePage(
        "https://accounts.google.com/",
        {sel.LOGGED_IN_BELL: FakeLocator([1])},
    )
    assert asyncio.run(auth_module.probe_logged_in(page)) is False


def test_wait_for_answer_raises_auth_on_login_wall() -> None:
    page = FakePage(
        "https://www.perplexity.ai/search/x",
        {
            sel.LOGIN_BUTTON: FakeLocator([1]),
            sel.STOP_BUTTON: FakeLocator([0]),
            sel.ANSWER_BODY: FakeLocator([0]),
        },
    )
    with pytest.raises(AuthError):
        asyncio.run(wait_module.wait_for_answer(page, timeout=1.0))
