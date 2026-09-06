"""Tests for the v2.1.0 Phase 3 WorkflowEngine.

Covers:
- Workflow definition CRUD (save/get/delete + validation)
- Snapshot creation and persistence
- Conflict detection (segment-id dimension)
- Conflict resolution (keep_first/keep_last/keep_all)
- Failure handling (retry/skip/abort)
- Cancel (immediate/after_current)
- Apply/discard workflow
- find_resumable_snapshots (cross-session recovery)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.workflow_engine import (
    LLM_STEP_TYPES,
    VALID_STEP_TYPES,
    WorkflowEngine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Redirect settings.json to an isolated temp file."""
    import copy as _copy
    import json as _json
    import os as _os

    from core.config import _DEFAULT_SETTINGS

    settings_path = tmp_path / "settings.json"

    def _load() -> dict:
        if not settings_path.exists():
            return _copy.deepcopy(_DEFAULT_SETTINGS)
        try:
            data = _json.loads(settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return _copy.deepcopy(_DEFAULT_SETTINGS)
        merged = _copy.deepcopy(_DEFAULT_SETTINGS)
        merged.update(data)
        return merged

    def _save(settings: dict) -> None:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = settings_path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        _os.replace(tmp, settings_path)

    monkeypatch.setattr("core.config.load_settings", _load)
    monkeypatch.setattr("core.config.save_settings", _save)
    return settings_path


@pytest.fixture
def mock_deps(tmp_path):
    """Create WorkflowEngine with mocked TaskManager + ProjectService."""
    task_mgr = MagicMock()
    task_mgr.create_task.return_value = {
        "success": True,
        "data": {"id": "task-fake-01", "status": "queued"},
    }

    project_svc = MagicMock()
    project_svc.current_path = tmp_path / "projects" / "test" / "project.json"
    project_svc.current_path.parent.mkdir(parents=True, exist_ok=True)

    emit_fn = MagicMock()
    return task_mgr, project_svc, emit_fn


@pytest.fixture
def engine(mock_deps, isolated_settings):
    """WorkflowEngine with isolated settings + mock deps."""
    task_mgr, project_svc, emit_fn = mock_deps
    return WorkflowEngine(task_mgr, project_svc, emit_fn)


def _make_project_with_segments():
    """Create a mock project with subtitle segments."""
    from tests.mocks.factories import make_segment

    segs = [
        make_segment(id="seg-1", start=0.0, end=5.0, text="hello world"),
        make_segment(id="seg-2", start=5.0, end=10.0, text="another segment"),
    ]
    from tests.mocks.factories import make_project

    return make_project(segments=segs)


# ------------------------------------------------------------------
# Workflow definition CRUD
# ------------------------------------------------------------------


class TestWorkflowCRUD:
    def test_get_empty(self, engine):
        result = engine.get_workflows()
        assert result["success"]
        assert result["data"] == []

    def test_save_and_get(self, engine):
        steps = [
            {"type": "llm_smart_delete", "preset_id": None},
            {"type": "llm_smart_delete", "preset_id": None},
        ]
        result = engine.save_workflow("深度清理", steps)
        assert result["success"]
        wf = result["data"]
        assert wf["name"] == "深度清理"
        assert wf["id"].startswith("wf-")
        assert len(wf["steps"]) == 2

        # Verify it shows up in get_workflows
        all_wf = engine.get_workflows()
        assert len(all_wf["data"]) == 1
        assert all_wf["data"][0]["name"] == "深度清理"

    def test_save_empty_name_fails(self, engine):
        result = engine.save_workflow("", [{"type": "llm_smart_delete"}])
        assert not result["success"]

    def test_save_empty_steps_fails(self, engine):
        result = engine.save_workflow("test", [])
        assert not result["success"]

    def test_save_invalid_step_type_fails(self, engine):
        result = engine.save_workflow("test", [{"type": "invalid_type"}])
        assert not result["success"]
        assert "无效的步骤类型" in result["error"]

    def test_save_search_not_allowed(self, engine):
        """P3 semantic search is excluded from workflows (D-31)."""
        result = engine.save_workflow("test", [{"type": "llm_semantic_search"}])
        assert not result["success"]

    def test_update_existing(self, engine):
        # Create
        result = engine.save_workflow("v1", [{"type": "llm_smart_delete"}])
        wf_id = result["data"]["id"]

        # Update
        result2 = engine.save_workflow(
            "v2", [{"type": "llm_smart_delete"}, {"type": "llm_highlight"}], workflow_id=wf_id,
        )
        assert result2["success"]
        assert result2["data"]["name"] == "v2"
        assert len(result2["data"]["steps"]) == 2

    def test_delete(self, engine):
        result = engine.save_workflow("test", [{"type": "llm_smart_delete"}])
        wf_id = result["data"]["id"]

        del_result = engine.delete_workflow(wf_id)
        assert del_result["success"]

        all_wf = engine.get_workflows()
        assert len(all_wf["data"]) == 0

    def test_delete_nonexistent(self, engine):
        result = engine.delete_workflow("wf-nonexistent")
        assert not result["success"]

    def test_valid_step_types_complete(self):
        """All 3 valid step types are present."""
        assert VALID_STEP_TYPES == {
            "llm_smart_delete",
            "llm_subtitle_correction", "llm_highlight",
        }

    def test_llm_step_types(self):
        """LLM steps excluded search/llm_smart_delete (D-26, D-31)."""
        assert LLM_STEP_TYPES == {
            "llm_smart_delete", "llm_subtitle_correction", "llm_highlight",
        }


# ------------------------------------------------------------------
# Snapshot + conflict detection
# ------------------------------------------------------------------


class TestSnapshotAndConflicts:
    def test_detect_conflicts_no_active(self, engine):
        """No active snapshot -> error."""
        result = engine.detect_conflicts()
        assert not result["success"]

    def test_detect_conflicts_none(self, engine):
        """Single edit per segment -> no conflict."""
        engine._active = {
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": "seg-1",
                 "action": "delete", "source": "llm_smart", "step_index": 0},
            ],
            "segments_snapshot": [
                {"id": "seg-1", "start": 0, "end": 5, "text": "hello", "type": "subtitle"},
            ],
        }
        result = engine.detect_conflicts()
        assert result["success"]
        assert result["data"]["total_conflicts"] == 0

    def test_detect_conflicts_found(self, engine):
        """Same segment + 2 decisions from different steps -> conflict."""
        engine._active = {
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": "seg-1",
                 "action": "delete", "source": "llm_smart", "step_index": 0,
                 "reason": "redundant"},
                {"id": "e2", "target_type": "segment", "target_id": "seg-1",
                 "action": "keep", "source": "llm_highlight", "step_index": 1,
                 "reason": "high density"},
            ],
            "segments_snapshot": [
                {"id": "seg-1", "start": 0, "end": 5, "text": "hello", "type": "subtitle"},
            ],
        }
        result = engine.detect_conflicts()
        assert result["success"]
        assert result["data"]["total_conflicts"] == 1
        conflict = result["data"]["conflicts"][0]
        assert conflict["segment_id"] == "seg-1"
        assert conflict["segment_text"] == "hello"
        assert len(conflict["decisions"]) == 2

    def test_detect_conflicts_range_excluded(self, engine):
        """target_type=range edits are not included in conflict detection."""
        engine._active = {
            "accumulated_edits": [
                {"id": "e1", "target_type": "range", "target_id": None, "action": "delete"},
                {"id": "e2", "target_type": "range", "target_id": None, "action": "keep"},
            ],
            "segments_snapshot": [],
        }
        result = engine.detect_conflicts()
        assert result["data"]["total_conflicts"] == 0


