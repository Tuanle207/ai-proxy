"""Phase 2 tests: the provider seam (registry, params schema, adapter execution)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

import pytest

from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.params import json_schema
from ai_proxy.core.provider.registry import UnknownProviderError
from ai_proxy.core.worker.failure import default_classify_failure
from tests.fakes import FakeParams, make_deps, make_session, make_spec


def test_registry_starts_empty() -> None:
    assert registry.names() == []


def test_registry_register_and_get() -> None:
    registry.register(make_spec(name="fake"))
    assert registry.names() == ["fake"]
    assert registry.get("fake").name == "fake"


def test_registry_duplicate_name_rejected() -> None:
    registry.register(make_spec(name="fake"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_spec(name="fake"))


def test_registry_unknown_name_raises() -> None:
    with pytest.raises(UnknownProviderError):
        registry.get("nope")


def test_registry_entry_point_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeEntryPoint:
        def __init__(self, name: str, load: Any) -> None:
            self.name = name
            self._load = load

        def load(self) -> Any:
            return self._load()

    class _FakeEntryPoints:
        def __init__(self, eps: list[_FakeEntryPoint]) -> None:
            self._eps = eps

        def select(self, *, group: str) -> list[_FakeEntryPoint]:
            assert group == "ai_proxy.providers"
            return self._eps

    ep = _FakeEntryPoint("third_party", lambda: registry.register(make_spec(name="third_party")))
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: _FakeEntryPoints([ep]))

    registry.discover()

    assert "third_party" in registry.names()


def test_params_json_schema_round_trip() -> None:
    schema = json_schema(FakeParams)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"mode", "count_hint"}
    assert FakeParams.model_validate({"mode": "slow", "count_hint": 2}).mode == "slow"
    with pytest.raises(ValueError):
        FakeParams.model_validate({"unknown_key": True})


def test_fake_provider_resolved_and_executed(tmp_path: Any) -> None:
    from ai_proxy.core.paths import DataPaths

    paths = DataPaths(tmp_path / "data")
    spec = make_spec()
    registry.register(spec)

    deps = make_deps(paths)
    adapter = spec.build_adapter(deps)
    session = make_session(paths, deps=deps)
    request = TaskRequest(provider="fake", kind=TaskKind.TEXT, prompt="hello")

    result = _run(adapter.execute(session, request))

    assert result.account_email == "fake@example.com"
    assert len(result.artifacts) == 1
    assert result.artifacts[0].text == "fake:text:hello"


def test_default_classify_failure_fallback() -> None:
    policy = default_classify_failure(RuntimeError("boom"))
    assert policy.retryable is True
    assert policy.error_code == "unknown"


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)
