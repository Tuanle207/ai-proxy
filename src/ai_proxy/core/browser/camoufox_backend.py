"""Camoufox-backed implementation of `BrowserBackend`."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext

from ai_proxy.core.browser.proxy import validate_proxy_url
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import Account
from ai_proxy.core.paths import DataPaths

_log = get_logger()


def build_launch_options(account: Account, *, headless: bool) -> dict[str, Any]:
    """Build Camoufox launch options for `account` (per-account proxy, humanized cursor)."""
    options: dict[str, Any] = {"headless": headless, "humanize": True}
    if account.proxy:
        options["proxy"] = {"server": validate_proxy_url(account.proxy)}
        options["geoip"] = True
    return options


class _WarmSession:
    """A live Camoufox browser + context kept around for reuse between jobs.

    By default a session serves at most one job at a time — two simultaneous tabs against the
    same logged-in session confused Perplexity's SPA badly enough to time out navigation/composer
    waits that are otherwise reliable (verified live 2026-08-18). Providers may opt into tab
    sharing via `max_tabs_per_session > 1`, in which case up to that many concurrent pages run
    inside one browser (see `CamoufoxBackend`). A session records whether it is headed so a
    headless job never grabs a headed window (or vice-versa).
    """

    def __init__(
        self,
        account: Account,
        cm: AsyncCamoufox,
        browser: Browser,
        context: BrowserContext,
        *,
        headless: bool,
    ):
        self.account = account
        self.cm = cm
        self.browser = browser
        self.context = context
        self.headless = headless
        self.active_pages = 0
        self.evict_task: asyncio.Task[None] | None = None


class CamoufoxBackend:
    """Launches one Camoufox browser per account and persists its `storage_state.json`.

    Session cookies are provider-scoped (blocker 1.2.2): the same email on two providers
    must never overwrite each other's storage state, so the backend is constructed per
    provider and writes under `providers/<provider>/sessions/<email>/`.

    When `idle_ttl_seconds > 0`, a browser+context is kept warm per account (headed or headless,
    whichever the job requests) and reused across consecutive jobs instead of relaunching
    Camoufox every time — full browser startup (~10s+) otherwise dominates job latency. By
    default concurrent jobs for the same account each get their own warm session (never sharing
    one — see `_WarmSession`); set `max_tabs_per_session > 1` to instead serve up to that many
    concurrent pages from a single browser, one tab per job. Each session is closed after
    `idle_ttl_seconds` with no active page, or immediately via `close_all()` (service shutdown).
    Interactive logins pass `reuse=False` and always get a fresh, one-off browser regardless of
    this setting.
    """

    def __init__(
        self,
        paths: DataPaths,
        provider: str,
        *,
        idle_ttl_seconds: float = 0.0,
        max_tabs_per_session: int = 1,
    ):
        self._paths = paths
        self.provider = provider
        self._idle_ttl_seconds = idle_ttl_seconds
        self._max_tabs_per_session = max(1, max_tabs_per_session)
        self._write_locks: dict[str, asyncio.Lock] = {}
        self._warm: dict[str, list[_WarmSession]] = {}
        self._warm_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, email: str) -> asyncio.Lock:
        email = email.strip().lower()
        lock = self._write_locks.get(email)
        if lock is None:
            lock = asyncio.Lock()
            self._write_locks[email] = lock
        return lock

    def _warm_lock_for(self, email: str) -> asyncio.Lock:
        email = email.strip().lower()
        lock = self._warm_locks.get(email)
        if lock is None:
            lock = asyncio.Lock()
            self._warm_locks[email] = lock
        return lock

    async def _persist_storage_state(self, account: Account, context: BrowserContext) -> None:
        """Serialize `storage_state.json` under a per-account lock, atomically (§1.2.4).

        Two contexts for the same account must never write the session file at once; a torn
        write surfaces later as a spurious `needs_login`. Writing to a temp file then
        `os.replace` mirrors `accounts/store.py`.
        """
        async with self._lock_for(account.email):
            self._paths.ensure_session_dir(self.provider, account.email)
            state_file = self._paths.storage_state_file(self.provider, account.email)
            tmp_file = state_file.with_name(state_file.name + ".tmp")
            await context.storage_state(path=str(tmp_file))
            os.replace(tmp_file, state_file)

    @asynccontextmanager
    async def browser_context(
        self, account: Account, *, headless: bool = True, reuse: bool = True
    ) -> AsyncIterator[BrowserContext]:
        if reuse and self._idle_ttl_seconds > 0:
            async with self._pooled_context(account, headless=headless) as context:
                yield context
            return
        async with self._fresh_context(account, headless=headless) as context:
            yield context

    @asynccontextmanager
    async def _fresh_context(
        self, account: Account, *, headless: bool
    ) -> AsyncIterator[BrowserContext]:
        options = build_launch_options(account, headless=headless)
        state_file = self._paths.storage_state_file(self.provider, account.email)
        async with AsyncCamoufox(**options) as raw_browser:
            # persistent_context is not used above, so this is always a Browser.
            browser = cast(Browser, raw_browser)
            context_kwargs: dict[str, Any] = {}
            if state_file.is_file():
                context_kwargs["storage_state"] = str(state_file)
            context = await browser.new_context(**context_kwargs)
            try:
                yield context
            finally:
                await self._persist_storage_state(account, context)
                await context.close()

    @asynccontextmanager
    async def _pooled_context(
        self, account: Account, *, headless: bool
    ) -> AsyncIterator[BrowserContext]:
        email = account.email.strip().lower()
        lock = self._warm_lock_for(email)
        async with lock:
            session = self._claim_session(email, headless=headless)
            if session is None:
                session = await self._start_warm_session(account, headless=headless)
                self._warm.setdefault(email, []).append(session)
            session.active_pages += 1
            if session.evict_task is not None:
                session.evict_task.cancel()
                session.evict_task = None
        try:
            yield session.context
        finally:
            async with lock:
                session.active_pages -= 1
                if session.active_pages == 0:
                    session.evict_task = asyncio.create_task(
                        self._evict_after_idle(email, session)
                    )

    def _claim_session(self, email: str, *, headless: bool) -> _WarmSession | None:
        """Return a live, matching-`headless` session with a free tab slot, dropping dead ones."""
        sessions = self._warm.get(email, [])
        alive = [s for s in sessions if s.browser.is_connected()]
        if len(alive) != len(sessions):
            _log.warning(
                "browser_warm_session_disconnected", provider=self.provider, account_email=email
            )
            self._warm[email] = alive
        for session in alive:
            if session.headless == headless and session.active_pages < self._max_tabs_per_session:
                return session
        return None

    async def _start_warm_session(self, account: Account, *, headless: bool) -> _WarmSession:
        options = build_launch_options(account, headless=headless)
        state_file = self._paths.storage_state_file(self.provider, account.email)
        cm = AsyncCamoufox(**options)
        browser = cast(Browser, await cm.__aenter__())
        context_kwargs: dict[str, Any] = {}
        if state_file.is_file():
            context_kwargs["storage_state"] = str(state_file)
        context = await browser.new_context(**context_kwargs)
        _log.info(
            "browser_warm_session_started",
            provider=self.provider,
            account_email=account.email,
            headless=headless,
        )
        return _WarmSession(account, cm, browser, context, headless=headless)

    async def _evict_after_idle(self, email: str, session: _WarmSession) -> None:
        try:
            await asyncio.sleep(self._idle_ttl_seconds)
        except asyncio.CancelledError:
            return
        lock = self._warm_lock_for(email)
        async with lock:
            sessions = self._warm.get(email, [])
            if session.active_pages > 0 or session not in sessions:
                return
            sessions.remove(session)
            if not sessions:
                self._warm.pop(email, None)
        await self._close_warm(session)

    async def _close_warm(self, session: _WarmSession) -> None:
        try:
            await self._persist_storage_state(session.account, session.context)
            await session.context.close()
            await session.cm.__aexit__(None, None, None)
        except Exception:
            _log.warning(
                "browser_warm_session_close_failed",
                provider=self.provider,
                account_email=session.account.email,
            )
        else:
            _log.info(
                "browser_warm_session_closed",
                provider=self.provider,
                account_email=session.account.email,
            )

    async def close_all(self) -> None:
        """Close every warm session immediately, regardless of idle state (service shutdown)."""
        for email in list(self._warm):
            lock = self._warm_lock_for(email)
            async with lock:
                sessions = self._warm.pop(email, [])
            for session in sessions:
                if session.evict_task is not None:
                    session.evict_task.cancel()
                await self._close_warm(session)

    async def close_account_sessions(self, email: str) -> None:
        """Close every warm session for `email` immediately (e.g. its session expired).

        Dropping the dead-cookie sessions now means a later re-login writes fresh storage state
        and the next job gets a clean browser instead of re-claiming a stale, logged-out session.
        """
        email = email.strip().lower()
        lock = self._warm_lock_for(email)
        async with lock:
            sessions = self._warm.pop(email, [])
        for session in sessions:
            if session.evict_task is not None:
                session.evict_task.cancel()
            await self._close_warm(session)
