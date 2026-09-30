"""Google Flow authentication tests that do not launch a browser."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ai_web_provider.providers.google_flow import auth as auth_module


def test_interactive_login_delegates_to_headed_chromium_backend() -> None:
    async def run() -> None:
        calls: list[tuple[object, str]] = []

        async def interactive_login(account: object, url: str, probe: object) -> bool:
            calls.append((account, url))
            return True

        auth = auth_module.GoogleFlowAuth(
            SimpleNamespace(backend=SimpleNamespace(interactive_login=interactive_login), paths=None)
        )
        account = SimpleNamespace(email="account@example.com")
        assert await auth.interactive_login(SimpleNamespace(account=account))
        assert calls == [(account, auth_module.FLOW_URL)]

    asyncio.run(run())
