"""v2.1.1 M1-2: TaskManager must distinguish cancellation from failure.

Regression tests for the bug where cancelling a running task marked it
FAILED and emitted TASK_FAILED with a full stack trace. After the fix,
a handler that raises ``RuntimeError("Cancelled")`` (or any exception
while ``cancel_event`` is set) results in:

- task status -> CANCELLED (not FAILED)
- TASK_CANCELLED emitted (not TASK_FAILED)
- no ``logger.exception`` stack trace
"""

from __future__ import annotations

from core.events import TASK_CANCELLED, TASK_COMPLETED, TASK_FAILED
from core.models import MiloTask, TaskType
from core.task_manager import TaskManager


def _make_task(task_type: TaskType = TaskType.SILENCE_DETECTION) -> tuple[str, MiloTask]:
    return (
        "task-cancel-1",
        MiloTask(id="task-cancel-1", type=task_type, payload={}),
    )


def _build_manager():
    emitted: list[tuple[str, dict]] = []

    def emit_fn(event_name: str, detail: dict) -> None:
        emitted.append((event_name, detail))

    tm = TaskManager(emit_fn)
    return tm, emitted


def _seed_task(tm: TaskManager, task_id: str, task: MiloTask) -> None:
    """Pre-populate _tasks the way the queue dispatcher would before _execute_task."""
    tm._tasks[task_id] = task


class TestCancelDistinction:
    """Cancel vs failure vs success paths in _execute_task."""

    def test_cancelled_handler_marks_cancelled(self):
        """Handler raising RuntimeError('Cancelled') -> CANCELLED + TASK_CANCELLED."""
        tm, emitted = _build_manager()

        def handler(task, cancel_event, progress_cb):
            raise RuntimeError("Cancelled")

        tm.register_handler(TaskType.SILENCE_DETECTION, handler)
        task_id, task = _make_task()
        _seed_task(tm, task_id, task)
        tm._execute_task(task_id, task)

        assert tm._tasks[task_id].status.value == "cancelled"
        event_names = [e[0] for e in emitted]
        assert TASK_CANCELLED in event_names
        assert TASK_FAILED not in event_names

    def test_real_failure_marks_failed(self):
        """A genuine exception (cancel_event not set) -> FAILED + TASK_FAILED."""
        tm, emitted = _build_manager()

        def handler(task, cancel_event, progress_cb):
            raise ValueError("boom")

        tm.register_handler(TaskType.SILENCE_DETECTION, handler)
        task_id, task = _make_task()
        _seed_task(tm, task_id, task)
        tm._execute_task(task_id, task)

        assert tm._tasks[task_id].status.value == "failed"
        assert tm._tasks[task_id].error == "boom"
        event_names = [e[0] for e in emitted]
        assert TASK_FAILED in event_names
        assert TASK_CANCELLED not in event_names

    def test_cancel_event_set_marks_cancelled(self):
        """Any exception while cancel_event is set -> CANCELLED (even non-Cancelled exc).

        Simulates the real LLM flow: the handler observes cancel (cancels itself
        via the event it receives) and then raises a non-RuntimeError exception
        mid-teardown. task_manager must still classify this as CANCELLED because
        cancel_event.is_set() is True.
        """
        tm, emitted = _build_manager()

        def handler(task, cancel_event, progress_cb):
            # The handler cancels itself (as the LLM layer does when the user
            # clicks cancel), then a downstream cleanup raises a plain error.
            cancel_event.set()
            raise OSError("connection aborted during teardown")

        tm.register_handler(TaskType.SILENCE_DETECTION, handler)
        task_id, task = _make_task()
        _seed_task(tm, task_id, task)
        tm._execute_task(task_id, task)

        assert tm._tasks[task_id].status.value == "cancelled"
        event_names = [e[0] for e in emitted]
        assert TASK_CANCELLED in event_names
        assert TASK_FAILED not in event_names

    def test_successful_handler_marks_completed(self):
        tm, emitted = _build_manager()

        def handler(task, cancel_event, progress_cb):
            return {"ok": True}

        tm.register_handler(TaskType.SILENCE_DETECTION, handler)
        task_id, task = _make_task()
        _seed_task(tm, task_id, task)
        tm._execute_task(task_id, task)

        assert tm._tasks[task_id].status.value == "completed"
        event_names = [e[0] for e in emitted]
        assert TASK_COMPLETED in event_names

    def test_cancelled_event_carries_task_type(self):
        """TASK_CANCELLED detail includes task_type for frontend filtering."""
        tm, emitted = _build_manager()

        def handler(task, cancel_event, progress_cb):
            raise RuntimeError("Cancelled")

        tm.register_handler(TaskType.SILENCE_DETECTION, handler)
        task_id, task = _make_task()
        _seed_task(tm, task_id, task)
        tm._execute_task(task_id, task)

        cancelled_events = [d for name, d in emitted if name == TASK_CANCELLED]
        assert len(cancelled_events) == 1
        assert cancelled_events[0]["task_id"] == task_id
        assert cancelled_events[0]["task_type"] == TaskType.SILENCE_DETECTION.value
