"""Unified task manager for long-running background operations.

Provides create/start/cancel/query for tasks like silence detection, export, etc.
Tasks run on background threads and report progress via bridge events.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from core.events import TASK_COMPLETED, TASK_FAILED, TASK_PROGRESS
from core.models import MiloTask, TaskProgress, TaskStatus, TaskType


class TaskManager:
    """Manages background tasks with progress reporting."""

    def __init__(self, emit_fn: Callable[[str, Any], None]) -> None:
        self._emit = emit_fn
        self._tasks: dict[str, MiloTask] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._handlers: dict[TaskType, Callable[[MiloTask, threading.Event], dict]] = {}

    def register_handler(
        self, task_type: TaskType, handler: Callable[[MiloTask, threading.Event], dict]
    ) -> None:
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler

    def create_task(self, task_type: str, payload: dict | None = None) -> dict:
        """Create a new task and return its data."""
        try:
            tt = TaskType(task_type)
        except ValueError:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

        task_id = str(uuid.uuid4())[:8]
        task = MiloTask(
            id=task_id,
            type=tt,
            status=TaskStatus.QUEUED,
            payload=payload or {},
        )
        with self._lock:
            self._tasks[task_id] = task

        return {"success": True, "data": task.model_dump()}

    def start_task(self, task_id: str) -> dict:
        """Start a queued task on a background thread."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"success": False, "error": f"Task not found: {task_id}"}
            if task.status != TaskStatus.QUEUED:
                return {"success": False, "error": f"Task {task_id} is {task.status}, not queued"}

            handler = self._handlers.get(task.type)
            if handler is None:
                return {"success": False, "error": f"No handler for task type: {task.type}"}

            cancel_event = threading.Event()
            self._cancel_events[task_id] = cancel_event
            self._tasks[task_id] = task.model_copy(update={
                "status": TaskStatus.RUNNING,
                "started_at": datetime.now().isoformat(),
            })

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, handler, cancel_event),
            daemon=True,
        )
        thread.start()
        with self._lock:
            return {"success": True, "data": self._tasks[task_id].model_dump()}

    def cancel_task(self, task_id: str) -> dict:
        """Request cancellation of a running task."""
        with self._lock:
            task = self._tasks.get(task_id)
            event = self._cancel_events.get(task_id)
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}
        if event:
            event.set()
        with self._lock:
            self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
        return {"success": True}

    def get_task(self, task_id: str) -> dict:
        """Get a task by ID."""
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}
        return {"success": True, "data": task.model_dump()}

    def list_tasks(self) -> dict:
        """List all tasks."""
        with self._lock:
            tasks = [t.model_dump() for t in self._tasks.values()]
        return {"success": True, "data": tasks}

    def _update_progress(self, task_id: str, percent: float, message: str) -> None:
        """Update task progress and emit event."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            self._tasks[task_id] = task.model_copy(update={
                "progress": TaskProgress(percent=percent, message=message),
            })
        self._emit(TASK_PROGRESS, {
            "task_id": task_id,
            "percent": percent,
            "message": message,
        })

    def _run_task(
        self,
        task_id: str,
        handler: Callable[[MiloTask, threading.Event], dict],
        cancel_event: threading.Event,
    ) -> None:
        """Execute a task handler in a background thread."""
        try:
            with self._lock:
                task = self._tasks.get(task_id)
            if task is None:
                return

            def progress_cb(percent: float, message: str = "") -> None:
                self._update_progress(task_id, percent, message)

            result = handler(task, cancel_event)

            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(update={
                        "status": TaskStatus.COMPLETED,
                        "progress": TaskProgress(percent=100),
                        "result": result,
                        "completed_at": datetime.now().isoformat(),
                    })

            self._emit(TASK_COMPLETED, {
                "task_id": task_id,
                "task_type": task.type.value if task else None,
                "result": result,
            })

        except Exception as e:
            logger.exception("Task {} failed", task_id)
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    self._tasks[task_id] = task.model_copy(update={
                        "status": TaskStatus.FAILED,
                        "error": str(e),
                        "completed_at": datetime.now().isoformat(),
                    })

            self._emit(TASK_FAILED, {
                "task_id": task_id,
                "error": str(e),
            })

        finally:
            with self._lock:
                self._cancel_events.pop(task_id, None)
