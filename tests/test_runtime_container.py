"""Ungoogled-chromium lifecycle tests without starting a browser process."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ai_web_provider.core.config import Settings
from ai_web_provider.runtime.container import ProviderRuntimeContainer


class _Browser:
    instances: list[_Browser] = []

    def __init__(self, *_: object) -> None:
        self.started = 0
        self.stopped = 0
        self.instances.append(self)

    async def startup(self) -> None:
        self.started += 1

    async def shutdown(self) -> None:
        self.stopped += 1


def test_container_starts_and_stops_one_browser_manager(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        _Browser.instances.clear()
        monkeypatch.setattr(
            "ai_web_provider.runtime.container.UngoogledChromiumRuntimeManager", _Browser
        )
        container = ProviderRuntimeContainer(Settings(data_dir=str(tmp_path)))

        await container.startup()
        await container.startup()
        await container.shutdown()

        [runtime] = _Browser.instances
        assert runtime.started == 1
        assert runtime.stopped == 1

    asyncio.run(run())
