"""Failure diagnostics: step tracking, page event buffers, and on-failure page captures.

Captures are always on but only written when an attempt fails; successful attempts only pay for
a few in-memory ring buffers. Everything here is best-effort — a capture problem is logged and
never replaces the job's original exception.

Layout: `<data_dir>/failures/<YYYY-MM-DD>/<capture_id>/{screenshot.png,page.html,meta.json}`.
The directory holds screenshots of logged-in pages, so it is created 0700; no cookies, storage
state, response bodies or prompt text are ever written.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import stat
import time
import traceback
from collections import deque
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from ai_web_provider.core.logging_setup import get_logger

_log = get_logger()

_CAPTURE_TIMEOUT_SECONDS = 10.0
_SCREENSHOT_TIMEOUT_MS = 5000
_MAX_CONSOLE = 50
_MAX_PAGE_ERRORS = 20
_MAX_FAILED_REQUESTS = 20
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")

# (step, started_at monotonic) marks for the current attempt; reset by `start_attempt`.
_step_marks: ContextVar[list[tuple[str, float]] | None] = ContextVar("_step_marks", default=None)


# --- step tracking ---------------------------------------------------------------------------


def start_attempt() -> None:
    """Reset step tracking for a new executor attempt (in the current task context)."""
    _step_marks.set([])
    structlog.contextvars.unbind_contextvars("step", "workspace_ref")


def mark_step(step: str, **fields: Any) -> str:
    """Record that `step` started: binds it (plus `fields`) into the log context and times it.

    Returns `step` so adapters can keep their local `step` variable: `step = mark_step("x")`.
    """
    marks = _step_marks.get()
    if marks is not None:
        marks.append((step, time.monotonic()))
    structlog.contextvars.bind_contextvars(step=step, **fields)
    return step


def current_step() -> str | None:
    value = structlog.contextvars.get_contextvars().get("step")
    return value if isinstance(value, str) else None


def step_timings(now: float | None = None) -> list[dict[str, Any]]:
    """Durations of the steps marked in this attempt; the last one runs until `now`."""
    marks = _step_marks.get() or []
    now = time.monotonic() if now is None else now
    timings = []
    for index, (step, started) in enumerate(marks):
        ended = marks[index + 1][1] if index + 1 < len(marks) else now
        timings.append({"step": step, "elapsed_ms": round((ended - started) * 1000)})
    return timings


# --- page event buffers ----------------------------------------------------------------------


def _strip_query(url: str) -> str:
    # Query strings can carry tokens/signatures; keep only scheme://host/path.
    return url.split("?", 1)[0].split("#", 1)[0]


class PageEventRecorder:
    """Keeps the last few console messages, page errors and failed requests of a page."""

    def __init__(self) -> None:
        self.console: deque[dict[str, str]] = deque(maxlen=_MAX_CONSOLE)
        self.page_errors: deque[str] = deque(maxlen=_MAX_PAGE_ERRORS)
        self.failed_requests: deque[dict[str, Any]] = deque(maxlen=_MAX_FAILED_REQUESTS)

    def attach(self, page: Any) -> PageEventRecorder:
        try:
            page.on("console", self._on_console)
            page.on("pageerror", self._on_page_error)
            page.on("requestfailed", self._on_request_failed)
            page.on("response", self._on_response)
        except Exception:
            _log.warning("diagnostics_page_listeners_attach_failed", exc_info=True)
        return self

    def _on_console(self, message: Any) -> None:
        try:
            self.console.append({"type": str(message.type), "text": str(message.text)[:2000]})
        except Exception:
            pass

    def _on_page_error(self, error: Any) -> None:
        self.page_errors.append(str(error)[:2000])

    def _on_request_failed(self, request: Any) -> None:
        try:
            self.failed_requests.append(
                {
                    "url": _strip_query(request.url),
                    "method": request.method,
                    "failure": str(request.failure),
                }
            )
        except Exception:
            pass

    def _on_response(self, response: Any) -> None:
        try:
            if response.status >= 400:
                self.failed_requests.append(
                    {
                        "url": _strip_query(response.url),
                        "method": response.request.method,
                        "status": response.status,
                    }
                )
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "console": list(self.console),
            "page_errors": list(self.page_errors),
            "failed_requests": list(self.failed_requests),
        }


# --- capture ---------------------------------------------------------------------------------


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


def new_capture_id(request_id: str, attempt: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now:%H%M%S}_{_SAFE_ID.sub('_', request_id)[:64]}_a{attempt}"


def capture_dir(failures_dir: Path, capture_id: str, now: datetime | None = None) -> Path:
    now = now or datetime.now(UTC)
    return failures_dir / f"{now:%Y-%m-%d}" / capture_id


async def capture_failure(
    page: Any,
    *,
    failures_dir: Path,
    error: BaseException,
    meta: dict[str, Any],
    recorder: PageEventRecorder | None = None,
) -> str | None:
    """Write screenshot, HTML and metadata for a failed attempt. Returns the `capture_id`.

    Never raises: the whole capture is time-bounded and each part is independent.
    """
    now = datetime.now(UTC)
    request_id = str(meta.get("request_id") or "unknown")
    capture_id = new_capture_id(request_id, int(meta.get("attempt") or 0), now)
    target = capture_dir(failures_dir, capture_id, now)
    try:
        await asyncio.wait_for(
            _write_capture(page, target, error=error, meta=meta, recorder=recorder, now=now),
            timeout=_CAPTURE_TIMEOUT_SECONDS,
        )
    except Exception:
        _log.warning("failure_capture_failed", capture_id=capture_id, exc_info=True)
        if not target.exists():
            return None
    return capture_id


async def _write_capture(
    page: Any,
    target: Path,
    *,
    error: BaseException,
    meta: dict[str, Any],
    recorder: PageEventRecorder | None,
    now: datetime,
) -> None:
    await asyncio.to_thread(_private_dir, target.parent.parent)
    await asyncio.to_thread(_private_dir, target.parent)
    await asyncio.to_thread(_private_dir, target)
    problems: list[str] = []

    page_url = None
    viewport = None
    if page is not None:
        try:
            page_url = page.url
            viewport = page.viewport_size
        except Exception as exc:
            problems.append(f"page_info: {exc!r}")
        try:
            await page.screenshot(
                path=str(target / "screenshot.png"), full_page=True, timeout=_SCREENSHOT_TIMEOUT_MS
            )
        except Exception as exc:
            problems.append(f"screenshot: {exc!r}")
        try:
            html = await page.content()
            await asyncio.to_thread((target / "page.html").write_text, html, "utf-8")
        except Exception as exc:
            problems.append(f"html: {exc!r}")

    document = {
        **meta,
        "captured_at": now.isoformat(),
        "page_url": page_url,
        "viewport": viewport,
        "error_type": type(error).__name__,
        "error_message": str(error)[:4000],
        # Plain traceback: no frame locals (they would dump settings/emails/project ids).
        "traceback": "".join(traceback.format_exception(error)),
        "step_timings": step_timings(),
        **(recorder.snapshot() if recorder is not None else {}),
        "capture_problems": problems,
    }
    payload = json.dumps(document, indent=2, default=str, ensure_ascii=False)
    await asyncio.to_thread((target / "meta.json").write_text, payload, "utf-8")


# --- retention -------------------------------------------------------------------------------


def prune_failures(
    failures_dir: Path, *, max_age_days: int, max_total_mb: int, now: datetime | None = None
) -> int:
    """Delete captures older than `max_age_days`, then oldest-first until under `max_total_mb`.

    Returns the number of capture directories removed.
    """
    if not failures_dir.is_dir():
        return 0
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=max_age_days)).timestamp()
    captures: list[tuple[float, int, Path]] = []
    for day_dir in failures_dir.iterdir():
        if not day_dir.is_dir():
            continue
        for capture in day_dir.iterdir():
            if not capture.is_dir():
                continue
            files = [f for f in capture.rglob("*") if f.is_file()]
            mtime = max((f.stat().st_mtime for f in files), default=capture.stat().st_mtime)
            size = sum(f.stat().st_size for f in files)
            captures.append((mtime, size, capture))

    removed = 0
    captures.sort(key=lambda item: item[0])
    budget = max_total_mb * 1024 * 1024
    total = sum(size for _, size, _ in captures)
    for mtime, size, capture in captures:
        if mtime >= cutoff and total <= budget:
            break
        shutil.rmtree(capture, ignore_errors=True)
        total -= size
        removed += 1

    for day_dir in failures_dir.iterdir():
        if day_dir.is_dir() and not any(day_dir.iterdir()):
            day_dir.rmdir()
    return removed
