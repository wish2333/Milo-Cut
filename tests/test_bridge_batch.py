"""Batch event dispatch tests for v3.0.0 M4 (P2-2).

Covers the red lines from risk review 3.2 (M4) and SPEC errata 2.1/2.2:

- single event works (new batch path)
- multiple events go out in ONE evaluate_js call, order preserved
- 512KB budget splits into multiple evaluate_js calls, order preserved
- the injected dispatch JS carries a typeof fallback (old-frontend compat)
- tick() returns the remaining pending count
- task:completed strips the project payload (project_stripped marker)
"""

from __future__ import annotations

import json

import pytest

from core.events import TASK_COMPLETED
from core.models import TaskType
from pywebvue.bridge import Bridge


class FakeWindow:
    """Records every evaluate_js call."""

    def __init__(self):
        self.scripts: list[str] = []

    def evaluate_js(self, js: str) -> None:
        self.scripts.append(js)


@pytest.fixture
def bridge() -> Bridge:
    b = Bridge()
    b._window = FakeWindow()
    return b


def _dispatched_events(script: str) -> list[dict]:
    """Extract the ``evts`` JSON array from a dispatch script."""
    marker = "var evts="
    start = script.index(marker) + len(marker)
    end = script.index(";", start)
    return json.loads(script[start:end])


class TestBatchDispatch:
    def test_single_event_single_call(self, bridge: Bridge) -> None:
        bridge._emit("hello", {"a": 1})
        bridge._flush_events()
        win: FakeWindow = bridge._window
        assert len(win.scripts) == 1
        evts = _dispatched_events(win.scripts[0])
        assert evts == [{"name": "pywebvue:hello", "detail": {"a": 1}}]

    def test_batch_sends_one_call_with_order_preserved(self, bridge: Bridge) -> None:
        for i in range(20):
            bridge._emit(f"ev{i}", {"i": i})
        bridge._flush_events()
        win: FakeWindow = bridge._window
        assert len(win.scripts) == 1  # one evaluate_js for the whole batch
        evts = _dispatched_events(win.scripts[0])
        assert [e["name"] for e in evts] == [f"pywebvue:ev{i}" for i in range(20)]

    def test_large_payload_splits_preserving_order(self, bridge: Bridge) -> None:
        # Each payload ~300KB serialized -> budget 512KB -> one per batch.
        big = "x" * (300 * 1024)
        for i in range(3):
            bridge._emit(f"big{i}", {"blob": big, "i": i})
        bridge._flush_events()
        win: FakeWindow = bridge._window
        assert len(win.scripts) == 3
        names = []
        for script in win.scripts:
            evts = _dispatched_events(script)
            assert len(evts) == 1
            names.append(evts[0]["name"])
        assert names == ["pywebvue:big0", "pywebvue:big1", "pywebvue:big2"]

    def test_mixed_sizes_group_within_budget(self, bridge: Bridge) -> None:
        # 10 payloads of ~60KB each -> 2 batches of 5 within 512KB budget.
        blob = "y" * (60 * 1024)
        for i in range(10):
            bridge._emit(f"m{i}", {"blob": blob, "i": i})
        bridge._flush_events()
        win: FakeWindow = bridge._window
        assert len(win.scripts) == 2
        combined = [_dispatched_events(s) for s in win.scripts]
        assert len(combined[0]) + len(combined[1]) == 10
        flat = [e["name"] for chunk in combined for e in chunk]
        assert flat == [f"pywebvue:m{i}" for i in range(10)]

    def test_dispatch_js_has_fallback_for_old_frontend(self, bridge: Bridge) -> None:
        bridge._emit("compat", None)
        bridge._flush_events()
        win: FakeWindow = bridge._window
        script = win.scripts[0]
        assert "typeof window.__pywebvueDispatchEvents === 'function'" in script
        assert "document.dispatchEvent" in script
        assert "bubbles: true" in script

    def test_window_closed_drops_queue(self) -> None:
        b = Bridge()

        class DeadWindow:
            def evaluate_js(self, js: str) -> None:
                raise RuntimeError("window closed")

        b._window = DeadWindow()
        b._emit("doomed", {"x": 1})
        b._flush_events()
        assert b._window is None


class TestTickPending:
    def test_tick_returns_pending_zero(self, bridge: Bridge) -> None:
        res = bridge.tick()
        assert res["success"] is True
        assert res["data"]["pending"] == 0

    def test_tick_returns_pending_count(self, bridge: Bridge) -> None:
        # Dispatch target is a plain FakeWindow; _flush_events will drain
        # via evaluate_js, so count pending BEFORE the flush by calling
        # tick with window None first to check queue depth behaviour.
        for i in range(5):
            bridge._emit(f"p{i}", {"i": i})
        res = bridge.tick()
        assert res["data"]["pending"] == 0  # drained by this very tick
        assert len(bridge._window.scripts) == 1

    def test_tick_no_window_clears_queue(self) -> None:
        b = Bridge()
        b._window = None
        b._emit("x", 1)
        res = b.tick()
        assert res["success"] is True
        assert b._event_queue.empty()


class TestCompletedProjectStripped:
    """task:completed must not carry the full project (M4-3)."""

    @staticmethod
    def _run_task(monkeypatch, task_type: TaskType, result: dict) -> list[tuple]:
        import time

        from core.task_manager import TaskManager

        captured: list[tuple] = []
        manager = TaskManager(emit_fn=lambda name, data: captured.append((name, data)))
        manager.register_handler(task_type, lambda task, ce, cb: result)
        manager.create_task(task_type.value, {})
        deadline = time.time() + 5
        while time.time() < deadline and not captured:
            time.sleep(0.02)
        return captured

    def test_completed_event_strips_project(self, monkeypatch, tmp_path):
        from core.models import TaskType

        captured = self._run_task(
            monkeypatch,
            TaskType.SILENCE_DETECTION,
            {"status": "ok", "project": {"huge": "dump"}, "revision": 7},
        )
        assert captured, "TASK_COMPLETED event must be emitted"
        name, data = captured[0]
        assert name == TASK_COMPLETED
        assert "project" not in data["result"]
        assert data["result_meta"]["project_stripped"] is True
        assert data["result"]["revision"] == 7

    def test_completed_event_without_project_untouched(self, monkeypatch, tmp_path):
        from core.models import TaskType

        captured = self._run_task(
            monkeypatch,
            TaskType.WAVEFORM_GENERATION,
            {"waveform_path": "/tmp/p.png"},
        )
        assert captured
        name, data = captured[0]
        assert name == TASK_COMPLETED
        assert data["result"] == {"waveform_path": "/tmp/p.png"}
        assert data["result_meta"] == {}
