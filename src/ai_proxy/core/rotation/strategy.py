"""Account selection strategies for spreading jobs across the pool."""

from __future__ import annotations

from typing import Protocol

from ai_proxy.core.models import Account


class RotationStrategy(Protocol):
    """Chooses one account from a non-empty list of currently available accounts."""

    def select(self, accounts: list[Account]) -> Account: ...


class RoundRobinStrategy:
    """Cycles through accounts in order, remembering the last one picked."""

    def __init__(self) -> None:
        self._last_email: str | None = None

    def select(self, accounts: list[Account]) -> Account:
        if not accounts:
            raise ValueError("no accounts available to select from")
        if self._last_email is not None:
            emails = [a.email for a in accounts]
            if self._last_email in emails:
                next_index = (emails.index(self._last_email) + 1) % len(accounts)
                chosen = accounts[next_index]
                self._last_email = chosen.email
                return chosen
        chosen = accounts[0]
        self._last_email = chosen.email
        return chosen


class LeastLoadedStrategy:
    """Post-MVP: picks the account with the fewest total recorded jobs."""

    def select(self, accounts: list[Account]) -> Account:
        if not accounts:
            raise ValueError("no accounts available to select from")
        return min(accounts, key=lambda a: a.success_count + a.fail_count)
