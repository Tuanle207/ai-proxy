"""`AccountSlotPool` must never block forever when every available account has already been
tried for a job (routine with a single configured account) — see `_select_candidate`."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ai_web_provider.core.accounts.manager import AccountManager
from ai_web_provider.core.models import AccountStatus
from ai_web_provider.core.paths import DataPaths
from ai_web_provider.core.rotation.pool import AccountSlotPool
from ai_web_provider.core.rotation.strategy import RoundRobinStrategy


def _pool(tmp_path: Path, *emails: str) -> AccountSlotPool:
    accounts = AccountManager(DataPaths(tmp_path), "perplexity")
    for email in emails:
        accounts.add(email)
        accounts.set_status(email, AccountStatus.ACTIVE)
    return AccountSlotPool(
        accounts, RoundRobinStrategy(), per_account_limit=2, max_concurrent_jobs=4
    )


def test_acquire_falls_back_to_tried_account_when_it_is_the_only_one(tmp_path: Path) -> None:
    pool = _pool(tmp_path, "solo@example.com")

    slot = asyncio.run(pool.acquire(exclude=frozenset({"solo@example.com"})))

    assert slot.email == "solo@example.com"


def test_acquire_prefers_untried_account_when_available(tmp_path: Path) -> None:
    pool = _pool(tmp_path, "tried@example.com", "fresh@example.com")

    slot = asyncio.run(pool.acquire(exclude=frozenset({"tried@example.com"})))

    assert slot.email == "fresh@example.com"


def test_try_acquire_returns_slot_when_available(tmp_path: Path) -> None:
    async def main() -> None:
        pool = _pool(tmp_path, "solo@example.com")

        slot = await pool.try_acquire()

        assert slot is not None and slot.email == "solo@example.com"
        slot.release()

    asyncio.run(main())


def test_try_acquire_returns_none_when_saturated(tmp_path: Path) -> None:
    async def main() -> None:
        pool = _pool(tmp_path, "solo@example.com")  # per_account_limit=2
        first = await pool.acquire()
        second = await pool.acquire()

        assert await pool.try_acquire() is None

        first.release()
        second.release()
        assert await pool.try_acquire() is not None

    asyncio.run(main())


def test_project_limits_cap_accounts_individually(tmp_path: Path) -> None:
    async def main() -> None:
        accounts = AccountManager(DataPaths(tmp_path), "google_flow")
        for email in ("one@example.com", "two@example.com"):
            accounts.add(email)
            accounts.set_status(email, AccountStatus.ACTIVE)
        pool = AccountSlotPool(
            accounts,
            RoundRobinStrategy(),
            per_account_limit=2,
            per_account_limits={"one@example.com": 1, "two@example.com": 2},
            max_concurrent_jobs=4,
        )

        first = await pool.acquire()
        second = await pool.acquire()
        third = await pool.acquire()
        slots = (first, second, third)
        assert {slot.email for slot in slots} == {"one@example.com", "two@example.com"}
        assert sum(slot.email == "one@example.com" for slot in slots) == 1
        assert sum(slot.email == "two@example.com" for slot in slots) == 2

    asyncio.run(main())
