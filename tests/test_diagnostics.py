import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_web_provider.core.diagnostics import PageEventRecorder, prune_failures


def _capture(root: Path, day: str, name: str, *, size: int, age_days: float) -> Path:
    capture = root / day / name
    capture.mkdir(parents=True)
    file = capture / "screenshot.png"
    file.write_bytes(b"x" * size)
    mtime = (datetime.now(UTC) - timedelta(days=age_days)).timestamp()
    os.utime(file, (mtime, mtime))
    return capture


def test_prune_removes_captures_older_than_max_age(tmp_path: Path) -> None:
    old = _capture(tmp_path, "2026-09-01", "old", size=10, age_days=10)
    fresh = _capture(tmp_path, "2026-09-28", "fresh", size=10, age_days=0)
    assert prune_failures(tmp_path, max_age_days=7, max_total_mb=500) == 1
    assert not old.exists() and not old.parent.exists()
    assert fresh.exists()


def test_prune_removes_oldest_until_under_size_budget(tmp_path: Path) -> None:
    mb = 1024 * 1024
    oldest = _capture(tmp_path, "d", "oldest", size=mb, age_days=2)
    middle = _capture(tmp_path, "d", "middle", size=mb, age_days=1)
    newest = _capture(tmp_path, "d", "newest", size=mb, age_days=0)
    assert prune_failures(tmp_path, max_age_days=7, max_total_mb=2) == 1
    assert not oldest.exists() and middle.exists() and newest.exists()


def test_prune_missing_dir_is_noop(tmp_path: Path) -> None:
    assert prune_failures(tmp_path / "missing", max_age_days=7, max_total_mb=1) == 0


def test_recorder_keeps_failed_responses_without_query_strings() -> None:
    class _Page:
        def __init__(self) -> None:
            self.handlers: dict = {}

        def on(self, event, handler) -> None:
            self.handlers[event] = handler

    class _Req:
        method = "POST"

    class _Resp:
        def __init__(self, status: int) -> None:
            self.status = status
            self.url = "https://x.test/api/generate?key=secret"
            self.request = _Req()

    page = _Page()
    recorder = PageEventRecorder().attach(page)
    page.handlers["response"](_Resp(200))
    page.handlers["response"](_Resp(429))
    assert recorder.snapshot()["failed_requests"] == [
        {"url": "https://x.test/api/generate", "method": "POST", "status": 429}
    ]