class TestConflictResolution:
    def test_resolve_keep_all(self, engine):
        """D-66: keep_all retains both decisions."""
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": "seg-1",
                 "action": "delete", "step_index": 0},
                {"id": "e2", "target_type": "segment", "target_id": "seg-1",
                 "action": "keep", "step_index": 1},
            ],
        }
        result = engine.resolve_conflict("seg-1", "keep_all")
        assert result["success"]
        # Both edits still present
        assert len(engine._active["accumulated_edits"]) == 2

    def test_resolve_keep_first(self, engine):
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": "seg-1",
                 "action": "delete", "step_index": 0},
                {"id": "e2", "target_type": "segment", "target_id": "seg-1",
                 "action": "keep", "step_index": 1},
            ],
        }
        result = engine.resolve_conflict("seg-1", "keep_first")
        assert result["success"]
        assert result["data"]["removed_count"] == 1
        # Only first edit remains
        remaining = engine._active["accumulated_edits"]
        assert len(remaining) == 1
        assert remaining[0]["id"] == "e1"

    def test_resolve_keep_last(self, engine):
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "accumulated_edits": [
                {"id": "e1", "target_type": "segment", "target_id": "seg-1",
                 "action": "delete", "step_index": 0},
                {"id": "e2", "target_type": "segment", "target_id": "seg-1",
                 "action": "keep", "step_index": 1},
            ],
        }
        result = engine.resolve_conflict("seg-1", "keep_last")
        assert result["success"]
        remaining = engine._active["accumulated_edits"]
        assert len(remaining) == 1
        assert remaining[0]["id"] == "e2"

    def test_resolve_invalid_resolution(self, engine):
        engine._active = {"accumulated_edits": []}
        result = engine.resolve_conflict("seg-1", "invalid")
        assert not result["success"]


