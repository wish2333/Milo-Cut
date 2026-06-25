"""Tests for add_highlight_segment / remove_highlight_segment API methods.

Covers the manual highlight CRUD exposed in ``MiloCutApi``, which delegates to
``ProjectService.add_analysis_results`` and ``_update_timeline_by_id``.

Audit R-06 M5: these two methods previously had zero test coverage.
"""

from __future__ import annotations

import pytest

from core.models import (
    AnalysisData,
    AnalysisResult,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    Timeline,
    TranscriptData,
)
from main import MiloCutApi


# ── helpers ──────────────────────────────────────────────────────────


def _make_project_with_segments(
    segments: list[Segment] | None = None,
    *,
    timeline_id: str = "default",
) -> Project:
    """Build a minimal Project with a single timeline."""
    if segments is None:
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=2.0, text="hello"),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=2.0, end=4.0, text="world"),
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
        media=MediaInfo(path="/fake.mp4", duration=10.0),
        timelines=[timeline],
        active_timeline_id=timeline_id,
    )


class _ServiceStub:
    """Minimal stub of ProjectService exposing add_analysis_results and
    _update_timeline_by_id so the API methods can operate on an in-memory
    Project without filesystem or window dependencies."""

    def __init__(self, project: Project):
        self.current = project

    def add_analysis_results(self, results: list[dict], source: str, clear_existing: bool = False) -> dict:
        results_parsed = [AnalysisResult.model_validate(r) for r in results]
        tl = self.current.active_timeline

        if clear_existing and results_parsed:
            target_type = results_parsed[0].type
            removed_ar_ids = {r.id for r in tl.analysis.results if r.type == target_type}
            existing_results = [r for r in tl.analysis.results if r.type != target_type]
            existing_edits = [e for e in tl.edits if e.analysis_id not in removed_ar_ids]
        else:
            existing_results = list(tl.analysis.results)
            existing_edits = list(tl.edits)

        # Build EditDecisions (matches production add_analysis_results logic)
        seg_map = {s.id: s for s in tl.transcript.segments}
        existing_edit_ids = {e.id for e in existing_edits}
        new_edits = []
        for ar in results_parsed:
            matching_segs = [seg_map[sid] for sid in ar.segment_ids if sid in seg_map]
            if not matching_segs:
                continue
            start = min(s.start for s in matching_segs)
            end = max(s.end for s in matching_segs)
            edit_id = f"edit-{ar.id}"
            if edit_id in existing_edit_ids:
                n = 2
                while f"{edit_id}_dup{n}" in existing_edit_ids:
                    n += 1
                edit_id = f"{edit_id}_dup{n}"
            existing_edit_ids.add(edit_id)
            from core.models import EditDecision, EditStatus
            action = "keep" if source in ("llm_highlight", "manual_highlight") else "delete"
            new_edits.append(EditDecision(
                id=edit_id,
                start=start,
                end=end,
                action=action,
                source=source,
                analysis_id=ar.id,
                status=EditStatus.PENDING,
                priority=100,
                target_type="segment",
                target_id=ar.segment_ids[0],
            ))

        self.current = self.current.model_copy(
            update={
                "timelines": [
                    t.model_copy(
                        update={
                            "analysis": t.analysis.model_copy(
                                update={"results": existing_results + results_parsed}
                            ),
                            "edits": existing_edits + new_edits,
                        }
                    )
                    if t.id == tl.id
                    else t
                    for t in self.current.timelines
                ]
            }
        )
        return {"success": True}

    def _update_timeline_by_id(self, tl_id: str, **updates) -> None:
        self.current = self.current.model_copy(
            update={
                "timelines": [
                    t.model_copy(update=updates) if t.id == tl_id else t
                    for t in self.current.timelines
                ]
            }
        )


@pytest.fixture
def api():
    """MiloCutApi with an in-memory project stub and no side-effects."""
    api = MiloCutApi.__new__(MiloCutApi)
    proj = _make_project_with_segments()
    api._project = _ServiceStub(proj)
    api._mark_dirty = lambda store: store
    return api


# ── add_highlight_segment ─────────────────────────────────────────────


class TestAddHighlightSegment:
    def test_adds_highlight_for_valid_subtitle_segment(self, api):
        result = api.add_highlight_segment("s1")
        assert result["success"]
        assert result["data"]["result"]["type"] == "llm_highlight"
        assert result["data"]["result"]["segment_ids"] == ["s1"]
        assert result["data"]["result"]["detail"] == "手动添加"

        # Verify it was persisted into the timeline
        tl = api._project.current.active_timeline
        highlights = [r for r in tl.analysis.results if r.type == "llm_highlight"]
        assert len(highlights) == 1

    def test_rejects_nonexistent_segment(self, api):
        result = api.add_highlight_segment("nonexistent")
        assert not result["success"]
        assert "not found" in result["error"]

    def test_rejects_non_subtitle_segment(self, api):
        # Build a project where s1 is a silence segment
        segs = [
            Segment(id="s1", type=SegmentType.SILENCE, start=0.0, end=2.0, text=""),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=2.0, end=4.0, text="ok"),
        ]
        api._project.current = _make_project_with_segments(segs)
        result = api.add_highlight_segment("s1")
        assert not result["success"]
        assert "not found or not a subtitle" in result["error"]

    def test_rejects_when_no_project(self, api):
        api._project.current = None
        result = api.add_highlight_segment("s1")
        assert not result["success"]
        assert "No project open" in result["error"]

    def test_rejects_nonexistent_timeline(self, api):
        result = api.add_highlight_segment("s1", timeline_id="no-such-tl")
        assert not result["success"]
        assert "not found" in result["error"]


