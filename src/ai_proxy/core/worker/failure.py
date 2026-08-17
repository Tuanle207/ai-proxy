"""Default failure classification and account-effect policy.

Lifted verbatim from `worker/runner.py` (Phase 2.3). Providers may override this table through
`ProviderAdapter.classify_failure`; the core dispatch loop falls back to `default_classify_failure`
when an adapter returns `None`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError

from ai_proxy.core.errors import (
    AuthError,
    GenerationTimeoutError,
    QuotaExceededError,
    SelectorNotFoundError,
)


class AccountEffect(enum.StrEnum):
    NONE = "none"
    NEEDS_LOGIN = "needs_login"
    COOLDOWN = "cooldown"
    QUOTA_COOLDOWN = "quota_cooldown"


@dataclass(frozen=True)
class FailurePolicy:
    retryable: bool
    error_code: str
    account_effect: AccountEffect


def default_classify_failure(exc: BaseException) -> FailurePolicy:
    """Map a job exception to its outcome + account effect (§4.7)."""
    if isinstance(exc, AuthError):
        return FailurePolicy(True, "auth_error", AccountEffect.NEEDS_LOGIN)
    if isinstance(exc, QuotaExceededError):
        return FailurePolicy(True, "quota_exceeded", AccountEffect.QUOTA_COOLDOWN)
    if isinstance(exc, GenerationTimeoutError):
        return FailurePolicy(True, "timeout", AccountEffect.COOLDOWN)
    if isinstance(exc, SelectorNotFoundError):
        return FailurePolicy(False, "selector_not_found", AccountEffect.NONE)
    if isinstance(exc, PlaywrightError):
        return FailurePolicy(True, "browser_error", AccountEffect.COOLDOWN)
    return FailurePolicy(True, "unknown", AccountEffect.COOLDOWN)
