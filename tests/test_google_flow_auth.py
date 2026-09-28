"""Google Flow authentication tests that do not launch a browser."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ai_web_provider.core.models import Account
from ai_web_provider.providers.google_flow import auth as auth_module


def test_interactive_login_requires_headful_browser() -> None:
    backend = SimpleNamespace(headless=True)

    with pytest.raises(auth_module.HeadlessLoginError, match="AI_PROXY_HEADLESS=false"):
        asyncio.run(
            auth_module.interactive_login(
                Account(email="account@example.com"),
                SimpleNamespace(),
                backend,
            )
        )
