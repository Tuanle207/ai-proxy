"""Provider registry: register/resolve providers by stable name."""

from __future__ import annotations

from ai_proxy.core.errors import AIProxyError
from ai_proxy.core.provider.spec import ProviderSpec

_ENTRY_POINT_GROUP = "ai_proxy.providers"

_REGISTRY: dict[str, ProviderSpec] = {}


class UnknownProviderError(AIProxyError):
    """Raised when a provider name is not registered."""


def register(spec: ProviderSpec) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"provider {spec.name!r} is already registered")
    _REGISTRY[spec.name] = spec


def get(name: str) -> ProviderSpec:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownProviderError(name) from None


def names() -> list[str]:
    return sorted(_REGISTRY)


def discover() -> None:
    """Import built-ins and load third-party providers via the ``ai_proxy.providers`` entry point.

    Built-ins live under `ai_proxy.providers.*` and self-register on import; third-party providers
    ship as separate distributions exposing the entry-point group.
    """
    import importlib.metadata

    import ai_proxy.providers  # noqa: F401  built-ins self-register on import

    eps = importlib.metadata.entry_points()
    for ep in eps.select(group=_ENTRY_POINT_GROUP):
        ep.load()