# ------------------------------------------------------------------
# Failure handling
# ------------------------------------------------------------------


class TestFailureHandling:
    def test_handle_valid_actions(self, engine):
        for action in ("retry", "skip", "abort"):
            result = engine.handle_step_failure(action)
            assert result["success"]
            assert result["data"]["action"] == action

    def test_handle_invalid_action(self, engine):
        result = engine.handle_step_failure("invalid")
        assert not result["success"]


# ------------------------------------------------------------------
# Cancel
# ------------------------------------------------------------------


class TestCancel:
    def test_cancel_no_active(self, engine):
        result = engine.cancel_workflow("immediate")
        assert not result["success"]

    def test_cancel_immediate(self, engine):
        engine._active = {"workflow_instance_id": "wfi-x"}
        engine._current_task_id = "task-123"
        result = engine.cancel_workflow("immediate")
        assert result["success"]
        assert engine._cancel_event.is_set()
        assert engine._cancel_mode == "immediate"
        # Should have cancelled the current task
        engine._task_manager.cancel_task.assert_called_once_with("task-123")

    def test_cancel_after_current(self, engine):
        engine._active = {"workflow_instance_id": "wfi-x"}
        engine._current_task_id = "task-123"
        result = engine.cancel_workflow("after_current")
        assert result["success"]
        assert engine._cancel_mode == "after_current"
        # Should NOT cancel the current task yet
        engine._task_manager.cancel_task.assert_not_called()

    def test_cancel_invalid_mode(self, engine):
        engine._active = {"workflow_instance_id": "wfi-x"}
        result = engine.cancel_workflow("invalid")
        assert not result["success"]


# ------------------------------------------------------------------
# Apply / Discard
# ------------------------------------------------------------------


class TestApplyDiscard:
    def test_discard_no_active(self, engine):
        result = engine.discard_workflow()
        assert not result["success"]

    def test_discard_clears_state(self, engine):
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "workflow_id": "wf-1",
            "workflow_name": "test",
            "timeline_id": "default",
        }
        result = engine.discard_workflow()
        assert result["success"]
        assert engine._active is None

    def test_apply_no_active(self, engine):
        """v2.2.0: stub is idempotent — no active workflow returns success, applied_count 0."""
        result = engine.apply_workflow()
        assert result["success"]
        assert result["data"]["applied_count"] == 0

    def test_apply_clears_active(self, engine):
        """v2.2.0: non-sandbox stub clears _active and deletes snapshot, writes no project state."""
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "workflow_id": "wf-1",
            "workflow_name": "test",
            "timeline_id": "default",
        }
        result = engine.apply_workflow()
        assert result["success"]
        assert result["data"]["applied_count"] == 0
        # Stub must not touch project state — only clear the active workflow.
        assert engine._active is None

    def test_apply_does_not_write_project(self, engine, mock_deps):
        """v2.2.0: apply must NOT read or write project_svc.current (B5)."""
        _task_mgr, project_svc, _emit = mock_deps
        # project_svc.current intentionally left as the MagicMock default;
        # the stub must not dereference it.
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "workflow_id": "wf-1",
            "workflow_name": "test",
            "timeline_id": "default",
        }
        result = engine.apply_workflow()
        assert result["success"]
        # No save_project / current write attempted on the project service
        project_svc.save_project.assert_not_called()
        assert engine._active is None


