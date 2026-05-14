"""Bridge base class and @expose decorator."""

from __future__ import annotations

import functools
import itertools
import json
import logging
import queue
import re
import threading
import warnings
from typing import Any, Callable

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

    Bridge-thread task execution:
        Use ``register_handler(name, handler)`` to register handlers,
        then ``run_on_bridge(name, args)`` from background threads.
    """

    def __init__(self, *, debug: bool = False) -> None:
        self._window = None
        self._debug = debug
        self._drop_lock = threading.Lock()
        self._dropped_paths: list[str] = []
        self._event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        # Task execution: handler registry + task queue
        self._handlers: dict[str, Callable[[Any], Any]] = {}
        self._task_queue: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self._pending_results: dict[str, queue.Queue[tuple[bool, Any]]] = {}
        self._cancelled_tasks: set[str] = set()
        self._task_lock = threading.Lock()
        self._task_counter = itertools.count(1)

    def _emit(self, event: str, data: Any = None) -> None:
        """Thread-safe: queue an event for main-thread delivery."""
        if not _EVENT_RE.fullmatch(event):
            raise ValueError(f"Invalid event name: {event!r}")
        self._event_queue.put((event, data))

    def _flush_events(self) -> None:
        """Drain the event queue and dispatch via evaluate_js."""
        if self._window is None:
            while True:
                try:
                    self._event_queue.get_nowait()
                except queue.Empty:
                    break
            return

        while True:
            try:
                event, data = self._event_queue.get_nowait()
            except queue.Empty:
                break

            payload = json.dumps(data, ensure_ascii=False) if data is not None else "null"
            event_name = json.dumps(f"pywebvue:{event}", ensure_ascii=False)
            js = (
                f"document.dispatchEvent("
                f"new CustomEvent({event_name}, "
                f"{{detail: {payload}, bubbles: true}}))"
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
                break

    @expose
    def tick(self) -> dict[str, Any]:
        """Process queued events and execute one pending task.

        Called periodically by a JS timer (recursive ``setTimeout``).
        """
        self._flush_events()
        self._execute_next_task()
        return {"success": True}

    def _execute_next_task(self) -> None:
        """Execute at most one pending task from the queue."""
        try:
            task_id, name, args = self._task_queue.get_nowait()
        except queue.Empty:
            return

        handler = self._handlers.get(name)
        if handler is None:
            self._deliver_result(task_id, False, f"Unknown handler: {name}")
            return

        # Skip tasks whose caller has already timed out.
        with self._task_lock:
            if task_id in self._cancelled_tasks:
                self._cancelled_tasks.discard(task_id)
                return

        try:
            result = handler(args)
            self._deliver_result(task_id, True, result)
        except Exception as e:
            logger.debug("Handler '%s' failed: %s", name, e)
            self._deliver_result(task_id, False, str(e))

    def _deliver_result(self, task_id: str, success: bool, result: Any) -> None:
        """Put a task result into the caller's result queue."""
        with self._task_lock:
            result_q = self._pending_results.get(task_id)
        if result_q is not None:
            result_q.put((success, result))

    def register_handler(self, name: str, handler: Callable[[Any], Any]) -> None:
        """Register a named handler for bridge-thread task execution.

        Handlers are called when scheduled via ``run_on_bridge(name, args)``.
        """
        self._handlers[name] = handler

    def run_on_bridge(
        self, name: str, args: Any = None, timeout: float = 30.0
    ) -> Any:
        """Schedule a named handler and block until completion.

        Thread-safe: callable from background threads.
        Raises TimeoutError if the task exceeds *timeout* seconds.
        Raises RuntimeError if the handler raises or is not registered.
        """
        task_id = str(next(self._task_counter))
        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue()

        with self._task_lock:
            self._pending_results[task_id] = result_queue

        self._task_queue.put((task_id, name, args))

        try:
            success, result = result_queue.get(timeout=timeout)
            if not success:
                raise RuntimeError(f"Task '{name}' failed: {result}")
            return result
        except queue.Empty:
            with self._task_lock:
                self._cancelled_tasks.add(task_id)
            raise TimeoutError(
                f"Task '{name}' (id={task_id}) timed out after {timeout}s"
            )
        finally:
            with self._task_lock:
                self._pending_results.pop(task_id, None)

    def _on_drop(self, event: dict) -> None:
        """Handle native file drag-and-drop events from pywebview."""
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [
            f.get("pywebviewFullPath")
            for f in files
            if f.get("pywebviewFullPath")
        ]
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

    def run_on_main_thread(
        self, name: str, args: Any = None, timeout: float = 30.0
    ) -> Any:
        """Deprecated: use ``run_on_bridge`` instead."""
        warnings.warn(
            "run_on_main_thread() is deprecated, use run_on_bridge() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.run_on_bridge(name, args, timeout)
