"""Capacity-aware account acquisition (fixes §1.2.1).

Replaces the "select an account, then block on its semaphore" behaviour of the CLI scheduler: a
job only blocks here when *every* account is saturated or the global browser ceiling is reached,
and it always lands on an account that has a free slot.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import Account
from ai_proxy.core.rotation.strategy import RotationStrategy

_log = get_logger()


@dataclass
class PoolStats:
    total_slots: int
    free_slots: int
    total_in_flight: int
    per_account_limit: int
    per_account_in_flight: dict[str, int]


class AccountSlot:
    """A reserved slot on a single account. Release it when the job finishes."""

    def __init__(self, pool: AccountSlotPool, email: str, *, global_held: bool = False):
        self._pool = pool
        self.email = email
        self._global_held = global_held

    def release(self) -> None:
        self._pool.release(self, global_held=self._global_held)


class AccountSlotPool:
    def __init__(
        self,
        accounts: AccountManager,
        strategy: RotationStrategy,
        *,
        per_account_limit: int,
        max_concurrent_browsers: int,
        global_semaphore: asyncio.Semaphore | None = None,
    ):
        self._accounts = accounts
        self._strategy = strategy
        self._per_account_limit = per_account_limit
        self._max_concurrent_browsers = max_concurrent_browsers
        self._global = global_semaphore
        self._in_flight: dict[str, int] = {}
        self._total_in_flight = 0
        self._capacity_changed = asyncio.Event()

    async def acquire(self, *, exclude: frozenset[str] = frozenset()) -> AccountSlot:
        waited_polls = 0
        while True:
            account = self._select_candidate(exclude)
            if account is not None:
                global_held = False
                if self._global is not None:
                    await self._global.acquire()
                    global_held = True
                self._in_flight[account.email] = self._in_flight.get(account.email, 0) + 1
                self._total_in_flight += 1
                _log.info(
                    "account_slot_acquired",
                    account_email=account.email,
                    in_flight=self._in_flight[account.email],
                )
                return AccountSlot(self, account.email, global_held=global_held)
            waited_polls += 1
            if waited_polls == 30:
                # ~30s with no candidate: log once so a stalled dispatch (job stuck "queued"
                # with no further logs) is diagnosable instead of silent.
                _log.warning(
                    "account_slot_wait_no_candidate",
                    total_in_flight=self._total_in_flight,
                    max_concurrent_browsers=self._max_concurrent_browsers,
                    excluded=sorted(exclude),
                    account_statuses={
                        a.email: a.status.value for a in self._accounts.list_accounts()
                    },
                )
            # Re-poll on a short timeout so cooldown expiry is noticed without a wakeup.
            try:
                await asyncio.wait_for(self._capacity_changed.wait(), timeout=1.0)
            except TimeoutError:
                pass

    def release(self, slot: AccountSlot, *, global_held: bool = False) -> None:
        current = self._in_flight.get(slot.email, 0)
        if current <= 1:
            self._in_flight.pop(slot.email, None)
        else:
            self._in_flight[slot.email] = current - 1
        self._total_in_flight = max(0, self._total_in_flight - 1)
        if global_held and self._global is not None:
            self._global.release()
        _log.info("account_slot_released", account_email=slot.email)
        self._notify()

    async def refresh(self) -> None:
        """Re-read `accounts.yaml` if it changed on disk (CLI/server coexistence, §6.7)."""
        if await self._accounts.reload_if_changed():
            self._notify()

    def _notify(self) -> None:
        """Wake current waiters without leaving future `wait()` calls returning instantly."""
        self._capacity_changed.set()
        self._capacity_changed.clear()

    def _select_candidate(self, exclude: frozenset[str]) -> Account | None:
        if self._total_in_flight >= self._max_concurrent_browsers:
            return None
        available = [
            account
            for account in self._accounts.get_available()
            if self._in_flight.get(account.email, 0) < self._per_account_limit
        ]
        if not available:
            return None
        candidates = [account for account in available if account.email not in exclude]
        if not candidates:
            # Every currently-available account has already been tried for this job (routine
            # with a single account). Retrying the same account beats blocking `acquire()`
            # forever — `job_max_attempts` still caps how many times this can happen.
            candidates = available
        return self._strategy.select(candidates)

    def snapshot(self) -> PoolStats:
        return PoolStats(
            total_slots=self._max_concurrent_browsers,
            free_slots=max(0, self._max_concurrent_browsers - self._total_in_flight),
            total_in_flight=self._total_in_flight,
            per_account_limit=self._per_account_limit,
            per_account_in_flight=dict(self._in_flight),
        )
