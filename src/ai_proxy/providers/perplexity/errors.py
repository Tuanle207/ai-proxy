"""Perplexity-specific errors.

Reconnaissance (plan P3.1) determines the actual error/rate-limit/login banners to detect;
until then the page-driving code raises `PerplexityError` and the adapter maps it through
`classify_failure` (plan P6.2).
"""

from __future__ import annotations

from ai_proxy.core.errors import AIProxyError


class PerplexityError(AIProxyError):
    """Base for Perplexity site-driving failures."""
