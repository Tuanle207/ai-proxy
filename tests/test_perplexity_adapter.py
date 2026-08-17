"""Perplexity adapter tests: execute shape, failure classification, cleanup (no browser)."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.worker.failure import AccountEffect
from ai_proxy.providers.perplexity import adapter as adapter_module
from ai_proxy.providers.perplexity.adapter import PerplexityAdapter
from ai_proxy.providers.perplexity.errors import PerplexityError
from tests.fakes import make_deps, make_session


def test_classify_failure_delegates_unknown() -> None:
    adapter = PerplexityAdapter(make_deps(DataPaths("data")))
    assert adapter.classify_failure(RuntimeError("boom")) is None


def test_classify_failure_perplexity_error_non_retryable() -> None:
    adapter = PerplexityAdapter(make_deps(DataPaths("data")))
    policy = adapter.classify_failure(PerplexityError("answer body not found"))
    assert policy is not None
    assert policy.retryable is False
    assert policy.account_effect is AccountEffect.NONE


def test_execute_returns_text_artifact(monkeypatch: Any, tmp_path: Any) -> None:
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    async def _fake_extract_answer(page: Any) -> tuple[str, list[dict[str, str]]]:
        return "hello world", [{"url": "https://example.com", "title": "Example"}]

    async def _fake_extract_thread_ref(page: Any) -> str:
        return "https://www.perplexity.ai/search/test"

    monkeypatch.setattr(adapter_module.navigate, "open_thread", _noop)
    monkeypatch.setattr(adapter_module.prompt, "submit_prompt", _noop)
    monkeypatch.setattr(adapter_module.wait, "wait_for_answer", _noop)
    monkeypatch.setattr(adapter_module.extract, "extract_answer", _fake_extract_answer)
    monkeypatch.setattr(adapter_module.extract, "extract_thread_ref", _fake_extract_thread_ref)

    paths = DataPaths(tmp_path / "data")
    adapter = PerplexityAdapter(make_deps(paths))
    session = make_session(paths)
    session.page = object()  # execute only requires a non-None page

    request = TaskRequest(provider="perplexity", kind=TaskKind.TEXT, prompt="hi")
    result = asyncio.run(adapter.execute(session, request))

    assert result.account_email == "fake@example.com"
    assert result.workspace_ref == "https://www.perplexity.ai/search/test"
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.kind is TaskKind.TEXT
    assert artifact.text == "hello world"
    assert artifact.meta["citations"] == [{"url": "https://example.com", "title": "Example"}]
