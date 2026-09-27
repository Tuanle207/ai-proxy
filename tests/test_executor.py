import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_proxy.core.errors import SelectorNotFoundError
from ai_proxy.core.models import Account, TaskKind, TaskRequest, TaskResult
from ai_proxy.runtime.executor import ProviderExecutor


class _Slot:
    email = "account@example.com"

    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class _Pool:
    def __init__(self, slot: _Slot) -> None:
        self._slot = slot

    async def try_acquire(self, **_: object) -> _Slot:
        return self._slot


class _Page:
    def __init__(self) -> None:
        self.closed = False

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
        self.account = Account(email="account@example.com")
        self.success = 0
        self.failure = 0

    def get(self, _: str) -> Account:
        return self.account

    async def record_success_async(self, _: str) -> None:
        self.success += 1

    async def record_failure_async(self, _: str) -> None:
        self.failure += 1


class _Adapter:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def execute(self, session, request: TaskRequest) -> TaskResult:
        if self._error:
            raise self._error
        return TaskResult(request=request, account_email=session.account.email)

    def classify_failure(self, _: BaseException):
        return None


def _executor(error: Exception | None = None):
    slot = _Slot()
    page = _Page()
    accounts = _Accounts()
    runtime = SimpleNamespace(pool=_Pool(slot), accounts=accounts, backend=_Backend(page), settings=SimpleNamespace(), adapter=_Adapter(error))
    container = SimpleNamespace(settings=SimpleNamespace(max_retries=1, headless=True, cooldown_minutes=5, quota_cooldown_minutes=120), paths=SimpleNamespace(outputs_dir=Path("outputs")), provider=lambda _: runtime)
    return ProviderExecutor(container), slot, page, accounts


def test_executor_closes_page_releases_slot_and_records_success() -> None:
    async def run() -> None:
        executor, slot, page, accounts = _executor()
        await executor.execute(TaskRequest(provider="test", kind=TaskKind.TEXT, prompt="test"))
        assert page.closed and slot.released and accounts.success == 1 and accounts.failure == 0

    asyncio.run(run())


def test_executor_closes_page_releases_slot_and_records_failure() -> None:
    async def run() -> None:
        executor, slot, page, accounts = _executor(SelectorNotFoundError("changed"))
        with pytest.raises(SelectorNotFoundError):
            await executor.execute(TaskRequest(provider="test", kind=TaskKind.TEXT, prompt="test"))
        assert page.closed and slot.released and accounts.success == 0 and accounts.failure == 1

    asyncio.run(run())
