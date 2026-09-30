"""Diagnostics for the ungoogled-chromium executable."""

from __future__ import annotations


def ungoogled_chromium_status(binary: str) -> tuple[bool, str]:
    """Return whether the consumer-supplied ungoogled-chromium executable is present."""
    from pathlib import Path

    path = Path(binary).expanduser()
    if path.is_file():
        return True, str(path.resolve())
    return False, f"ungoogled-chromium executable not found: {path}"
