"""Structured logging configuration (structlog)."""

from __future__ import annotations

import importlib.util
import logging
import sys

import structlog


def configure_logging(*, level: str = "INFO", json: bool = False) -> None:
    """Configure structlog + stdlib logging. Call once at process startup (CLI/library init)."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    renderer = structlog.processors.JSONRenderer() if json else _console_renderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            *([structlog.processors.format_exc_info] if json else []),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _console_renderer() -> structlog.dev.ConsoleRenderer:
    formatter: structlog.typing.ExceptionRenderer
    # Never render frame locals: they dump settings (account emails, project ids) into every
    # traceback and bury the actual error.
    if importlib.util.find_spec("rich") is not None:
        formatter = structlog.dev.RichTracebackFormatter(show_locals=False)
    else:
        formatter = structlog.dev.plain_traceback
    return structlog.dev.ConsoleRenderer(exception_formatter=formatter)


def get_logger(**initial_values: object) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(**initial_values)  # type: ignore[no-any-return]
