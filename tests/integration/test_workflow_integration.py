"""Workflow integration tests (v2.1.0 Phase 4补齐).

Multi-step orchestration, snapshot persistence + recovery, end-to-end
apply flow, and preset_id dispatch validation.

All tests use ``@pytest.mark.integration`` and are excluded from the
default test run via ``addopts = "-m 'not integration'"`` in
pyproject.toml.  Run with: ``uv run pytest -m integration``
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from unittest.mock import MagicMock

import pytest

from core.workflow_engine import (
    STEP_DISPLAY_NAMES,
    STEP_TO_TASK_TYPE,
    VALID_STEP_TYPES,
    WorkflowEngine,
)
from tests.mocks.factories import make_project, make_segments

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Redirect settings.json to an isolated temp file."""
    from core.config import _DEFAULT_SETTINGS

    settings_path = tmp_path / "settings.json"

    def _load() -> dict:
        if not settings_path.exists():
            return copy.deepcopy(_DEFAULT_SETTINGS)
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return copy.deepcopy(_DEFAULT_SETTINGS)
        merged = copy.deepcopy(_DEFAULT_SETTINGS)
        merged.update(data)
        return merged

    def _save(settings: dict) -> None:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = settings_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, settings_path)

    monkeypatch.setattr("core.config.load_settings", _load)
    monkeypatch.setattr("core.config.save_settings", _save)
    return settings_path


@pytest.fixture
def project_deps(tmp_path):
    """ProjectService mock with real-ish project + file-backed snapshot dir."""
    proj_path = tmp_path / "projects" / "test-proj" / "project.json"
    proj_path.parent.mkdir(parents=True, exist_ok=True)

    project_svc = MagicMock()
    segments = make_segments(4, text_template="segment {}")
    project_svc.current = make_project(segments=segments, name="test-proj")
    project_svc.current_path = proj_path
    return project_svc


@pytest.fixture
def engine(project_deps, isolated_settings, monkeypatch):
    """WorkflowEngine with isolated settings + mocked TaskManager + LLM config."""
    events_log: list[tuple[str, dict]] = []

    def _emit(name: str, data: dict) -> None:
        events_log.append((name, data))

    task_mgr = MagicMock()
    task_mgr.create_task.return_value = {
        "success": True,
        "data": {"id": "task-fake-001", "status": "queued"},
    }
    task_mgr.get_task.return_value = {
        "success": True,
        "data": {"id": "task-fake-001", "status": "completed", "result": {}},
    }

    wf = WorkflowEngine(task_mgr, project_deps, _emit)
    wf._events_log = events_log  # type: ignore[attr-defined]

    # Mock LLM config so workflow start succeeds for LLM steps (D-26)
    _mock_llm_cfg = MagicMock()
    _mock_llm_cfg.is_configured.return_value = True
    monkeypatch.setattr(
        "core.llm_service.get_llm_config",
        lambda: _mock_llm_cfg,
    )
    return wf


