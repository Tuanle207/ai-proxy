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
from ai_proxy.providers.perplexity.page.navigate import resolve_thread_ref
from tests.fakes import make_deps, make_session


def test_resolve_thread_ref_bare_id() -> None:
    assert resolve_thread_ref("abc-123") == "https://www.perplexity.ai/search/abc-123"


def test_resolve_thread_ref_full_url_passthrough() -> None:
    url = "https://www.perplexity.ai/search/abc-123"
    assert resolve_thread_ref(url) == url


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

    async def _fake_count_answers(page: Any) -> int:
        return 0

    async def _fake_extract_answer(page: Any) -> str:
        return "hello world"

    async def _fake_extract_thread_ref(page: Any) -> str:
        return "https://www.perplexity.ai/search/test"

    monkeypatch.setattr(adapter_module.navigate, "open_thread", _noop)
    monkeypatch.setattr(adapter_module.prompt, "submit_prompt", _noop)
    monkeypatch.setattr(adapter_module.wait, "count_answers", _fake_count_answers)
    monkeypatch.setattr(adapter_module.wait, "wait_for_answer", _noop)
    monkeypatch.setattr(adapter_module.extract, "extract_answer", _fake_extract_answer)
    monkeypatch.setattr(adapter_module.extract, "extract_thread_ref", _fake_extract_thread_ref)

    paths = DataPaths(tmp_path / "data")
    adapter = PerplexityAdapter(make_deps(paths))
    session = make_session(paths)
    session.page = object()  # execute only requires a non-None page
    created_refs: list[str] = []

    async def _on_workspace_created(ref: str) -> None:
        created_refs.append(ref)

    session.on_workspace_created = _on_workspace_created

    request = TaskRequest(provider="perplexity", kind=TaskKind.TEXT, prompt="hi")
    result = asyncio.run(adapter.execute(session, request))

    assert result.account_email == "fake@example.com"
    assert result.workspace_ref == "https://www.perplexity.ai/search/test"
    assert created_refs == ["https://www.perplexity.ai/search/test"]
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.kind is TaskKind.TEXT
    assert artifact.text == "hello world"
