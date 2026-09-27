"""`open_flow` tests: an expired Flow session must raise `AuthError`, not a selector timeout."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_web_provider.core.errors import AuthError, SelectorNotFoundError
from ai_web_provider.providers.google_flow.page import navigate as navigate_module
from ai_web_provider.providers.google_flow.page.selectors import FLOW_URL


class _FakePage:
    """`goto` records the target but leaves `url` as pre-set (simulating a server redirect)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.goto_calls: list[str] = []

    async def goto(self, target: str) -> None:
        self.goto_calls.append(target)


@pytest.fixture
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(navigate_module, "human_delay", _noop)


def test_open_flow_raises_auth_error_on_login_redirect(_no_delay: None) -> None:
    page = _FakePage("https://accounts.google.com/o/oauth2/auth?...")

    with pytest.raises(AuthError):
        asyncio.run(navigate_module.open_flow(page))

    assert page.goto_calls == [FLOW_URL]


def test_open_flow_ok_on_authenticated_page(_no_delay: None) -> None:
    page = _FakePage("https://labs.google/fx/tools/flow")

    asyncio.run(navigate_module.open_flow(page))

    assert page.goto_calls == [FLOW_URL]


def test_open_project_raises_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _FakePage(FLOW_URL)

    async def _unavailable(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(navigate_module, "_navigate_to_project", _unavailable)

    with pytest.raises(SelectorNotFoundError, match="configured-project"):
        asyncio.run(navigate_module.open_project(page, "configured-project"))
