"""Diagnostics for the browser layer (used by `flow doctor`)."""

from __future__ import annotations


def camoufox_status() -> tuple[bool, str]:
    """Return (installed, message) describing whether the Camoufox browser binary is present."""
    try:
        from camoufox.pkgman import installed_verstr

        return True, installed_verstr()
    except Exception as exc:  # camoufox raises CamoufoxNotInstalled or similar
        return False, str(exc)
