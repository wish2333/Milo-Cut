"""Loguru configuration with file rotation and frontend sink.

Migrated from ff-intelligent-neo core/logging.py, adapted for Milo-Cut.
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from core.paths import get_log_dir

_frontend_sink: Callable[[str], None] | None = None


def _sink_fn(message: Any) -> None:
    """Forward WARNING+ messages to the frontend via bridge emit."""
    if _frontend_sink is not None and message.record["level"].no >= 30:
        _frontend_sink(str(message).rstrip())


def setup_frontend_sink(emit_fn: Callable[[str, Any], None]) -> None:
    """Register a frontend sink that forwards warnings to the UI."""
    global _frontend_sink

    def forward(text: str) -> None:
        emit_fn("log_line", {"level": "warning", "message": text})

    _frontend_sink = forward


def setup_logging() -> None:
    """Configure loguru with console, file, and optional frontend sinks."""
    logger.remove()
    logger.add(
        lambda m: None,
        level="DEBUG",
        colorize=False,
    )
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_dir / "app_{time:YYYY-MM-DD}.log"),
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )
    logger.add(
        _sink_fn,
        level="WARNING",
    )


def get_logger() -> Any:
    """Return the configured loguru logger."""
    return logger