# ── remove_highlight_segment ──────────────────────────────────────────


class TestRemoveHighlightSegment:
    def test_removes_existing_highlight(self, api):
        # First add a highlight
        api.add_highlight_segment("s1")
        tl = api._project.current.active_timeline
        assert len([r for r in tl.analysis.results if r.type == "llm_highlight"]) == 1

        # Now remove it
        result = api.remove_highlight_segment("s1")
        assert result["success"]
        assert result["data"]["removed_count"] == 1

        tl = api._project.current.active_timeline
        assert len([r for r in tl.analysis.results if r.type == "llm_highlight"]) == 0

    def test_fails_when_no_highlight_exists(self, api):
        result = api.remove_highlight_segment("s1")
        assert not result["success"]
        assert "No highlight found" in result["error"]

    def test_preserves_other_highlights(self, api):
        api.add_highlight_segment("s1")
        api.add_highlight_segment("s2")
        tl = api._project.current.active_timeline
        assert len([r for r in tl.analysis.results if r.type == "llm_highlight"]) == 2

        result = api.remove_highlight_segment("s1")
        assert result["success"]
        assert result["data"]["removed_count"] == 1

        tl = api._project.current.active_timeline
        remaining = [r for r in tl.analysis.results if r.type == "llm_highlight"]
        assert len(remaining) == 1
        assert remaining[0].segment_ids == ["s2"]

    def test_removes_all_results_matching_segment(self, api):
        """If multiple AnalysisResults reference the same segment_id,
        all of them should be removed (current behaviour).
        """
        # Add one highlight through the API, then add a duplicate manually
        api.add_highlight_segment("s1")

        from core.models import AnalysisResult

        tl = api._project.current.active_timeline
        existing = list(tl.analysis.results)
        existing.append(
            AnalysisResult(
                id="dup_hl",
                type="llm_highlight",
                segment_ids=["s1"],
                confidence=1.0,
                detail="Duplicate",
            )
        )
        api._project.current = api._project.current.model_copy(
            update={
                "timelines": [
                    t.model_copy(
                        update={"analysis": t.analysis.model_copy(update={"results": existing})}
                    )
                    if t.id == tl.id
                    else t
                    for t in api._project.current.timelines
                ]
            }
        )

        result = api.remove_highlight_segment("s1")
        assert result["success"]
        assert result["data"]["removed_count"] == 2

    def test_rejects_when_no_project(self, api):
        api._project.current = None
        result = api.remove_highlight_segment("s1")
        assert not result["success"]
        assert "No project open" in result["error"]

    def test_removing_highlight_also_cleans_associated_edits(self, api):
        """Bug G: remove_highlight_segment must cascade-delete EditDecisions."""
        # Add a highlight (creates both AnalysisResult + EditDecision)
        api.add_highlight_segment("s1")
        tl = api._project.current.active_timeline

        # Verify EditDecision was created
        assert len(tl.edits) > 0
        assert any(e.source == "manual_highlight" for e in tl.edits)
        assert any(e.analysis_id and "manual_hl" in e.analysis_id for e in tl.edits)

        # Remove the highlight
        result = api.remove_highlight_segment("s1")
        assert result["success"]

        # Verify both AnalysisResult AND EditDecision are gone
        tl = api._project.current.active_timeline
        highlights = [r for r in tl.analysis.results if r.type == "llm_highlight"]
        assert len(highlights) == 0
        # No orphan EditDecisions should remain
        orphan_edits = [
            e for e in tl.edits
            if e.source == "manual_highlight"
        ]
        assert len(orphan_edits) == 0, f"Orphan edits remain: {orphan_edits}"


# ── Bug E: action depends on source ───────────────────────────────────


class TestHighlightActionBySource:
    def test_manual_highlight_creates_keep_action(self, api):
        """Bug E: manual_highlight source should create action='keep', not 'delete'."""
        api.add_highlight_segment("s1")
        tl = api._project.current.active_timeline
        highlight_edits = [e for e in tl.edits if e.source == "manual_highlight"]
        assert len(highlight_edits) == 1
        assert highlight_edits[0].action == "keep", (
            f"Expected action='keep', got '{highlight_edits[0].action}'"
        )

    def test_non_highlight_source_creates_delete_action(self, api):
        """Non-highlight sources should still create action='delete'."""
        from core.models import AnalysisResult
        api._project.add_analysis_results(
            [{
                "id": "test_ar_1",
                "type": "llm_smart_delete",
                "segment_ids": ["s1"],
                "confidence": 0.9,
                "detail": "test",
            }],
            source="llm_smart",
        )
        tl = api._project.current.active_timeline
        smart_edits = [e for e in tl.edits if e.source == "llm_smart"]
        assert len(smart_edits) == 1
        assert smart_edits[0].action == "delete"