# ------------------------------------------------------------------
# Status query
# ------------------------------------------------------------------


class TestStatus:
    def test_no_active(self, engine):
        result = engine.get_workflow_status()
        assert result["success"]
        assert result["data"]["active"] is False

    def test_active(self, engine):
        engine._active = {
            "workflow_instance_id": "wfi-test",
            "workflow_name": "test",
            "timeline_id": "default",
            "status": "running",
            "current_step_index": 1,
            "total_steps": 3,
            "step_results": [
                {"index": 0, "type": "llm_smart_delete", "status": "completed", "edits_count": 5},
                {"index": 1, "type": "llm_smart_delete", "status": "running", "edits_count": 0},
                {"index": 2, "type": "llm_highlight", "status": "pending", "edits_count": 0},
            ],
        }
        result = engine.get_workflow_status()
        assert result["data"]["active"] is True
        assert result["data"]["current_step_index"] == 1
        assert result["data"]["total_steps"] == 3
        assert len(result["data"]["step_results"]) == 3


# ------------------------------------------------------------------
# Cross-session recovery
# ------------------------------------------------------------------


class TestResumableSnapshots:
    def test_find_resumable_none(self, engine, mock_deps):
        """No snapshots -> empty list."""
        _task_mgr, project_svc, _emit = mock_deps
        project_svc.current = None
        assert engine.find_resumable_snapshots() == []

    def test_find_resumable_found(self, engine, mock_deps):
        """A running snapshot file should be found."""
        _task_mgr, project_svc, _emit = mock_deps
        project_svc.current = _make_project_with_segments()

        # Write a snapshot file
        snap_path = project_svc.current_path.parent / "_workflow_wfi-test.json"
        snap_path.write_text(json.dumps({
            "workflow_instance_id": "wfi-test",
            "workflow_name": "test",
            "timeline_id": "default",
            "created_at": "2025-01-01T00:00:00",
            "status": "running",
            "current_step_index": 1,
            "total_steps": 3,
        }), encoding="utf-8")

        results = engine.find_resumable_snapshots()
        assert len(results) == 1
        assert results[0]["workflow_instance_id"] == "wfi-test"

    def test_find_resumable_excludes_completed(self, engine, mock_deps):
        """Completed snapshots are not resumable."""
        _task_mgr, project_svc, _emit = mock_deps
        project_svc.current = _make_project_with_segments()

        snap_path = project_svc.current_path.parent / "_workflow_wfi-done.json"
        snap_path.write_text(json.dumps({
            "workflow_instance_id": "wfi-done",
            "status": "completed",
        }), encoding="utf-8")

        assert engine.find_resumable_snapshots() == []


# ------------------------------------------------------------------
# v3.0.0 M3-6: failure rollback (two-step workflow, step 2 fails)
# ------------------------------------------------------------------


@pytest.fixture
def real_svc(tmp_path, monkeypatch):
    """Real ProjectService (patched paths) for rollback semantics checks."""
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    from core.project_service import ProjectService

    service = ProjectService()
    service.create_project("w", "/fake/media.mp4", {"duration": 10.0})
    # Seed subtitle segments (make_project keeps the create_project path/dir).
    service._current = _make_project_with_segments()
    return service


def _real_engine(real_svc):
    from core.workflow_engine import WorkflowEngine

    return WorkflowEngine(MagicMock(), real_svc, MagicMock())


def _two_step_def():
    return {
        "id": "wf-rollback",
        "name": "回滚测试",
        "steps": [
            {"type": "llm_smart_delete", "preset_id": None},
            {"type": "llm_subtitle_correction", "preset_id": None},
        ],
    }


def _wire_two_step_flow(engine, real_svc, observed):
    """Mock the task layer: step 1 mutates the project then completes,
    step 2 fails -- mimicking the v2.2.0 non-sandbox handler contract."""
    task_mgr = engine._task_manager
    task_mgr.create_task.side_effect = [
        {"success": True, "data": {"id": "t1", "status": "queued"}},
        {"success": True, "data": {"id": "t2", "status": "queued"}},
    ]

    def fake_get_task(task_id):
        if task_id == "t1":
            if not observed.get("step1_applied"):
                observed["step1_applied"] = True
                res = real_svc.update_segment_text("seg-1", "步骤一效果")
                assert res["success"]
            return {"success": True, "data": {"status": "completed", "result": {}}}
        if task_id == "t2":
            observed["rev_at_failure"] = real_svc._revision
            return {"success": True, "data": {"status": "failed", "error": "步骤二失败"}}
        return {"success": False, "error": "unknown task"}

    task_mgr.get_task.side_effect = fake_get_task


