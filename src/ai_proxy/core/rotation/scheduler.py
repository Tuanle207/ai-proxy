"""Ties account selection, concurrency limiting, and retry/cooldown together."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeVar

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.errors import NoAvailableAccountError
from ai_proxy.core.models import Account
from ai_proxy.core.rotation.limiter import ConcurrencyLimiter
from ai_proxy.core.rotation.strategy import RotationStrategy

T = TypeVar("T")


class JobScheduler:
    """Runs a job on a rotated, available account with retries across other accounts."""

    def __init__(
        self,
        account_manager: AccountManager,
        strategy: RotationStrategy,
        limiter: ConcurrencyLimiter,
        *,
        max_retries: int = 3,
        cooldown: timedelta = timedelta(minutes=5),
    ) -> None:
        self._accounts = account_manager
        self._strategy = strategy
        self._limiter = limiter
        self._max_retries = max_retries
        self._cooldown = cooldown

    async def run(self, job: Callable[[Account], Awaitable[T]]) -> T:
        """Run `job(account)`, retrying on a different account on failure.

        Raises `NoAvailableAccountError` if no account is available at all, or
        re-raises the last job exception once accounts/retries are exhausted.
        """
        last_error: Exception | None = None
        attempted: set[str] = set()
        for _ in range(self._max_retries):
            available = [a for a in self._accounts.get_available() if a.email not in attempted]
            if not available:
                break
            account = self._strategy.select(available)
            attempted.add(account.email)
            try:
                async with self._limiter.acquire(account.email):
                    result = await job(account)
                self._accounts.record_success(account.email)
                return result
            except Exception as exc:  # broad: any job failure triggers retry-on-another-account
                last_error = exc
                self._accounts.record_failure(account.email)
                self._accounts.set_cooldown(account.email, self._cooldown)
        if last_error is not None:
            raise last_error
        raise NoAvailableAccountError("no available account to run the job")
