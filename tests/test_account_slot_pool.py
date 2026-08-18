"""`AccountSlotPool` must never block forever when every available account has already been
tried for a job (routine with a single configured account) — see `_select_candidate`."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.models import AccountStatus
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.rotation.pool import AccountSlotPool
from ai_proxy.core.rotation.strategy import RoundRobinStrategy


def _pool(tmp_path: Path, *emails: str) -> AccountSlotPool:
    accounts = AccountManager(DataPaths(tmp_path), "perplexity")
    for email in emails:
        accounts.add(email)
        accounts.set_status(email, AccountStatus.ACTIVE)
    return AccountSlotPool(
        accounts, RoundRobinStrategy(), per_account_limit=2, max_concurrent_browsers=4
    )


def test_acquire_falls_back_to_tried_account_when_it_is_the_only_one(tmp_path: Path) -> None:
    pool = _pool(tmp_path, "solo@example.com")

    slot = asyncio.run(pool.acquire(exclude=frozenset({"solo@example.com"})))

    assert slot.email == "solo@example.com"


def test_acquire_prefers_untried_account_when_available(tmp_path: Path) -> None:
    pool = _pool(tmp_path, "tried@example.com", "fresh@example.com")

    slot = asyncio.run(pool.acquire(exclude=frozenset({"tried@example.com"})))

    assert slot.email == "fresh@example.com"