class TestFailureRollback:
    def test_rollback_step_keeps_step1_effect(self, real_svc, isolated_settings):
        """两步流第二步失败 → 回滚本步：第一步效果保留，revision 递增。"""
        engine = _real_engine(real_svc)
        observed: dict = {}
        _wire_two_step_flow(engine, real_svc, observed)
        snapshot = engine._create_snapshot(_two_step_def(), "default")
        rev_before = real_svc._revision

        # Pre-seed the failure answer so _wait_for_failure_action returns fast.
        engine._failure_action = "rollback_step"
        engine._failure_event.set()

        engine._run_steps(snapshot)

        # Step-1 effect survives (rollback target = before step 2).
        seg1 = next(
            s for s in real_svc.active_timeline.transcript.segments
            if s.id == "seg-1"
        )
        assert seg1.text == "步骤一效果"
        # Revision strictly increased across the rollback (M5 assertion).
        assert real_svc._revision > observed["rev_at_failure"] > rev_before
        # Terminal state + event.
        assert snapshot["status"] == "rolled_back"
        assert snapshot["rolled_back_to_step"] == 1
        assert snapshot["step_results"][1]["status"] == "failed"
        emitted = [c.args[0] for c in engine._emit.call_args_list]
        assert "workflow:rolled_back" in emitted

    def test_rollback_all_reverts_step1_effect(self, real_svc, isolated_settings):
        """整体回滚：第一步效果一并撤销。"""
        engine = _real_engine(real_svc)
        observed: dict = {}
        _wire_two_step_flow(engine, real_svc, observed)
        snapshot = engine._create_snapshot(_two_step_def(), "default")

        engine._failure_action = "rollback_all"
        engine._failure_event.set()

        engine._run_steps(snapshot)

        seg1 = next(
            s for s in real_svc.active_timeline.transcript.segments
            if s.id == "seg-1"
        )
        assert seg1.text == "hello world"  # original factory text
        assert snapshot["rolled_back_to_step"] == 0

    def test_cross_session_snapshot_still_rollbackable(self, real_svc, isolated_settings):
        """跨会话：新 engine 实例从磁盘加载快照后仍可回滚。"""
        engine = _real_engine(real_svc)
        snapshot = engine._create_snapshot(_two_step_def(), "default")

        # Session A: step-boundary snapshot persisted, then step 1 runs.
        snapshot["layer_snapshots"]["1"] = engine._capture_layer_snapshot("default")
        engine._save_snapshot(snapshot)
        assert real_svc.update_segment_text("seg-1", "步骤一效果")["success"]

        # Session B: fresh engine instance, load from disk, roll back.
        engine_b = _real_engine(real_svc)
        loaded = engine_b._load_snapshot(snapshot["workflow_instance_id"])
        assert loaded is not None
        assert "1" in loaded["layer_snapshots"]
        res = engine_b._rollback_to_step(loaded, 0)
        assert res["success"]
        seg1 = next(
            s for s in real_svc.active_timeline.transcript.segments
            if s.id == "seg-1"
        )
        assert seg1.text == "hello world"

    def test_rollback_missing_layer_snapshot_fails_gracefully(self, real_svc, isolated_settings):
        engine = _real_engine(real_svc)
        snapshot = engine._create_snapshot(_two_step_def(), "default")
        snapshot["layer_snapshots"] = {}  # legacy snapshot without captures
        res = engine._rollback_to_step(snapshot, 1)
        assert not res["success"]
        assert "缺少" in res["error"]

    def test_handle_step_failure_accepts_rollback_actions(self, real_svc, isolated_settings):
        engine = _real_engine(real_svc)
        assert engine.handle_step_failure("rollback_step")["success"]
        assert engine.handle_step_failure("rollback_all")["success"]
        assert not engine.handle_step_failure("rollback_typo")["success"]
