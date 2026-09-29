import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_web_provider.core.diagnostics import mark_step
from ai_web_provider.core.errors import (
    GenerationTimeoutError,
    SelectorNotFoundError,
    TaskFailedError,
)
from ai_web_provider.core.models import Account, TaskKind, TaskRequest, TaskResult
from ai_web_provider.core.paths import DataPaths
from ai_web_provider.runtime.executor import ProviderExecutor


class _Slot:
    def __init__(self, email: str = "account@example.com") -> None:
        self.email = email
        self.released = False

    def release(self) -> None:
        self.released = True


class _Pool:
    def __init__(self, slots: list[_Slot]) -> None:
        self._slots = list(slots)
        self.handed_out: list[_Slot] = []

    async def acquire(self, **_: object) -> _Slot:
        slot = self._slots.pop(0) if len(self._slots) > 1 else self._slots[0]
        self.handed_out.append(slot)
        return slot


class _Page:
    url = "https://example.test/project/abc?token=secret"
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, *, broken: bool = False) -> None:
        self.closed = False
        self.broken = broken
        self.handlers: dict[str, object] = {}

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    async def screenshot(self, *, path: str, **_: object) -> None:
        if self.broken:
            raise RuntimeError("target closed")
        Path(path).write_bytes(b"png")

    async def content(self) -> str:
        if self.broken:
            raise RuntimeError("target closed")
        return "<html>page</html>"

    async def close(self) -> None:
        self.closed = True


class _Context:
    def __init__(self, page: _Page) -> None:
        self._page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def new_page(self):
        return self._page


class _Backend:
    def __init__(self, page: _Page) -> None:
        self._page = page

    def browser_context(self, *_: object, **__: object):
        return _Context(self._page)


class _Accounts:
    def __init__(self) -> None:
        self.success = 0
        self.failure = 0
        self.cooldowns: list[str] = []

    def get(self, email: str) -> Account:
        return Account(email=email)

    async def record_success_async(self, _: str) -> None:
        self.success += 1

    async def record_failure_async(self, _: str) -> None:
        self.failure += 1

    async def set_cooldown_async(self, email: str, _: object) -> None:
        self.cooldowns.append(email)


class _Adapter:
    """Fails with the queued errors (one per call), then succeeds."""

    def __init__(self, *errors: Exception) -> None:
        self._errors = list(errors)

    async def execute(self, session, request: TaskRequest) -> TaskResult:
        mark_step("open_project", workspace_ref="project-1")
        mark_step("configure_generation")
        if self._errors:
            session.page.handlers["console"](SimpleNamespace(type="error", text="boom"))
            raise self._errors.pop(0)
        return TaskResult(request=request, account_email=session.account.email)

    def classify_failure(self, _: BaseException):
        return None


def _executor(tmp_path: Path, *errors: Exception, max_retries: int = 1, broken_page: bool = False):
    slots = [_Slot("a@example.com"), _Slot("b@example.com")]
    page = _Page(broken=broken_page)
    accounts = _Accounts()
    runtime = SimpleNamespace(
        pool=_Pool(slots),
        accounts=accounts,
        backend=_Backend(page),
        settings=SimpleNamespace(),
        adapter=_Adapter(*errors),
    )
    settings = SimpleNamespace(
        max_retries=max_retries,
        headless=True,
        cooldown_minutes=5,
        quota_cooldown_minutes=120,
        failure_retention_days=7,
        failure_retention_max_mb=500,
    )
    paths = DataPaths(tmp_path)
    container = SimpleNamespace(settings=settings, paths=paths, provider=lambda _: runtime)
    return ProviderExecutor(container), runtime.pool, page, accounts, paths


def _request(**overrides: object) -> TaskRequest:
    return TaskRequest(provider="test", kind=TaskKind.TEXT, prompt="secret prompt", **overrides)


def _captures(paths: DataPaths) -> list[Path]:
    if not paths.failures_dir.exists():
        return []
    return sorted(p for p in paths.failures_dir.glob("*/*") if p.is_dir())


