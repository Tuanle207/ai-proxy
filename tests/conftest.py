"""Shared fixtures: isolate the module-level provider registry between tests."""

from __future__ import annotations

import pytest

from ai_web_provider.core.provider import registry


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()