def _segments_hash(segments) -> str:
    """Compute the same hash WorkflowEngine uses for D-67 validation."""
    payload = json.dumps(
        [{"id": s.id, "s": s.start, "e": s.end, "t": s.text} for s in segments],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _make_task_polling(
    task_mgr: MagicMock,
    *,
    final_status: str = "completed",
    result: dict | None = None,
    error: str = "",
    poll_count: int = 3,
):
    """Configure TaskManager.get_task to simulate async task lifecycle."""
    call_count = {"n": 0}

    def _get_task(tid: str):
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            return {"success": True, "data": {"id": tid, "status": "queued"}}
        elif n == 2:
            return {"success": True, "data": {"id": tid, "status": "running"}}
        elif n >= poll_count:
            if final_status == "completed":
                return {
                    "success": True,
                    "data": {"id": tid, "status": "completed", "result": result or {}},
                }
            else:
                return {
                    "success": True,
                    "data": {"id": tid, "status": "failed", "error": error or "Task failed"},
                }
        else:
            return {
                "success": True,
                "data": {"id": tid, "status": "running",
                         "progress": {"percent": n * 20, "message": "processing"}},
            }

    task_mgr.get_task.side_effect = _get_task



# ------------------------------------------------------------------
# 1. Multi-step orchestration
# ------------------------------------------------------------------


@pytest.mark.integration
class TestMultiStepOrchestration:
    """Verify serial step execution, progress events, and snapshot updates."""

    def test_two_steps_complete_successfully(self, engine, project_deps):
        """Two-step workflow: full_analysis + llm_smart_delete."""
        wf_def = engine.save_workflow("two-step", [
            {"type": "full_analysis", "preset_id": None},
            {"type": "llm_smart_delete", "preset_id": None},
        ])
        assert wf_def["success"]
        wf_id = wf_def["data"]["id"]

        poll_n = {"n": 0}

        def _fast_poll(tid):
            poll_n["n"] += 1
            result = {}
            if poll_n["n"] > 1:
                result = {
                    "edits": [
                        {"id": "edit-wf-1", "start": 0, "end": 5.5, "action": "delete",
                         "source": "llm_smart_delete", "target_type": "segment",
                         "target_id": "seg-0001", "reason": "filler", "priority": 100},
                    ],
                    "results": [],
                    "token_usage": {"total_tokens": 10},
                }
            return {"success": True, "data": {"id": tid, "status": "completed", "result": result}}

        engine._task_manager.get_task.side_effect = _fast_poll

        start = engine.start_workflow(wf_id)
        assert start["success"]

        for _ in range(50):
            if engine._active is None or engine._active.get("status") in ("completed", "cancelled", "failed"):
                break
            time.sleep(0.1)
        else:
            pytest.fail("Workflow execution did not complete within 5s")

        log = engine._events_log
        started = [e for e in log if e[0] == "workflow:started"]
        assert len(started) == 1
        completed = [e for e in log if e[0] == "workflow:completed"]
        assert len(completed) == 1
        assert completed[0][1]["total_edits"] >= 1

    def test_step_failure_triggers_failed_event(self, engine, project_deps):
        """When a step fails, workflow:step_failed event is emitted."""
        wf_def = engine.save_workflow("fail-test", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        _make_task_polling(
            engine._task_manager, final_status="failed", error="analysis error",
            poll_count=3,
        )

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.5)
        engine.handle_step_failure("abort")

        for _ in range(50):
            if engine._active is None or engine._active.get("status") in ("cancelled", "failed"):
                break
            time.sleep(0.1)

        log = engine._events_log
        failed_events = [e for e in log if e[0] == "workflow:step_failed"]
        assert len(failed_events) >= 1
        assert "analysis error" in failed_events[0][1]["error"]

    def test_step_failure_skip_continues(self, engine, project_deps):
        """Skip a failed step, subsequent steps still execute."""
        wf_def = engine.save_workflow("skip-test", [
            {"type": "full_analysis", "preset_id": None},
            {"type": "llm_smart_delete", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        create_n = {"n": 0}

        def _create(task_type_str, payload):
            create_n["n"] += 1
            tid = f"task-{create_n['n']}"
            return {"success": True, "data": {"id": tid, "status": "queued"}}

        engine._task_manager.create_task.side_effect = _create

        poll_n = {"n": 0}

        def _poll(tid):
            poll_n["n"] += 1
            if "task-1" in tid:
                if poll_n["n"] >= 2:
                    return {"success": True, "data": {"id": tid, "status": "failed", "error": "step 1 failed"}}
                return {"success": True, "data": {"id": tid, "status": "running"}}
            else:
                if poll_n["n"] >= 2:
                    return {"success": True, "data": {"id": tid, "status": "completed", "result": {"edits": [], "results": [], "token_usage": {}}}}
                return {"success": True, "data": {"id": tid, "status": "running"}}

        engine._task_manager.get_task.side_effect = _poll

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.8)
        engine.handle_step_failure("skip")

        for _ in range(50):
            if engine._active is None or engine._active.get("status") in ("completed", "cancelled", "failed"):
                break
            time.sleep(0.1)

        log = engine._events_log
        completed = [e for e in log if e[0] == "workflow:completed"]
        assert len(completed) == 1

    def test_step_failure_retry(self, engine, project_deps):
        """Retry a failed step: first attempt fails, retry succeeds."""
        wf_def = engine.save_workflow("retry-test", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        _make_task_polling(
            engine._task_manager, final_status="failed", error="transient error",
            poll_count=2,
        )

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.5)

        poll_n = {"n": 0}

        def _retry_poll(tid):
            poll_n["n"] += 1
            if poll_n["n"] >= 2:
                return {"success": True, "data": {"id": tid, "status": "completed", "result": {"results": []}}}
            return {"success": True, "data": {"id": tid, "status": "running"}}

        engine._task_manager.get_task.side_effect = _retry_poll
        engine.handle_step_failure("retry")

        for _ in range(50):
            if engine._active is None or engine._active.get("status") in ("completed", "cancelled", "failed"):
                break
            time.sleep(0.1)

        log = engine._events_log
        completed = [e for e in log if e[0] == "workflow:completed"]
        assert len(completed) == 1

    def test_cancel_immediate_stops_execution(self, engine, project_deps):
        """Immediate cancel: current step cancelled, workflow stops."""
        wf_def = engine.save_workflow("cancel-test", [
            {"type": "full_analysis", "preset_id": None},
            {"type": "llm_smart_delete", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        task_id_holder = {"id": None}

        def _create(task_type_str, payload):
            tid = f"task-slow-{id(task_type_str)}"
            task_id_holder["id"] = tid
            return {"success": True, "data": {"id": tid, "status": "queued"}}

        engine._task_manager.create_task.side_effect = _create

        cancelled_flag = {"done": False}

        def _slow_poll(tid):
            if cancelled_flag["done"]:
                return {"success": True, "data": {"id": tid, "status": "cancelled"}}
            return {"success": True, "data": {"id": tid, "status": "running",
                     "progress": {"percent": 10}}}

        engine._task_manager.get_task.side_effect = _slow_poll

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.5)
        cancel_result = engine.cancel_workflow("immediate")
        assert cancel_result["success"]
        cancelled_flag["done"] = True

        for _ in range(50):
            if engine._active is None or engine._active.get("status") == "cancelled":
                break
            time.sleep(0.1)

        log = engine._events_log
        cancelled = [e for e in log if e[0] == "workflow:cancelled"]
        assert len(cancelled) == 1



# ------------------------------------------------------------------
# 2. Snapshot persistence + cross-session recovery
# ------------------------------------------------------------------


@pytest.mark.integration
class TestSnapshotPersistence:
    """Verify snapshots are saved/loaded from disk, and resumable detection."""

    def test_snapshot_file_created_on_start(self, engine, project_deps):
        """Starting a workflow creates a _workflow_*.json snapshot file."""
        wf_def = engine.save_workflow("snapshot-test", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        _make_task_polling(engine._task_manager, poll_count=2, result={"results": []})

        start = engine.start_workflow(wf_id)
        assert start["success"]

        for _ in range(50):
            if engine._active is None:
                break
            time.sleep(0.1)

        snap_files = list(project_deps.current_path.parent.glob("_workflow_*.json"))
        assert len(snap_files) >= 1

    def test_resumable_snapshots_detected(self, engine, project_deps):
        """find_resumable_snapshots finds running snapshots."""
        snap_path = project_deps.current_path.parent / "_workflow_wfi-resume.json"
        snap_path.write_text(json.dumps({
            "workflow_instance_id": "wfi-resume",
            "workflow_name": "interrupted",
            "timeline_id": "default",
            "created_at": "2025-01-01T00:00:00",
            "status": "running",
            "current_step_index": 1,
            "total_steps": 3,
        }), encoding="utf-8")

        results = engine.find_resumable_snapshots()
        assert len(results) == 1
        assert results[0]["workflow_instance_id"] == "wfi-resume"

        snap_path.unlink()

    def test_completed_snapshot_not_resumable(self, engine, project_deps):
        """Completed snapshots are excluded from resumable list."""
        snap_path = project_deps.current_path.parent / "_workflow_wfi-done.json"
        snap_path.write_text(json.dumps({
            "workflow_instance_id": "wfi-done",
            "status": "completed",
        }), encoding="utf-8")

        assert engine.find_resumable_snapshots() == []
        snap_path.unlink()

    def test_snapshot_segments_hash_matches_project(self, engine, project_deps):
        """Snapshot stores correct SHA256 of project segments."""
        segments = project_deps.current.timelines[0].transcript.segments
        expected_hash = _segments_hash(segments)

        wf_def = engine.save_workflow("hash-test", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        _make_task_polling(engine._task_manager, final_status="failed",
                            error="fail", poll_count=2)

        start = engine.start_workflow(wf_id)
        assert start["success"]
        instance_id = start["data"]["workflow_instance_id"]

        time.sleep(0.5)
        engine.handle_step_failure("abort")
        time.sleep(0.5)

        snap_path = project_deps.current_path.parent / f"_workflow_{instance_id}.json"
        if snap_path.exists():
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            assert snap["segments_hash"] == expected_hash
            snap_path.unlink()


# ------------------------------------------------------------------
# 3. End-to-end apply flow
# ------------------------------------------------------------------


@pytest.mark.integration
class TestEndToEndApply:
    """Full lifecycle: define -> run -> detect conflicts -> resolve -> apply."""

    def test_apply_edits_to_project(self, engine, project_deps):
        """Workflow edits applied to project become EditDecisions."""
        segments = project_deps.current.timelines[0].transcript.segments
        seg_hash = _segments_hash(segments)

        engine._active = {
            "workflow_instance_id": "wfi-e2e",
            "workflow_id": "wf-e2e",
            "workflow_name": "E2E",
            "timeline_id": "default",
            "status": "completed",
            "current_step_index": 2,
            "total_steps": 2,
            "segments_hash": seg_hash,
            "accumulated_edits": [
                {
                    "id": "edit-e2e-1", "start": 0.0, "end": 5.5, "action": "delete",
                    "source": "llm_smart_delete", "target_type": "segment",
                    "target_id": segments[0].id, "reason": "filler", "priority": 100,
                    "step_type": "llm_smart_delete", "step_index": 1,
                },
            ],
            "segments_snapshot": [s.model_dump() for s in segments],
        }

        apply_result = engine.apply_workflow()
        assert apply_result["success"]
        assert apply_result["data"]["applied_count"] == 1
        assert "workflow:wf-e2e:E2E" == apply_result["data"]["source"]

        project = project_deps.current
        assert len(project.timelines[0].edits) == 1
        assert project.timelines[0].edits[0].source == "workflow:wf-e2e:E2E"
        assert engine._active is None

    def test_apply_blocks_on_hash_mismatch(self, engine, project_deps):
        """Apply fails if segments were modified after workflow started."""
        engine._active = {
            "workflow_instance_id": "wfi-hash",
            "workflow_id": "wf-1",
            "workflow_name": "hash",
            "timeline_id": "default",
            "segments_hash": "wrong-hash-value",
            "accumulated_edits": [],
        }

        result = engine.apply_workflow()
        assert not result["success"]
        assert "失效" in result["error"]

    def test_discard_clears_snapshot(self, engine, project_deps):
        """Discard removes snapshot file and clears active state."""
        snap_path = project_deps.current_path.parent / "_workflow_wfi-discard.json"
        snap_path.write_text(json.dumps({
            "workflow_instance_id": "wfi-discard", "status": "completed",
        }))

        engine._active = {
            "workflow_instance_id": "wfi-discard",
            "workflow_id": "wf-1",
            "workflow_name": "test",
            "timeline_id": "default",
            "accumulated_edits": [],
        }

        result = engine.discard_workflow()
        assert result["success"]
        assert engine._active is None
        assert not snap_path.exists()

    def test_conflict_detected(self, engine, project_deps):
        """After workflow completes, conflicts are detected for same-segment edits."""
        segments = project_deps.current.timelines[0].transcript.segments

        engine._active = {
            "workflow_instance_id": "wfi-conflict",
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": segments[0].id,
                 "action": "delete", "source": "smart_delete", "step_index": 0,
                 "reason": "filler"},
                {"id": "e2", "target_type": "segment", "target_id": segments[0].id,
                 "action": "keep", "source": "highlight", "step_index": 1,
                 "reason": "key point"},
            ],
            "segments_snapshot": [s.model_dump() for s in segments],
        }

        result = engine.detect_conflicts()
        assert result["success"]
        assert result["data"]["total_conflicts"] == 1
        assert result["data"]["conflicts"][0]["segment_id"] == segments[0].id

    def test_resolve_then_apply(self, engine, project_deps):
        """Resolve a conflict (keep_first), then apply successfully."""
        segments = project_deps.current.timelines[0].transcript.segments
        seg_hash = _segments_hash(segments)

        engine._active = {
            "workflow_instance_id": "wfi-resolve",
            "workflow_id": "wf-r",
            "workflow_name": "resolve",
            "timeline_id": "default",
            "segments_hash": seg_hash,
            "accumulated_edits": [
                {"id": "e1", "start": 0.0, "end": 5.5, "target_type": "segment",
                 "target_id": segments[0].id, "action": "delete", "source": "smart_delete",
                 "step_index": 0, "reason": "filler", "priority": 100},
                {"id": "e2", "start": 0.0, "end": 5.5, "target_type": "segment",
                 "target_id": segments[0].id, "action": "keep", "source": "highlight",
                 "step_index": 1, "reason": "key", "priority": 100},
            ],
            "segments_snapshot": [s.model_dump() for s in segments],
        }

        resolve = engine.resolve_conflict(segments[0].id, "keep_first")
        assert resolve["success"]
        assert resolve["data"]["removed_count"] == 1
        assert len(engine._active["accumulated_edits"]) == 1

        apply_result = engine.apply_workflow()
        assert apply_result["success"]
        assert apply_result["data"]["applied_count"] == 1


# ------------------------------------------------------------------
# 4. Preset dispatch validation
# ------------------------------------------------------------------


@pytest.mark.integration
class TestPresetDispatch:
    """Verify preset_id is included in the step dispatch payload (D-43)."""

    def test_preset_id_in_payload(self, engine, project_deps):
        """When a step has preset_id, it appears in the TaskManager payload."""
        wf_def = engine.save_workflow("preset-test", [
            {"type": "llm_smart_delete", "preset_id": "preset-abc123"},
        ])
        wf_id = wf_def["data"]["id"]

        create_calls = []

        def _capture_create(task_type_str, payload):
            create_calls.append((task_type_str, payload))
            return {"success": True, "data": {"id": "task-preset-test", "status": "queued"}}

        engine._task_manager.create_task.side_effect = _capture_create
        _make_task_polling(engine._task_manager, poll_count=2,
                           result={"edits": [], "results": [], "token_usage": {}})

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.5)
        engine.discard_workflow()

        assert len(create_calls) >= 1
        _, payload = create_calls[0]
        assert payload.get("_workflow_preset_id") == "preset-abc123"
        assert payload.get("_workflow_accumulate") is True

    def test_no_preset_id_when_none(self, engine, project_deps):
        """Steps without preset_id do not include _workflow_preset_id in payload."""
        wf_def = engine.save_workflow("no-preset", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        create_calls = []

        def _capture_create(task_type_str, payload):
            create_calls.append((task_type_str, payload))
            return {"success": True, "data": {"id": "task-no-preset", "status": "queued"}}

        engine._task_manager.create_task.side_effect = _capture_create
        _make_task_polling(engine._task_manager, poll_count=2,
                           result={"results": []})

        start = engine.start_workflow(wf_id)
        assert start["success"]

        time.sleep(0.5)
        engine.discard_workflow()

        assert len(create_calls) >= 1
        _, payload = create_calls[0]
        assert payload.get("_workflow_preset_id") is None


# ------------------------------------------------------------------
# 5. Step type mapping + single-workflow constraint
# ------------------------------------------------------------------


@pytest.mark.integration
class TestStepTypeMapping:
    """Verify step types map correctly to TaskType enum values."""

    def test_all_step_types_have_task_type(self):
        for step_type in VALID_STEP_TYPES:
            assert step_type in STEP_TO_TASK_TYPE

    def test_all_step_types_have_display_name(self):
        for step_type in VALID_STEP_TYPES:
            assert step_type in STEP_DISPLAY_NAMES

    def test_task_type_values_are_valid(self):
        from core.models import TaskType
        for _step_type, task_type in STEP_TO_TASK_TYPE.items():
            assert isinstance(task_type, TaskType)

    def test_single_workflow_constraint(self, engine, project_deps):
        """Cannot start a second workflow while one is active (D-27)."""
        wf_def = engine.save_workflow("exclusive-test", [
            {"type": "full_analysis", "preset_id": None},
        ])
        wf_id = wf_def["data"]["id"]

        def _slow_poll(tid):
            return {"success": True, "data": {"id": tid, "status": "running"}}

        engine._task_manager.get_task.side_effect = _slow_poll

        start1 = engine.start_workflow(wf_id)
        assert start1["success"]

        start2 = engine.start_workflow(wf_id)
        assert not start2["success"]
        assert "已有工作流正在运行" in start2["error"]

        engine.cancel_workflow("immediate")
