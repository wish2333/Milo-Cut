"""Bridge base class and @expose decorator."""

from __future__ import annotations

import functools
import json
import logging
import queue
import re
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_EVENT_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def expose(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a bridge method with try/except error handling.

    Exposed methods should return ``{"success": True, "data": ...}``.
    On unhandled exception, the decorator returns
    ``{"success": False, "error": "...", "code": "INTERNAL_ERROR"}``.
    In production mode (default), error details are hidden from the frontend.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            logger.exception("Unhandled bridge exception in %s", func.__name__)
            bridge = args[0] if args and isinstance(args[0], Bridge) else None
            if bridge is not None and bridge._debug:
                error_msg = str(exc)
            else:
                error_msg = "Internal error"
            return {"success": False, "error": error_msg, "code": "INTERNAL_ERROR"}

    return wrapper


class Bridge:
    """Base class for Python APIs exposed to the frontend.

    Subclass this and decorate public methods with ``@expose``.
    Use ``self._emit(event_name, data)`` to push events to the frontend.

    Thread safety:
        ``_emit`` can be called from any thread. Events are queued and
        flushed via a periodic JS timer calling ``tick()``.

    """

    def __init__(self, *, debug: bool = False) -> None:
        self._window = None
        self._debug = debug
        self._drop_lock = threading.Lock()
        self._dropped_paths: list[str] = []
        self._event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def _emit(self, event: str, data: Any = None) -> None:
        """Thread-safe: queue an event for main-thread delivery."""
        if not _EVENT_RE.fullmatch(event):
            raise ValueError(f"Invalid event name: {event!r}")
        self._event_queue.put((event, data))

    # v3.0.0 M4: batch dispatch budget. Events are drained in chunks whose
    # serialized payload stays under this size (a single oversized event is
    # sent alone). Order within/between batches is preserved.
    _MAX_BATCH_BYTES = 512 * 1024

    def _flush_events(self) -> None:
        """Drain the event queue and dispatch via evaluate_js.

        v3.0.0 M4: one ``evaluate_js`` per batch (instead of per event).
        The injected JS prefers ``window.__pywebvueDispatchEvents`` (set up
        by ``pywebvue.app`` bootstrap) and falls back to per-event
        ``document.dispatchEvent`` when the helper is absent, so an old
        frontend bundle keeps working with the new backend.
        """
        if self._window is None:
            while True:
                try:
                    self._event_queue.get_nowait()
                except queue.Empty:
                    break
            return

        # Drain the whole queue up front (preserves FIFO order), then
        # dispatch in chunks by the serialized-size budget.
        drained: list[tuple[str, Any]] = []
        while True:
            try:
                drained.append(self._event_queue.get_nowait())
            except queue.Empty:
                break

        batch: list[tuple[str, Any]] = []
        batch_bytes = 0
        for event, data in drained:
            size = len(json.dumps(data, ensure_ascii=False).encode("utf-8")) if data is not None else 4
            if batch and batch_bytes + size > self._MAX_BATCH_BYTES:
                if not self._dispatch_batch(batch):
                    return
                batch = []
                batch_bytes = 0
            batch.append((event, data))
            batch_bytes += size

        if batch:
            self._dispatch_batch(batch)

    def _dispatch_batch(self, batch: list[tuple[str, Any]]) -> bool:
        """Send one batch via a single evaluate_js call.

        Returns False if the window was closed (evaluate_js failed).
        """
        events_json = json.dumps(
            [{"name": f"pywebvue:{e}", "detail": d} for e, d in batch],
            ensure_ascii=False,
        )
        js = (
            "(function(){"
            "var evts=" + events_json + ";"
            "if (typeof window.__pywebvueDispatchEvents === 'function')"
            "{ window.__pywebvueDispatchEvents(evts); }"
            "else { for (var i = 0; i < evts.length; i++)"
            "{ document.dispatchEvent(new CustomEvent(evts[i].name,"
            "{ detail: evts[i].detail, bubbles: true })); } }"
            "})();"
        )
        try:
            self._window.evaluate_js(js)
        except Exception:
            logger.debug("evaluate_js failed, marking window as closed")
            while True:
                try:
                    self._event_queue.get_nowait()
                except queue.Empty:
                    break
            self._window = None
            return False
        return True

    @expose
    def tick(self) -> dict[str, Any]:
        """Process queued events.

        Called periodically by a JS timer (recursive ``setTimeout``).
        v3.0.0 M4: returns the remaining queue depth so the JS loop can
        drop to a slow cadence when idle (adaptive tick).
        v3.0.0 M9-3: task-queue machinery removed (zero callers since
        introduction -- verified in the v3.0.0 risk review).
        """
        self._flush_events()
        return {"success": True, "data": {"pending": self._event_queue.qsize()}}

    def _on_drop(self, event: dict) -> None:
        """Handle native file drag-and-drop events from pywebview."""
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            with self._drop_lock:
                self._dropped_paths.extend(paths)

    @expose
    def get_dropped_files(self) -> dict[str, Any]:
        """Return file paths from the most recent drop event and clear the buffer."""
        with self._drop_lock:
            paths = list(self._dropped_paths)
            self._dropped_paths.clear()
        return {"success": True, "data": paths}
