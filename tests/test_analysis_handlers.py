"""v2.1.1 M1-1: _get_target_timeline helper regression tests.

Tests for ``MiloCutApi._get_target_timeline`` (the shared helper
that resolves the correct timeline from a task's payload).
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
        type=TaskType.SILENCE_DETECTION,
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
