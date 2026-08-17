"""AccountManager: registry CRUD, lifecycle, metrics, and availability filtering.

The synchronous methods remain the CLI/library API (byte-for-byte compatible). The `*_async`
variants are the server path: they serialize mutations through an `asyncio.Lock` and offload the
YAML write to `asyncio.to_thread`, so no worker task ever blocks the event loop on file I/O
(§1.2.2). The service constructs exactly one instance and shares it (see `ServiceContainer`).
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta

from ai_proxy.core.accounts.store import load_accounts, save_accounts
from ai_proxy.core.browser.proxy import validate_proxy_url
from ai_proxy.core.errors import AccountAlreadyExistsError, AccountNotFoundError
from ai_proxy.core.models import Account, AccountStatus
from ai_proxy.core.paths import DataPaths


class AccountManager:
    """Manages a provider's `accounts.yaml` registry and each account's session directory.

    Provider-scoped (blocker 1.2.1): status, cooldowns, and sessions are per-site facts, so
    each provider gets its own registry rooted at `data/providers/<provider>/`.
    """

    def __init__(self, paths: DataPaths, provider: str):
        self._paths = paths
        self.provider = provider
        self._paths.ensure()
        self._accounts: dict[str, Account] = load_accounts(self._paths.accounts_file(provider))
        self._loaded_mtime = self._accounts_mtime()
        self.last_loaded_at = datetime.now(UTC)
        self._write_lock = asyncio.Lock()

    def _accounts_mtime(self) -> float | None:
        try:
            return self._paths.accounts_file(self.provider).stat().st_mtime_ns
        except OSError:
            return None

    def _save(self) -> None:
        save_accounts(self._paths.accounts_file(self.provider), self._accounts)
        self._loaded_mtime = self._accounts_mtime()
        self.last_loaded_at = datetime.now(UTC)

    async def _save_locked(self) -> None:
        await asyncio.to_thread(
            save_accounts, self._paths.accounts_file(self.provider), self._accounts
        )
        self._loaded_mtime = self._accounts_mtime()
        self.last_loaded_at = datetime.now(UTC)

    def _get_or_raise(self, email: str) -> Account:
        email = email.strip().lower()
        try:
            return self._accounts[email]
        except KeyError:
            raise AccountNotFoundError(email) from None

    # --- in-memory mutations (no write) shared by the sync and async variants ---

    def _mutate_status(self, email: str, status: AccountStatus) -> Account:
        account = self._get_or_raise(email)
        account.status = status
        if status != AccountStatus.COOLDOWN:
            account.cooldown_until = None
        return account

    def _mutate_cooldown(self, email: str, duration: timedelta) -> Account:
        account = self._get_or_raise(email)
        account.status = AccountStatus.COOLDOWN
        account.cooldown_until = datetime.now(UTC) + duration
        return account

    def _mutate_success(self, email: str) -> Account:
        account = self._get_or_raise(email)
        account.success_count += 1
        account.last_used_at = datetime.now(UTC)
        return account

    def _mutate_failure(self, email: str) -> Account:
        account = self._get_or_raise(email)
        account.fail_count += 1
        account.last_used_at = datetime.now(UTC)
        return account

    # --- sync CRUD (CLI) ---

    def add(self, email: str, label: str | None = None, proxy: str | None = None) -> Account:
        """Register a new account with status `needs_login`. Rejects duplicates."""
        if proxy:
            validate_proxy_url(proxy)
        account = Account(email=email, label=label, proxy=proxy, status=AccountStatus.NEEDS_LOGIN)
        if account.email in self._accounts:
            raise AccountAlreadyExistsError(account.email)
        self._accounts[account.email] = account
        self._paths.ensure_session_dir(self.provider, account.email)
        self._save()
        return account

    def remove(self, email: str) -> None:
        """Delete an account entry and its entire session directory."""
        account = self._get_or_raise(email)
        del self._accounts[account.email]
        self._save()
        session_dir = self._paths.session_dir(self.provider, account.email)
        if session_dir.is_dir():
            shutil.rmtree(session_dir)

    def list_accounts(self) -> list[Account]:
        return list(self._accounts.values())

    def get(self, email: str) -> Account:
        return self._get_or_raise(email)

    def enable(self, email: str) -> Account:
        return self.set_status(email, AccountStatus.ACTIVE)

    def disable(self, email: str) -> Account:
        return self.set_status(email, AccountStatus.DISABLED)

    def set_status(self, email: str, status: AccountStatus) -> Account:
        account = self._mutate_status(email, status)
        self._save()
        return account

    def set_cooldown(self, email: str, duration: timedelta) -> Account:
        account = self._mutate_cooldown(email, duration)
        self._save()
        return account

    def record_success(self, email: str) -> Account:
        account = self._mutate_success(email)
        self._save()
        return account

    def record_failure(self, email: str) -> Account:
        account = self._mutate_failure(email)
        self._save()
        return account

    # --- async mutations (server) ---

    async def set_status_async(self, email: str, status: AccountStatus) -> Account:
        async with self._write_lock:
            account = self._mutate_status(email, status)
            await self._save_locked()
        return account

    async def set_cooldown_async(self, email: str, duration: timedelta) -> Account:
        async with self._write_lock:
            account = self._mutate_cooldown(email, duration)
            await self._save_locked()
        return account

    async def record_success_async(self, email: str) -> Account:
        async with self._write_lock:
            account = self._mutate_success(email)
            await self._save_locked()
        return account

    async def record_failure_async(self, email: str) -> Account:
        async with self._write_lock:
            account = self._mutate_failure(email)
            await self._save_locked()
        return account

    async def reload_if_changed(self) -> bool:
        """Reload `accounts.yaml` if its mtime changed since the last load (§6.7)."""
        mtime = self._accounts_mtime()
        if mtime is None or mtime == self._loaded_mtime:
            return False
        async with self._write_lock:
            if mtime == self._loaded_mtime:
                return False
            await asyncio.to_thread(self._reload)
        return True

    def _reload(self) -> None:
        self._accounts = load_accounts(self._paths.accounts_file(self.provider))
        self._loaded_mtime = self._accounts_mtime()
        self.last_loaded_at = datetime.now(UTC)

    def get_available(self, now: datetime | None = None) -> list[Account]:
        """Accounts that are neither disabled, needing login, nor in an active cooldown."""
        now = now or datetime.now(UTC)
        return [account for account in self._accounts.values() if account.is_available(now)]
