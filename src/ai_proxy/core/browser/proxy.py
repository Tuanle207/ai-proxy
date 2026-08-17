"""Validation helpers for per-account proxy configuration."""

from __future__ import annotations

from urllib.parse import urlparse

_SUPPORTED_SCHEMES = {"http", "https", "socks4", "socks5"}


def validate_proxy_url(proxy: str) -> str:
    """Validate a proxy URL of the form `scheme://[user:pass@]host:port`.

    Raises `ValueError` if the scheme, host, or port is missing/unsupported.
    """
    parsed = urlparse(proxy)
    if parsed.scheme not in _SUPPORTED_SCHEMES:
        raise ValueError(
            f"unsupported proxy scheme {parsed.scheme!r} in {proxy!r}; "
            f"expected one of {sorted(_SUPPORTED_SCHEMES)}"
        )
    if not parsed.hostname:
        raise ValueError(f"proxy URL is missing a host: {proxy!r}")
    if not parsed.port:
        raise ValueError(f"proxy URL is missing a port: {proxy!r}")
    return proxy
