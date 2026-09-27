"""`CamoufoxBackend` warm-session claim tests (no real browser launched)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ai_web_provider.core.browser.camoufox_backend import CamoufoxBackend
from ai_web_provider.core.paths import DataPaths


def _backend(tmp_path: Path, *, max_tabs: int) -> CamoufoxBackend:
    return CamoufoxBackend(
        DataPaths(tmp_path), "google_flow", idle_ttl_seconds=600.0, max_tabs_per_session=max_tabs
    )


def _session(*, headless: bool = True, active_pages: int = 0) -> SimpleNamespace:
    browser = SimpleNamespace(is_connected=lambda: True)
    return SimpleNamespace(browser=browser, headless=headless, active_pages=active_pages)


def test_claim_session_reuses_session_with_free_tab(tmp_path: Path) -> None:
    backend = _backend(tmp_path, max_tabs=2)
    session = _session(active_pages=1)
    backend._warm["a@example.com"] = [session]

    assert backend._claim_session("a@example.com", headless=True) is session


def test_claim_session_returns_none_when_tabs_saturated(tmp_path: Path) -> None:
    backend = _backend(tmp_path, max_tabs=2)
    backend._warm["a@example.com"] = [_session(active_pages=2)]

    assert backend._claim_session("a@example.com", headless=True) is None


def test_claim_session_skips_mismatched_headless(tmp_path: Path) -> None:
    backend = _backend(tmp_path, max_tabs=2)
    backend._warm["a@example.com"] = [_session(headless=False)]

    assert backend._claim_session("a@example.com", headless=True) is None


def test_claim_session_drops_disconnected_sessions(tmp_path: Path) -> None:
    backend = _backend(tmp_path, max_tabs=1)
    dead = _session(active_pages=0)
    dead.browser = SimpleNamespace(is_connected=lambda: False)
    backend._warm["a@example.com"] = [dead]

    assert backend._claim_session("a@example.com", headless=True) is None
    assert backend._warm["a@example.com"] == []
