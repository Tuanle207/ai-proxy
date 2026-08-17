"""Perplexity provider tests: params schema, self-registration, adapter build.

The module-level registry is cleared by the autouse fixture in `conftest.py`, so the
self-registration test forces `importlib.reload` to re-run `perplexity/__init__.py`.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from ai_proxy.core.models import TaskKind
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.params import json_schema
from tests.fakes import make_deps


def test_perplexity_params_schema() -> None:
    from ai_proxy.providers.perplexity.params import PerplexityParams

    schema = json_schema(PerplexityParams)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"focus", "model", "search_mode", "include_citations"}
    assert PerplexityParams.model_validate({}).include_citations is True
    with pytest.raises(ValueError):
        PerplexityParams.model_validate({"aspect_ratio": "16:9"})


def test_perplexity_self_registers(tmp_path: Any) -> None:
    import ai_proxy.providers.perplexity as perplexity

    importlib.reload(perplexity)

    assert "perplexity" in registry.names()
    spec = registry.get("perplexity")
    assert spec.name == "perplexity"
    assert spec.display_name == "Perplexity"
    assert spec.capabilities.task_kinds == frozenset({TaskKind.TEXT})
    assert spec.capabilities.max_outputs_per_request == 1
    assert spec.capabilities.supports_reference_inputs is False
    assert spec.capabilities.supports_workspace_reuse is True
    assert spec.capabilities.requires_browser is True

    adapter = spec.build_adapter(make_deps(DataPaths(tmp_path / "data")))
    assert adapter.classify_failure(RuntimeError("boom")) is None
