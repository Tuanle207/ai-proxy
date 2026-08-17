"""Exception hierarchy shared across the package."""

from __future__ import annotations


class AIProxyError(Exception):
    """Base class for all ai_proxy errors."""


class AccountAlreadyExistsError(AIProxyError):
    """Raised when adding an account whose email is already registered."""


class AccountNotFoundError(AIProxyError):
    """Raised when an operation references an unknown account email."""


class NoAvailableAccountError(AIProxyError):
    """Raised when no account is available to service a job."""


class AuthError(AIProxyError):
    """Raised when a job fails due to an authentication/session problem."""


class GenerationTimeoutError(AIProxyError):
    """Raised when a generation job does not complete within its timeout."""


class QuotaExceededError(AIProxyError):
    """Raised when Flow reports the account is out of generation quota/credits."""


class SelectorNotFoundError(AIProxyError):
    """Raised when an expected page element cannot be located (likely a UI change)."""
