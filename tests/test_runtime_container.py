"""Shared Camoufox lifecycle tests (no real browser launched)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ai_web_provider.core.config import Settings
from ai_web_provider.runtime.container import ProviderRuntimeContainer


class _Browser:
    def is_connected(self) -> bool:
        return True


class _Camoufox:
    instances: list[_Camoufox] = []

    def __init__(self, **options: object) -> None:
        self.options = options
        self.browser = _Browser()
        self.exited = False
        self.instances.append(self)

    async def __aenter__(self) -> _Browser:
        return self.browser

    async def __aexit__(self, *_: object) -> None:
        self.exited = True


def test_container_starts_one_shared_image_blocking_browser(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        _Camoufox.instances.clear()
        monkeypatch.setattr("ai_web_provider.runtime.container.AsyncCamoufox", _Camoufox)
        container = ProviderRuntimeContainer(Settings(data_dir=str(tmp_path)))

        await container.startup()
        await container.startup()

        assert len(_Camoufox.instances) == 1
        browser = _Camoufox.instances[0].browser
        assert _Camoufox.instances[0].options["block_images"] is True
        assert all(runtime.backend._browser is browser for runtime in container.runtimes.values())

        await container.shutdown()
        await container.shutdown()

        assert _Camoufox.instances[0].exited
        assert all(runtime.backend._browser is None for runtime in container.runtimes.values())

    asyncio.run(run())


def test_container_passes_headless_mode_to_every_backend(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        _Camoufox.instances.clear()
        monkeypatch.setattr("ai_web_provider.runtime.container.AsyncCamoufox", _Camoufox)
        container = ProviderRuntimeContainer(Settings(data_dir=str(tmp_path), headless=False))

        await container.startup()

        assert _Camoufox.instances[0].options["headless"] is False
        assert all(not runtime.backend.headless for runtime in container.runtimes.values())

        await container.shutdown()

    asyncio.run(run())
