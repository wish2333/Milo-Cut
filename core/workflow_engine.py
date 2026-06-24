"""Workflow engine for v2.1.0 Phase 3 -- one-click cleanup workflows.

Manages configurable task chains (rule analysis + P0 + P1 + P2 in any
combination), serial execution with step-level data isolation, conflict
detection (segment-id dimension), and cross-session snapshot persistence.

Architecture (D-18):
    WorkflowEngine = orchestration layer
    TaskManager    = execution layer

The engine does NOT execute analysis directly. It dispatches individual
steps through TaskManager (which calls the existing LLM/rule handlers),
but sets a ``_workflow_accumulate`` flag in the task payload so handlers
return raw results WITHOUT writing to the real project. The engine
accumulates edits into an in-memory snapshot and only applies them when
the user explicitly confirms after conflict resolution.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core import config as _config
from core.events import (
    WORKFLOW_CANCELLED,
    WORKFLOW_COMPLETED,
    WORKFLOW_CONFLICTS_DETECTED,
    WORKFLOW_HEARTBEAT,
    WORKFLOW_STARTED,
    WORKFLOW_STEP_COMPLETED,
    WORKFLOW_STEP_FAILED,
    WORKFLOW_STEP_PROGRESS,
    WORKFLOW_STEP_STARTED,
)
from core.models import TaskType
from core.paths import get_projects_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Valid step types for workflow definitions (D-29).
VALID_STEP_TYPES: set[str] = {
    "llm_smart_delete",
    "llm_subtitle_correction",
    "llm_highlight",
}

#: Mapping from step type to TaskType for dispatch.
STEP_TO_TASK_TYPE: dict[str, TaskType] = {
    "llm_smart_delete": TaskType.LLM_SMART_DELETE,
    "llm_subtitle_correction": TaskType.LLM_SUBTITLE_CORRECTION,
    "llm_highlight": TaskType.LLM_HIGHLIGHT,
}

#: LLM step types (require LLM configuration to start, D-26).
LLM_STEP_TYPES: set[str] = {
    "llm_smart_delete",
    "llm_subtitle_correction",
    "llm_highlight",
}

#: Human-readable names for step types (used in events and UI).
STEP_DISPLAY_NAMES: dict[str, str] = {
    "llm_smart_delete": "P0 智能删除",
    "llm_subtitle_correction": "P1 字幕修正",
    "llm_highlight": "P2 精华提取",
}

#: Heartbeat interval in seconds (D-72).
HEARTBEAT_INTERVAL = 15.0


class WorkflowError(Exception):
    """Raised for workflow-level errors (invalid definition, state, etc.)."""


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """Task-chain orchestration engine.

    Manages workflow definition CRUD, serial execution, step-level data
    isolation (in-memory work copy), conflict detection (segment-id
    dimension), and cross-session snapshot persistence.

    The engine is single-instance, single-active-workflow (D-27).
    """

    def __init__(
        self,
        task_manager,
        project_service,
        emit_fn: Callable[[str, Any], None],
    ) -> None:
        self._task_manager = task_manager
        self._project_service = project_service
        self._emit = emit_fn

        # Active execution state (single workflow, D-27)
        self._lock = threading.RLock()
        self._active: dict | None = None  # snapshot dict of the running workflow
        self._cancel_event = threading.Event()
        self._cancel_mode: str = ""  # "immediate" | "after_current"
        self._current_task_id: str | None = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

        # Failure handling (D-11 interactive)
        self._failure_event = threading.Event()
        self._failure_action: str = ""

    # ------------------------------------------------------------------
    # Workflow definition CRUD (stored in settings.json, D-23)
    # ------------------------------------------------------------------

    def get_workflows(self) -> dict:
        """Return all saved workflow definitions."""
        settings = _config.load_settings()
        workflows = settings.get("workflows", [])
        return {"success": True, "data": workflows}

    def save_workflow(self, name: str, steps: list[dict], workflow_id: str = "") -> dict:
        """Create or update a workflow definition.

        Args:
            name: Human-readable workflow name.
            steps: List of ``{"type": str, "preset_id": str | None}``.
            workflow_id: If provided, update existing; otherwise create new.

        Returns:
            Envelope with the saved workflow definition.
        """
        name = (name or "").strip()
        if not name:
            return {"success": False, "error": "工作流名称不能为空"}

        # Validate steps
        if not steps:
            return {"success": False, "error": "工作流至少需要一个步骤"}

        normalized_steps: list[dict] = []
        for i, step in enumerate(steps):
            step_type = step.get("type", "")
            if step_type not in VALID_STEP_TYPES:
                return {
                    "success": False,
                    "error": f"步骤 {i + 1}: 无效的步骤类型 '{step_type}'",
                }
            normalized_steps.append({
                "type": step_type,
                "preset_id": step.get("preset_id") or None,
            })

        settings = _config.load_settings()
        workflows: list[dict] = list(settings.get("workflows", []))

        now = datetime.now().isoformat()
        if workflow_id:
            # Update existing
            found = False
            for i, wf in enumerate(workflows):
                if wf.get("id") == workflow_id:
                    workflows[i] = {
                        "id": workflow_id,
                        "name": name,
                        "steps": normalized_steps,
                        "created_at": wf.get("created_at", now),
                        "updated_at": now,
                    }
                    found = True
                    break
            if not found:
                return {"success": False, "error": f"工作流不存在: {workflow_id}"}
        else:
            # Create new
            workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
            workflows.append({
                "id": workflow_id,
                "name": name,
                "steps": normalized_steps,
                "created_at": now,
                "updated_at": now,
            })

        settings["workflows"] = workflows
        _config.save_settings(settings)

        # Return the saved definition
        saved = next(wf for wf in workflows if wf["id"] == workflow_id)
        logger.info("Saved workflow '{}' ({})", name, workflow_id)
        return {"success": True, "data": saved}

    def delete_workflow(self, workflow_id: str) -> dict:
        """Delete a workflow definition by id."""
        settings = _config.load_settings()
        workflows: list[dict] = list(settings.get("workflows", []))
        new_workflows = [wf for wf in workflows if wf.get("id") != workflow_id]
        if len(new_workflows) == len(workflows):
            return {"success": False, "error": f"工作流不存在: {workflow_id}"}
        settings["workflows"] = new_workflows
        _config.save_settings(settings)
        logger.info("Deleted workflow {}", workflow_id)
        return {"success": True, "data": {"id": workflow_id}}

    # ------------------------------------------------------------------
    # Snapshot management (D-28, D-30)
    # ------------------------------------------------------------------

    def _snapshot_dir(self) -> Path:
        """Return the directory for workflow snapshot files of the current project."""
        project = self._project_service.current
        if project is None or self._project_service.current_path is None:
            # Fallback to projects root (should not happen during execution)
            return get_projects_dir()
        return self._project_service.current_path.parent

    def _snapshot_path(self, instance_id: str) -> Path:
        return self._snapshot_dir() / f"_workflow_{instance_id}.json"

    def _compute_segments_hash(self, segments: list[dict]) -> str:
        """Compute a content hash over segment ids + start + end + text (D-67)."""
        # Only hash subtitle segments (the ones analysis operates on)
        payload = json.dumps(
            [{"id": s["id"], "s": s["start"], "e": s["end"], "t": s.get("text", "")}
             for s in segments if s.get("type") == "subtitle"],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _create_snapshot(
        self,
        workflow_def: dict,
        timeline_id: str,
    ) -> dict:
        """Create an in-memory snapshot for a new workflow execution."""
        project = self._project_service.current
        if project is None:
            raise WorkflowError("No project open")
        timeline = project.get_timeline(timeline_id)
        if timeline is None:
            raise WorkflowError(f"Timeline {timeline_id} not found")

        segments_snapshot = [s.model_dump() for s in timeline.transcript.segments]
        segments_hash = self._compute_segments_hash(segments_snapshot)

        instance_id = f"wfi-{uuid.uuid4().hex[:12]}"
        snapshot = {
            "workflow_id": workflow_def["id"],
            "workflow_instance_id": instance_id,
            "workflow_name": workflow_def["name"],
            "timeline_id": timeline_id,
            "created_at": datetime.now().isoformat(),
            "status": "running",
            "current_step_index": 0,
            "total_steps": len(workflow_def["steps"]),
            "steps_def": workflow_def["steps"],
            "segments_hash": segments_hash,
            "segments_snapshot": segments_snapshot,
            "accumulated_edits": [],
            "step_results": [
                {"index": i, "type": s["type"], "status": "pending", "edits_count": 0}
                for i, s in enumerate(workflow_def["steps"])
            ],
        }
        self._save_snapshot(snapshot)
        return snapshot

    def _save_snapshot(self, snapshot: dict) -> None:
        """Persist snapshot to disk (cross-session recovery, D-28)."""
        path = self._snapshot_path(snapshot["workflow_instance_id"])
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            import os as _os
            _os.replace(tmp, path)
        except Exception as e:
            logger.warning("Failed to save workflow snapshot: {}", e)

    def _load_snapshot(self, instance_id: str) -> dict | None:
        path = self._snapshot_path(instance_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load workflow snapshot {}: {}", instance_id, e)
            return None

    def _delete_snapshot(self, instance_id: str) -> None:
        path = self._snapshot_path(instance_id)
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.warning("Failed to delete workflow snapshot {}: {}", instance_id, e)

    def find_resumable_snapshots(self) -> list[dict]:
        """Scan the project dir for snapshots in running/paused status.

        Used at app startup to offer cross-session recovery (D-28).
        """
        project = self._project_service.current
        if project is None or self._project_service.current_path is None:
            return []
        proj_dir = self._project_service.current_path.parent
        results: list[dict] = []
        for path in proj_dir.glob("_workflow_*.json"):
            try:
                snap = json.loads(path.read_text(encoding="utf-8"))
                if snap.get("status") in ("running", "paused"):
                    results.append({
                        "workflow_instance_id": snap["workflow_instance_id"],
                        "workflow_name": snap.get("workflow_name", ""),
                        "timeline_id": snap.get("timeline_id", ""),
                        "created_at": snap.get("created_at", ""),
                        "current_step_index": snap.get("current_step_index", 0),
                        "total_steps": snap.get("total_steps", 0),
                    })
            except Exception:
                continue
        return results

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------

    def get_workflow_status(self) -> dict:
        """Return the current workflow execution status + progress (D-20)."""
        with self._lock:
            if self._active is None:
                return {
                    "success": True,
                    "data": {"active": False},
                }
            snap = self._active
            return {
                "success": True,
                "data": {
                    "active": True,
                    "workflow_instance_id": snap["workflow_instance_id"],
                    "workflow_name": snap["workflow_name"],
                    "timeline_id": snap["timeline_id"],
                    "status": snap["status"],
                    "current_step_index": snap["current_step_index"],
                    "total_steps": snap["total_steps"],
                    "cancel_mode": self._cancel_mode,
                    "step_results": snap["step_results"],
                },
            }

    # ------------------------------------------------------------------
    # Conflict detection (D-13, D-15, D-24)
    # ------------------------------------------------------------------

    def detect_conflicts(self) -> dict:
        """Detect EditDecision conflicts in the snapshot's accumulated_edits.

        A conflict = same segment_id has multiple decisions from different
        steps/sources (D-15: segment-id dimension).

        Returns conflicts list with segment text and the competing decisions.
        """
        with self._lock:
            snap = self._active
        if snap is None:
            # Allow conflict detection on a loaded snapshot too
            return {"success": False, "error": "No active workflow snapshot"}

        accumulated = snap.get("accumulated_edits", [])
        seg_map = {s["id"]: s for s in snap.get("segments_snapshot", [])}

        # Group by target_id (segment-level edits only)
        groups: dict[str, list[dict]] = defaultdict(list)
        for edit in accumulated:
            if edit.get("target_type") == "segment" and edit.get("target_id"):
                groups[edit["target_id"]].append(edit)

        conflicts = []
        for seg_id, edits in groups.items():
            if len(edits) < 2:
                continue
            # D-66: conflict = multiple decisions on the same segment
            seg = seg_map.get(seg_id, {})
            conflicts.append({
                "segment_id": seg_id,
                "segment_text": seg.get("text", ""),
                "segment_start": seg.get("start", 0),
                "segment_end": seg.get("end", 0),
                "decisions": [
                    {
                        "edit_id": e.get("id", ""),
                        "action": e.get("action", "delete"),
                        "source": e.get("source", ""),
                        "step_type": e.get("step_type", ""),
                        "step_index": e.get("step_index", 0),
                        "reason": e.get("reason", ""),
                    }
                    for e in edits
                ],
            })

        result = {"conflicts": conflicts, "total_conflicts": len(conflicts)}
        logger.info(
            "Workflow conflict detection: {} conflicts from {} edits",
            len(conflicts), len(accumulated),
        )
        return {"success": True, "data": result}

    # ------------------------------------------------------------------
    # Workflow execution (D-12, D-14, D-18)
    # ------------------------------------------------------------------

    def start_workflow(self, workflow_id: str, timeline_id: str = "") -> dict:
        """Start a workflow: create snapshot + begin serial execution.

        Returns error if a workflow is already active (D-27 single workflow).
        """
        with self._lock:
            if self._active is not None:
                return {
                    "success": False,
                    "error": "已有工作流正在运行，请等待完成或取消后再试",
                }

        # Load workflow definition
        settings = _config.load_settings()
        workflows = settings.get("workflows", [])
        wf_def = next((wf for wf in workflows if wf.get("id") == workflow_id), None)
        if wf_def is None:
            return {"success": False, "error": f"工作流不存在: {workflow_id}"}

        # Validate steps contain valid types
        for i, step in enumerate(wf_def.get("steps", [])):
            if step.get("type") not in VALID_STEP_TYPES:
                return {
                    "success": False,
                    "error": f"步骤 {i + 1}: 无效的步骤类型 '{step.get('type')}'",
                }

        # Resolve timeline
        project = self._project_service.current
        if project is None:
            return {"success": False, "error": "未打开项目"}
        tl_id = timeline_id or project.active_timeline_id
        if project.get_timeline(tl_id) is None:
            return {"success": False, "error": f"Timeline 不存在: {tl_id}"}

        # LLM configuration check (D-26: configurable but not startable)
        has_llm_steps = any(s["type"] in LLM_STEP_TYPES for s in wf_def["steps"])
        if has_llm_steps:
            from core.llm_service import get_llm_config
            config = get_llm_config()
            if not config.is_configured():
                return {
                    "success": False,
                    "error": "工作流包含 LLM 步骤但 LLM 未配置，请先在设置中配置 LLM",
                }

        # Create snapshot
        try:
            snapshot = self._create_snapshot(wf_def, tl_id)
        except WorkflowError as e:
            return {"success": False, "error": str(e)}

        with self._lock:
            self._active = snapshot
            self._cancel_event.clear()
            self._cancel_mode = ""
            self._current_task_id = None
            self._failure_event.clear()
            self._failure_action = ""

        # Emit started event
        self._emit(WORKFLOW_STARTED, {
            "workflow_instance_id": snapshot["workflow_instance_id"],
            "workflow_name": snapshot["workflow_name"],
            "timeline_id": tl_id,
            "total_steps": snapshot["total_steps"],
            "steps": [
                {"index": i, "type": s["type"],
                 "name": STEP_DISPLAY_NAMES.get(s["type"], s["type"])}
                for i, s in enumerate(snapshot["steps_def"])
            ],
        })

        # Start heartbeat (D-72)
        self._start_heartbeat()

        # Start execution thread
        thread = threading.Thread(
            target=self._run_steps,
            args=(snapshot,),
            daemon=True,
        )
        thread.start()

        logger.info(
            "Started workflow '{}' ({}), {} steps",
            wf_def["name"], snapshot["workflow_instance_id"],
            snapshot["total_steps"],
        )
        return {"success": True, "data": {
            "workflow_instance_id": snapshot["workflow_instance_id"],
            "total_steps": snapshot["total_steps"],
        }}

    def _run_steps(self, snapshot: dict) -> None:
        """Execute steps serially (runs in a background thread)."""
        instance_id = snapshot["workflow_instance_id"]
        total = snapshot["total_steps"]

        try:
            for step_index in range(snapshot["current_step_index"], total):
                # Check cancellation
                with self._lock:
                    if self._cancel_event.is_set():
                        break
                    # "after_current" mode: stop if current step already done
                    if self._cancel_mode == "after_current" and step_index > snapshot["current_step_index"]:
                        break

                step_def = snapshot["steps_def"][step_index]
                step_type = step_def["type"]
                step_name = STEP_DISPLAY_NAMES.get(step_type, step_type)

                # Emit step started (D-70: distinguish queued vs running)
                self._emit(WORKFLOW_STEP_STARTED, {
                    "workflow_instance_id": instance_id,
                    "step_index": step_index,
                    "step_type": step_type,
                    "step_name": step_name,
                    "status": "queued",  # will become "running" when task starts
                })

                # Dispatch through TaskManager
                result = self._dispatch_step(snapshot, step_index, step_def)
                if result is None:
                    # Cancelled
                    break

                if not result.get("success"):
                    # Step failed -- emit and wait for failure handling (D-11)
                    error = result.get("error", "步骤执行失败")
                    self._emit(WORKFLOW_STEP_FAILED, {
                        "workflow_instance_id": instance_id,
                        "step_index": step_index,
                        "step_type": step_type,
                        "step_name": step_name,
                        "error": error,
                    })
                    action = self._wait_for_failure_action()
                    if action == "retry":
                        # Retry once
                        result = self._dispatch_step(snapshot, step_index, step_def)
                        if result is None:
                            break
                        if not result.get("success"):
                            # Still failing after retry, abort
                            logger.warning(
                                "Workflow {} step {} retry failed, aborting",
                                instance_id, step_index,
                            )
                            break
                    elif action == "skip":
                        # Mark as skipped, continue
                        snapshot["step_results"][step_index]["status"] = "skipped"
                        snapshot["current_step_index"] = step_index + 1
                        with self._lock:
                            self._active = snapshot
                        self._save_snapshot(snapshot)
                        continue
                    else:
                        # abort
                        break

                # Step succeeded -- accumulate results
                edits = self._extract_edits_from_result(result.get("data", {}), step_type, step_index)
                snapshot["accumulated_edits"].extend(edits)
                snapshot["step_results"][step_index]["status"] = "completed"
                snapshot["step_results"][step_index]["edits_count"] = len(edits)
                snapshot["current_step_index"] = step_index + 1

                with self._lock:
                    self._active = snapshot
                self._save_snapshot(snapshot)

                self._emit(WORKFLOW_STEP_COMPLETED, {
                    "workflow_instance_id": instance_id,
                    "step_index": step_index,
                    "step_type": step_type,
                    "step_name": step_name,
                    "edits_count": len(edits),
                })

            # Execution finished -- determine outcome
            with self._lock:
                was_cancelled = self._cancel_event.is_set()
                self._current_task_id = None

            if was_cancelled:
                snapshot["status"] = "cancelled"
                self._save_snapshot(snapshot)
                self._emit(WORKFLOW_CANCELLED, {
                    "workflow_instance_id": instance_id,
                    "completed_steps": snapshot["current_step_index"],
                    "total_steps": total,
                })
            else:
                snapshot["status"] = "completed"
                self._save_snapshot(snapshot)
                self._emit(WORKFLOW_COMPLETED, {
                    "workflow_instance_id": instance_id,
                    "workflow_name": snapshot["workflow_name"],
                    "total_edits": len(snapshot["accumulated_edits"]),
                    "step_results": snapshot["step_results"],
                })

                # Run conflict detection (D-24: one-shot after all steps)
                conflict_result = self.detect_conflicts()
                self._emit(WORKFLOW_CONFLICTS_DETECTED, {
                    "workflow_instance_id": instance_id,
                    "conflicts": conflict_result.get("data", {}).get("conflicts", []),
                    "total_conflicts": conflict_result.get("data", {}).get("total_conflicts", 0),
                })

        except Exception as e:
            logger.exception("Workflow {} crashed", instance_id)
            snapshot["status"] = "failed"
            self._save_snapshot(snapshot)
            self._emit(WORKFLOW_STEP_FAILED, {
                "workflow_instance_id": instance_id,
                "step_index": snapshot.get("current_step_index", 0),
                "step_type": "",
                "step_name": "",
                "error": f"工作流内部错误: {e}",
            })
        finally:
            self._stop_heartbeat()

    def _dispatch_step(self, snapshot: dict, step_index: int, step_def: dict) -> dict | None:
        """Dispatch a single step through TaskManager and wait for completion.

        Returns None if cancelled, otherwise the task result envelope.
        """
        instance_id = snapshot["workflow_instance_id"]
        step_type = step_def["type"]
        task_type_str = STEP_TO_TASK_TYPE[step_type].value

        # Build payload with workflow accumulation flag
        payload: dict[str, Any] = {
            "timeline_id": snapshot["timeline_id"],
            "_workflow_accumulate": True,
            "_workflow_instance_id": instance_id,
            "_workflow_step_index": step_index,
            "_workflow_step_type": step_type,
        }

        # Apply preset if specified (D-43, D-45)
        preset_id = step_def.get("preset_id")
        if preset_id:
            payload["_workflow_preset_id"] = preset_id

        # Create task
        create_result = self._task_manager.create_task(task_type_str, payload)
        if not create_result.get("success"):
            return create_result

        task_id = create_result["data"]["id"]
        with self._lock:
            self._current_task_id = task_id

        # Emit running status
        self._emit(WORKFLOW_STEP_STARTED, {
            "workflow_instance_id": instance_id,
            "step_index": step_index,
            "step_type": step_type,
            "step_name": STEP_DISPLAY_NAMES.get(step_type, step_type),
            "status": "running",
            "task_id": task_id,
        })

        # Wait for task completion by polling
        while True:
            # Check cancellation
            with self._lock:
                if self._cancel_event.is_set() and self._cancel_mode == "immediate":
                    self._task_manager.cancel_task(task_id)

            task_result = self._task_manager.get_task(task_id)
            if not task_result.get("success"):
                return {"success": False, "error": "Task not found after dispatch"}

            task_data = task_result["data"]
            status = task_data.get("status")

            if status == "completed":
                return {"success": True, "data": task_data.get("result", {})}
            elif status == "failed":
                return {"success": False, "error": task_data.get("error", "Task failed")}
            elif status == "cancelled":
                return None

            # Emit progress (forward task progress as step progress)
            progress = task_data.get("progress", {})
            pct = progress.get("percent", 0) if progress else 0
            msg = progress.get("message", "") if progress else ""
            if pct or msg:
                self._emit(WORKFLOW_STEP_PROGRESS, {
                    "workflow_instance_id": instance_id,
                    "step_index": step_index,
                    "percent": pct,
                    "message": msg,
                })

            time.sleep(0.1)

    def _extract_edits_from_result(
        self, result: dict, step_type: str, step_index: int,
    ) -> list[dict]:
        """Extract EditDecision dicts from a step's task result.

        Different step types return results in different shapes:
        - smart_delete / highlight: ``{"edits": [edit dicts], ...}`` -- use directly
        - subtitle_correction: ``{"corrections": [...]}`` -- no segment-level edits (text fix)
        """
        edits: list[dict] = []

        if step_type in ("llm_smart_delete", "llm_highlight"):
            # Handlers already build edit dicts in workflow mode
            raw_edits = result.get("edits", [])
            seen_ids: set[str] = set()
            for e in raw_edits:
                edit = dict(e)
                # Defensive: if id collides within same batch, append _dup{N}
                if edit.get("id") in seen_ids:
                    n = 2
                    while f"{edit['id']}_dup{n}" in seen_ids:
                        n += 1
                    edit["id"] = f"{edit['id']}_dup{n}"
                seen_ids.add(edit["id"])
                edit["step_type"] = step_type
                edit["step_index"] = step_index
                edits.append(edit)

        # subtitle_correction produces no segment-level EditDecisions
        return edits

    # ------------------------------------------------------------------
    # Failure handling (D-11)
    # ------------------------------------------------------------------

    def _wait_for_failure_action(self) -> str:
        """Block until the frontend responds with retry/skip/abort."""
        self._failure_event.wait()
        action = self._failure_action
        self._failure_event.clear()
        self._failure_action = ""
        return action

    def handle_step_failure(self, action: str) -> dict:
        """Respond to a step failure (called by frontend after user choice).

        Args:
            action: "retry" | "skip" | "abort"
        """
        if action not in ("retry", "skip", "abort"):
            return {"success": False, "error": f"无效的操作: {action}"}
        with self._lock:
            self._failure_action = action
            self._failure_event.set()
        return {"success": True, "data": {"action": action}}

    # ------------------------------------------------------------------
    # Cancellation (D-22)
    # ------------------------------------------------------------------

    def cancel_workflow(self, mode: str = "immediate") -> dict:
        """Cancel the active workflow.

        Args:
            mode: "immediate" -- cancel current step and stop immediately.
                  "after_current" -- let current step finish, then stop (D-71).
        """
        with self._lock:
            if self._active is None:
                return {"success": False, "error": "没有正在运行的工作流"}
            if mode not in ("immediate", "after_current"):
                return {"success": False, "error": f"无效的取消模式: {mode}"}

            self._cancel_mode = mode
            self._cancel_event.set()

            if mode == "immediate" and self._current_task_id:
                self._task_manager.cancel_task(self._current_task_id)

        logger.info("Workflow cancel requested (mode={})", mode)
        return {"success": True, "data": {"mode": mode}}

    # ------------------------------------------------------------------
    # Heartbeat (D-72)
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()

    def _heartbeat_loop(self) -> None:
        instance_id = ""
        with self._lock:
            if self._active:
                instance_id = self._active["workflow_instance_id"]
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL):
            self._emit(WORKFLOW_HEARTBEAT, {
                "workflow_instance_id": instance_id,
                "timestamp": datetime.now().isoformat(),
            })

    # ------------------------------------------------------------------
    # Apply / Discard (D-14, D-53, D-65, D-67)
    # ------------------------------------------------------------------

    def apply_workflow(self) -> dict:
        """Apply accumulated edits to the real project.

        Validates segments hash (D-67) before applying. The edits are written
        as EditDecisions with source ``workflow:<wf_id>:<name>`` (D-65).
        """
        with self._lock:
            snap = self._active

        if snap is None:
            return {"success": False, "error": "没有活跃的工作流快照"}

        project = self._project_service.current
        if project is None:
            return {"success": False, "error": "未打开项目"}

        timeline = project.get_timeline(snap["timeline_id"])
        if timeline is None:
            return {"success": False, "error": "Timeline 不存在"}

        # Hash validation (D-67: pessimistic lock + content hash)
        current_segments = [s.model_dump() for s in timeline.transcript.segments]
        current_hash = self._compute_segments_hash(current_segments)
        if current_hash != snap.get("segments_hash"):
            return {
                "success": False,
                "error": "Timeline 已发生显著变化，工作流已失效，请重新创建",
            }

        # Build EditDecision models from accumulated edits
        from core.models import EditDecision
        source = f"workflow:{snap['workflow_id']}:{snap['workflow_name']}"
        existing_edits = list(timeline.edits)
        new_edits: list[EditDecision] = []

        for e in snap["accumulated_edits"]:
            try:
                edit = EditDecision(
                    id=e["id"],
                    start=e["start"],
                    end=e["end"],
                    action=e.get("action", "delete"),
                    source=source,
                    analysis_id=e.get("analysis_id"),
                    status="pending",
                    priority=e.get("priority", 100),
                    target_type=e.get("target_type", "range"),
                    target_id=e.get("target_id"),
                )
                new_edits.append(edit)
            except Exception as ex:
                logger.warning("Skipping invalid edit in workflow apply: {} ({})", e, ex)

        # Apply to project
        updated_timeline = timeline.model_copy(update={
            "edits": existing_edits + new_edits,
        })
        new_timelines = [
            updated_timeline if t.id == timeline.id else t
            for t in project.timelines
        ]
        self._project_service.current = project.model_copy(update={
            "timelines": new_timelines,
        })

        # Save project
        self._project_service.save_project()

        # Clean up snapshot
        instance_id = snap["workflow_instance_id"]
        self._delete_snapshot(instance_id)
        with self._lock:
            self._active = None

        logger.info(
            "Applied workflow {} ({} edits) to project",
            snap["workflow_name"], len(new_edits),
        )
        return {
            "success": True,
            "data": {
                "applied_count": len(new_edits),
                "source": source,
                "project": self._project_service.current.model_dump(),
            },
        }

    def discard_workflow(self) -> dict:
        """Discard the workflow snapshot without applying (D-17 skip path)."""
        with self._lock:
            snap = self._active
            if snap is None:
                return {"success": False, "error": "没有活跃的工作流快照"}
            instance_id = snap["workflow_instance_id"]
            self._active = None

        self._delete_snapshot(instance_id)
        logger.info("Discarded workflow {}", instance_id)
        return {"success": True, "data": {"discarded": True}}

    # ------------------------------------------------------------------
    # Conflict resolution (D-16, D-17, D-66)
    # ------------------------------------------------------------------

    def resolve_conflict(self, segment_id: str, resolution: str) -> dict:
        """Resolve a single conflict by removing non-selected decisions.

        Args:
            segment_id: The segment with conflicting decisions.
            resolution: "keep_first" | "keep_last" | "keep_all".
                        keep_first = keep the earliest step's decision.
                        keep_last  = keep the latest step's decision.
                        keep_all   = keep all (D-66: both decisions coexist).
        """
        with self._lock:
            snap = self._active
        if snap is None:
            return {"success": False, "error": "没有活跃的工作流快照"}

        if resolution not in ("keep_first", "keep_last", "keep_all"):
            return {"success": False, "error": f"无效的解决方式: {resolution}"}

        if resolution == "keep_all":
            # D-66: both decisions remain independently
            return {"success": True, "data": {"kept": "all"}}

        accumulated = snap["accumulated_edits"]
        # Find edits for this segment, sorted by step_index
        seg_edits = [
            (i, e) for i, e in enumerate(accumulated)
            if e.get("target_id") == segment_id and e.get("target_type") == "segment"
        ]
        if not seg_edits:
            return {"success": False, "error": f"未找到 segment 冲突: {segment_id}"}

        seg_edits.sort(key=lambda x: x[1].get("step_index", 0))
        keep_index = seg_edits[0][0] if resolution == "keep_first" else seg_edits[-1][0]
        remove_indices = {idx for idx, _ in seg_edits if idx != keep_index}

        snap["accumulated_edits"] = [
            e for i, e in enumerate(accumulated) if i not in remove_indices
        ]
        with self._lock:
            self._active = snap
        self._save_snapshot(snap)

        logger.info(
            "Resolved conflict for segment {} ({}): removed {} edits",
            segment_id, resolution, len(remove_indices),
        )
        return {"success": True, "data": {
            "segment_id": segment_id,
            "removed_count": len(remove_indices),
        }}
