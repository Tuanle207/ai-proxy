"""Exception hierarchy shared across the package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_web_provider.core.models import AttemptRecord


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

    def __init__(self, message: str, model: str | None = None):
        super().__init__(message)
        self.model = model


class SelectorNotFoundError(AIProxyError):
    """Raised when an expected page element cannot be located (likely a UI change)."""


class TaskFailedError(AIProxyError):
    """Raised by the executor once a task has failed on every attempt.

    Wraps the last attempt's exception (`last_error`, also chained as `__cause__`) and carries
    the per-attempt history so callers can surface `request_id` / `capture_id`s for tracing.
    """

    def __init__(
        self,
        *,
        request_id: str,
        attempts: list[AttemptRecord],
        last_error: BaseException,
    ):
        super().__init__(str(last_error))
        self.request_id = request_id
        self.attempts = attempts
        self.last_error = last_error

    @property
    def error_code(self) -> str | None:
        return self.attempts[-1].error_code if self.attempts else None

    @property
    def capture_ids(self) -> list[str]:
        return [a.capture_id for a in self.attempts if a.capture_id]