def test_executor_closes_page_releases_slot_and_records_success(tmp_path: Path) -> None:
    async def run() -> None:
        executor, pool, page, accounts, paths = _executor(tmp_path)
        result = await executor.execute(_request())
        assert page.closed and pool.handed_out[0].released
        assert accounts.success == 1 and accounts.failure == 0
        assert [a.ok for a in result.attempts] == [True]
        assert _captures(paths) == []

    asyncio.run(run())


def test_executor_generates_request_id_when_missing(tmp_path: Path) -> None:
    async def run() -> None:
        executor, *_ = _executor(tmp_path)
        result = await executor.execute(_request())
        assert result.request.request_id and result.request.request_id.startswith("req_")

    asyncio.run(run())


def test_executor_failure_writes_capture_and_raises_task_failed(tmp_path: Path) -> None:
    async def run() -> None:
        executor, pool, page, accounts, paths = _executor(
            tmp_path, SelectorNotFoundError("changed")
        )
        with pytest.raises(TaskFailedError) as info:
            await executor.execute(_request(request_id="req-123"))
        error = info.value
        assert isinstance(error.last_error, SelectorNotFoundError)
        assert error.__cause__ is error.last_error
        assert error.request_id == "req-123"
        assert error.error_code == "selector_not_found"
        assert page.closed and pool.handed_out[0].released
        assert accounts.success == 0 and accounts.failure == 1

        [capture] = _captures(paths)
        assert error.capture_ids == [capture.name]
        assert capture.name.endswith("_req-123_a1")
        assert (capture / "screenshot.png").read_bytes() == b"png"
        assert (capture / "page.html").read_text() == "<html>page</html>"
        meta = json.loads((capture / "meta.json").read_text())
        assert meta["request_id"] == "req-123"
        assert meta["attempt"] == 1
        assert meta["account_email"] == "a@example.com"
        assert meta["step"] == "configure_generation"
        assert meta["workspace_ref"] == "project-1"
        assert meta["error_type"] == "SelectorNotFoundError"
        assert meta["page_url"] == _Page.url
        assert meta["console"] == [{"type": "error", "text": "boom"}]
        assert [t["step"] for t in meta["step_timings"]] == ["open_project", "configure_generation"]
        assert "secret prompt" not in (capture / "meta.json").read_text()
        assert meta["prompt_chars"] == len("secret prompt")

    asyncio.run(run())


def test_executor_capture_problems_do_not_mask_original_error(tmp_path: Path) -> None:
    async def run() -> None:
        executor, _, page, _, paths = _executor(
            tmp_path, SelectorNotFoundError("changed"), broken_page=True
        )
        with pytest.raises(TaskFailedError) as info:
            await executor.execute(_request(request_id="req-1"))
        assert isinstance(info.value.last_error, SelectorNotFoundError)
        assert page.closed
        [capture] = _captures(paths)
        assert not (capture / "screenshot.png").exists()
        meta = json.loads((capture / "meta.json").read_text())
        assert len(meta["capture_problems"]) == 2

    asyncio.run(run())


def test_executor_retry_success_keeps_failed_attempt_history(tmp_path: Path) -> None:
    async def run() -> None:
        executor, pool, _, accounts, paths = _executor(
            tmp_path, GenerationTimeoutError("slow"), max_retries=2
        )
        result = await executor.execute(_request(request_id="req-9"))
        assert [a.ok for a in result.attempts] == [False, True]
        failed = result.attempts[0]
        assert failed.account_email == "a@example.com"
        assert failed.error_code == "timeout"
        assert failed.step == "configure_generation"
        assert failed.capture_id and failed.capture_id.endswith("_req-9_a1")
        assert result.attempts[1].account_email == "b@example.com"
        assert accounts.cooldowns == ["a@example.com"]
        assert len(_captures(paths)) == 1

    asyncio.run(run())
