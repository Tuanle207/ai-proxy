"""AuthHandler protocol: provider-owned login/session detection."""

from __future__ import annotations

from typing import Protocol

from ai_proxy.core.provider.session import ProviderSession


class AuthHandler(Protocol):
    """A provider's authentication surface.

    Flow's OAuth detection (an `accounts.google.com` redirect probe) is not reusable across
    providers, so login/session logic lives behind this interface.
    """

    @property
    def login_url(self) -> str: ...

    async def is_logged_in(self, session: ProviderSession) -> bool: ...

    async def interactive_login(self, session: ProviderSession) -> bool: ...

    async def probe_session(self, session: ProviderSession) -> bool: ...
