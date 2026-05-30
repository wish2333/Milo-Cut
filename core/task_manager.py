"""Production-ready task manager with priority queue and concurrency control.

Fixes over previous implementation:
- HoL blocking: Worker thread only dispatches, execution in separate threads
- FIFO ordering: Atomic sequence counter ensures same-priority FIFO via three-tuple
- Cancel race condition: Queued tasks can be cancelled before execution
- Double-check pattern prevents executing cancelled tasks after semaphore acquisition
"""

from __future__ import annotations

import itertools
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from core.events import TASK_COMPLETED, TASK_FAILED, TASK_PROGRESS
from core.models import MiloTask, TaskProgress, TaskStatus, TaskType


class TaskManager:
    """High-concurrency task manager with HoL-blocking fix and FIFO ordering."""

    HEAVY_TASKS: set[TaskType] = {
        TaskType.EXPORT_VIDEO,
        TaskType.EXPORT_AUDIO,
        TaskType.TRANSCRIPTION,
        TaskType.SILENCE_DETECTION,
    }
    LIGHT_TASKS: set[TaskType] = {
        TaskType.WAVEFORM_GENERATION,
        TaskType.PROXY_GENERATION,
    }

    def __init__(self, emit_fn: Callable[[str, Any], None]) -> None:
        self._emit = emit_fn
        self._tasks: dict[str, MiloTask] = {}
        self._queue: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._cancel_events: dict[str, threading.Event] = {}  # Only for RUNNING tasks
        self._lock = threading.Lock()
        self._handlers: dict[TaskType, Callable[[MiloTask, threading.Event, Callable[[float, str], None]], dict]] = {}

        # Atomic counter for FIFO ordering within same priority
        self._sequence = itertools.count()

        # Concurrency control
        self._heavy_semaphore = threading.Semaphore(1)  # GPU/CPU-intensive
        self._light_semaphore = threading.Semaphore(3)  # I/O-bound

        # Worker thread
        self._worker_thread: threading.Thread | None = None
        self._worker_running = False

    def register_handler(
        self,
        task_type: TaskType,
        handler: Callable[[MiloTask, threading.Event, Callable[[float, str], None]], dict],
    ) -> None:
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler

    def create_task(
        self,
        task_type: str,
        payload: dict | None = None,
        priority: str = "normal",
    ) -> dict:
        """Create task with priority level and auto-dispatch to queue.

        Args:
            task_type: Task type string
            payload: Task payload
            priority: "high" (0), "normal" (1), "low" (2)
        """
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

            # Three-tuple: (priority, sequence, task_id)
            # Ensures FIFO within same priority level
            priority_map = {"high": 0, "normal": 1, "low": 2}
            priority_num = priority_map.get(priority, 1)
            self._queue.put((priority_num, next(self._sequence), task_id))

        self._ensure_worker()

        return {"success": True, "data": task.model_dump()}

    def start_task(self, task_id: str) -> dict:
        """Start a queued task. Compatibility shim -- tasks auto-dispatch on create.

        Returns success if the task exists and is queued or already running.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"success": False, "error": f"Task not found: {task_id}"}
            if task.status not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                return {"success": False, "error": f"Task {task_id} is {task.status}, not queued"}
            # Ensure worker is running to pick up queued tasks
        self._ensure_worker()
        with self._lock:
            return {"success": True, "data": self._tasks[task_id].model_dump()}

    def cancel_task(self, task_id: str) -> dict:
        """Cancel task -- works for both queued and running tasks.

        For queued tasks: Sets status to CANCELLED, worker will skip.
        For running tasks: Triggers cancel_event to terminate handler.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"success": False, "error": f"Task not found: {task_id}"}

            # Case A: Task still queued -- mark as cancelled, worker will skip
            if task.status == TaskStatus.QUEUED:
                self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
                return {"success": True, "data": self._tasks[task_id].model_dump()}

            # Case B: Task running -- trigger cancel event to terminate handler
            if task.status == TaskStatus.RUNNING:
                event = self._cancel_events.get(task_id)
                if event:
                    event.set()
                self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
                return {"success": True, "data": self._tasks[task_id].model_dump()}

        return {"success": False, "error": f"Task {task_id} is {task.status}, cannot cancel"}

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

    # ------------------------------------------------------------------
    # Internal: worker dispatch and execution
    # ------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        """Start worker thread if not already running."""
        with self._lock:
            if not self._worker_running:
                self._worker_running = True
                self._worker_thread = threading.Thread(
                    target=self._process_queue,
                    daemon=True,
                )
                self._worker_thread.start()

    def _process_queue(self) -> None:
        """Dispatch loop: only pulls tasks and spawns execution threads.

        This thread NEVER blocks on semaphore acquisition.
        """
        while True:
            try:
                _priority_num, _seq, task_id = self._queue.get(timeout=5.0)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker_running = False
                        return
                continue

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                # Skip tasks cancelled while queued
                if task.status == TaskStatus.CANCELLED:
                    continue

            # Spawn separate thread for semaphore + execution
            # This prevents HoL blocking on the dispatch loop
            t = threading.Thread(
                target=self._threaded_execution_wrapper,
                args=(task_id, task),
                daemon=True,
            )
            t.start()

    def _threaded_execution_wrapper(self, task_id: str, task: MiloTask) -> None:
        """Acquire appropriate semaphore and execute in separate thread."""
        semaphore = (
            self._heavy_semaphore
            if task.type in self.HEAVY_TASKS
            else self._light_semaphore
        )

        semaphore.acquire()
        try:
            # Double-check: re-check status (user may have cancelled while waiting)
            with self._lock:
                current = self._tasks.get(task_id)
                if current is None or current.status != TaskStatus.QUEUED:
                    return
            self._execute_task(task_id, task)
        finally:
            semaphore.release()

    def _execute_task(self, task_id: str, task: MiloTask) -> None:
        """Execute a single task handler."""
        handler = self._handlers.get(task.type)
        if not handler:
            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(update={
                        "status": TaskStatus.FAILED,
                        "error": f"No handler for task type: {task.type}",
                    })
            return

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[task_id] = cancel_event
            current = self._tasks.get(task_id)
            if current:
                self._tasks[task_id] = current.model_copy(update={
                    "status": TaskStatus.RUNNING,
                    "started_at": datetime.now().isoformat(),
                })

        try:
            def progress_cb(percent: float, message: str = "") -> None:
                self._update_progress(task_id, percent, message)

            result = handler(task, cancel_event, progress_cb)

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
                "task_type": task.type.value,
                "result": result,
            })

        except Exception as e:
            logger.exception("Task {} failed", task_id)
            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(update={
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
