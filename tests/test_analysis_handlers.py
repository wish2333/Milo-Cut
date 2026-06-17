"""v2.1.1 M1-1: Analysis handlers must read segments from active_timeline.

Regression tests for the ``AttributeError: 'Project' object has no attribute
'transcript'`` crash. After the v2.0.0 multi-timeline refactor, Project no
longer holds ``transcript`` directly -- it lives under
``project.timelines[].transcript``. The three rule-analysis handlers
(filler / error / full) were missed and read ``project.transcript.segments``.

These tests exercise ``MiloCutApi._get_target_timeline`` (the shared helper
all handlers now use) to confirm the correct timeline is resolved.
"""

from __future__ import annotations

import pytest

from core.models import (
    AnalysisData,
    MediaInfo,
    MiloTask,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    TaskType,
    Timeline,
    TranscriptData,
)
from main import MiloCutApi


def _make_project_with_timeline(timeline_id: str = "tl-1") -> Project:
    segments = [
        Segment(id="seg-1", type=SegmentType.SUBTITLE, start=0.0, end=2.0, text="这个那个"),
        Segment(id="seg-2", type=SegmentType.SUBTITLE, start=2.0, end=4.0, text="然后然后呢"),
        Segment(id="seg-3", type=SegmentType.SUBTITLE, start=4.0, end=6.0, text="正确内容"),
    ]
    timeline = Timeline(
        id=timeline_id,
        label="Main",
        source="default",
        transcript=TranscriptData(segments=segments),
        analysis=AnalysisData(),
        edits=[],
    )
    return Project(
        meta=ProjectMeta(name="test", media_path="/fake.mp4"),
        media=MediaInfo(path="/fake.mp4", duration=6.0),
        timelines=[timeline],
        active_timeline_id=timeline_id,
    )


def _make_task(timeline_id: str | None) -> MiloTask:
    payload = {}
    if timeline_id is not None:
        payload["timeline_id"] = timeline_id
    return MiloTask(
        id="task-1",
        type=TaskType.FILLER_DETECTION,
        payload=payload,
    )


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Build a MiloCutApi with a preloaded project; skip network/window setup."""
    api = MiloCutApi.__new__(MiloCutApi)
    # Minimal project-service-like holder exposing .current
    class _Holder:
        def __init__(self, project):
            self.current = project

    api._project = _Holder(_make_project_with_timeline())
    # _emit is used by handlers when storing results; no-op for these tests.
    api._emit = lambda *_a, **_kw: None
    # _mark_dirty passes the store dict through unchanged.
    api._mark_dirty = lambda store: store
    return api


class TestGetTargetTimeline:
    def test_resolves_explicit_timeline_id(self, api):
        task = _make_task(timeline_id="tl-1")
        tl = api._get_target_timeline(task)
        assert tl.id == "tl-1"
        assert len(tl.transcript.segments) == 3

    def test_falls_back_to_active_timeline(self, api):
        # No timeline_id in payload -> active_timeline_id
        task = _make_task(timeline_id=None)
        tl = api._get_target_timeline(task)
        assert tl.id == "tl-1"
        assert tl.transcript.segments[0].text == "这个那个"

    def test_raises_on_unknown_timeline(self, api):
        task = _make_task(timeline_id="does-not-exist")
        with pytest.raises(ValueError, match="not found"):
            api._get_target_timeline(task)

    def test_raises_when_no_project(self, api):
        api._project.current = None
        task = _make_task(timeline_id=None)
        with pytest.raises(ValueError, match="No project open"):
            api._get_target_timeline(task)


class TestHandlersReadActiveTimeline:
    """Confirm the three rule handlers no longer touch project.transcript."""

    def test_filler_detection_reads_segments(self, api, monkeypatch):
        # Filler detection used to crash with AttributeError on project.transcript.
        # The regression we guard against: the handler must run to completion
        # (no AttributeError) and call add_analysis_results with results derived
        # from the active timeline's segments.
        import core.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_settings", lambda: {"filler_words": ["那个"]}
        )
        captured: list[list] = []

        def _add(results_dicts, source=""):
            captured.append(results_dicts)
            return {"success": True, "data": _make_project_with_timeline().model_dump()}

        api._project.add_analysis_results = _add  # type: ignore[attr-defined]
        task = _make_task(timeline_id=None)
        # Must not raise AttributeError: 'Project' object has no attribute 'transcript'
        result = api._handle_filler_detection(task, None, lambda *a, **k: None)
        assert "results" in result
        # store was invoked exactly once with a list of result dicts
        assert len(captured) == 1

    def test_full_analysis_reads_active_timeline(self, api, monkeypatch):
        import core.config as config_mod

        monkeypatch.setattr(
            config_mod,
            "load_settings",
            lambda: {"filler_words": ["那个"], "error_trigger_words": []},
        )

        def _add(results_dicts, source=""):
            return {"success": True, "data": _make_project_with_timeline().model_dump()}

        api._project.add_analysis_results = _add  # type: ignore[attr-defined]
        task = _make_task(timeline_id=None)
        # Must not raise AttributeError; full analysis without workflow accumulate
        # returns {"project", "results"}.
        result = api._handle_full_analysis(task, None, lambda *a, **k: None)
        assert "results" in result
