"""v3.0.4 P2-1 M2-1: start_subtitle_correction track_id passthrough.

Locks (SPEC M2-1 / PLAN P2-1):
- New optional ``track_id`` parameter lands in the task payload verbatim.
- Default call (no track_id) keeps the v3.0.3 payload shape: ``track_id``
  is an empty string (= main track) and every other key is unchanged --
  existing callers are unaffected (R0-4 default-path equivalence).

Mock style follows tests/test_translation_expose.py (MiloCutApi.__new__ +
real ProjectService, worker dispatch disabled).
"""

from __future__ import annotations

import pytest

from core.models import LlmConfig, LlmProvider
from core.project_service import ProjectService
from core.task_manager import TaskManager
from main import MiloCutApi


def _configured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.DEEPSEEK,
        api_key="sk-test",
        model="deepseek-test",
        temperature=0.3,
        timeout=120,
    )


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "core.project_service.get_projects_dir", lambda: tmp_path / "projects"
    )

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})

    instance = MiloCutApi.__new__(MiloCutApi)
    instance._project = service
    instance._emit = lambda event, data=None: None
    instance._task_manager = TaskManager(lambda *a: None)
    instance._debug = False
    return instance


@pytest.fixture
def llm_configured(monkeypatch):
    monkeypatch.setattr(
        "core.llm_service.get_llm_config", lambda: _configured_llm()
    )


@pytest.fixture
def no_worker(monkeypatch):
    monkeypatch.setattr(
        "core.task_manager.TaskManager._ensure_worker", lambda self: None
    )


class TestStartCorrectionTrackIdPayload:
    def test_explicit_track_id_rides_payload(
        self, api, llm_configured, no_worker
    ):
        tm = api._task_manager
        res = api.start_subtitle_correction(track_id="trk_abc12345")
        assert res["success"] is True
        task = tm._tasks[res["data"]["id"]]
        assert task.payload["track_id"] == "trk_abc12345"
        # v3.0.3 payload keys stay intact
        assert task.payload["reference_text"] == ""
        assert task.payload["context_window"] == 3
        assert task.payload["timeline_id"] == (
            api._project.current.active_timeline_id
        )
        assert task.type.value == "llm_subtitle_correction"

    def test_default_call_main_track_equivalence(
        self, api, llm_configured, no_worker
    ):
        """No track_id arg -> payload track_id == "" (main track, v3.0.3)."""
        tm = api._task_manager
        res = api.start_subtitle_correction(reference_text="ref text")
        assert res["success"] is True
        task = tm._tasks[res["data"]["id"]]
        assert task.payload["track_id"] == ""
        assert task.payload["reference_text"] == "ref text"
