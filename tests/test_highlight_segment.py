"""Tests for add_highlight_segment / remove_highlight_segment API methods.

Covers the manual highlight CRUD exposed in ``MiloCutApi``, which delegates to
the real ``ProjectService`` (``add_analysis_results`` / ``_update_timeline_by_id``).

These tests instantiate the real ``ProjectService`` against an isolated tmp dir
so the API layer is exercised end-to-end without any duplicated service logic.
Service-level edge cases (clear_existing, cascade cleanup, migration) are
covered separately in ``tests/test_project_service.py``.

Audit R-06 M5: these two API methods previously had zero test coverage.
"""

from __future__ import annotations

import pytest

from core.models import Segment, SegmentType
from core.project_service import ProjectService
from main import MiloCutApi


# ── helpers ──────────────────────────────────────────────────────────


def _create_service(tmp_path, monkeypatch) -> ProjectService:
    """Real ProjectService with isolated paths (no global state leakage)."""
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
    return ProjectService()


def _create_media_file(tmp_path) -> str:
    media_file = tmp_path / "test.mp4"
    media_file.write_bytes(b"fake media content")
    return str(media_file)


def _seed_segments(svc: ProjectService, segments: list[Segment]) -> None:
    """Populate the active timeline transcript with the given segments."""
    svc.update_transcript([s.model_dump() for s in segments])


def _default_segments() -> list[Segment]:
    return [
        Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=2.0, text="hello"),
        Segment(id="s2", type=SegmentType.SUBTITLE, start=2.0, end=4.0, text="world"),
    ]


@pytest.fixture
def api(tmp_path, monkeypatch) -> MiloCutApi:
    """MiloCutApi wired to a real ProjectService seeded with two subtitle segments.

    Uses ``__new__`` to skip Bridge/window initialization; only the two API
    methods under test (and the real service they delegate to) are exercised.
    """
    svc = _create_service(tmp_path, monkeypatch)
    svc.create_project("test", _create_media_file(tmp_path), {"duration": 60.0})
    _seed_segments(svc, _default_segments())

    api = MiloCutApi.__new__(MiloCutApi)
    api._project = svc
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
        # Reseed: s1 is a silence segment, only s2 is subtitle
        svc = api._project
        _seed_segments(svc, [
            Segment(id="s1", type=SegmentType.SILENCE, start=0.0, end=2.0, text=""),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=2.0, end=4.0, text="ok"),
        ])
        result = api.add_highlight_segment("s1")
        assert not result["success"]
        assert "not found or not a subtitle" in result["error"]

    def test_rejects_when_no_project(self, api):
        api._project.close_project()
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

        svc = api._project
        tl = svc.current.active_timeline
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
        svc._update_timeline_by_id(
            tl.id,
            analysis=tl.analysis.model_copy(update={"results": existing}),
        )

        result = api.remove_highlight_segment("s1")
        assert result["success"]
        assert result["data"]["removed_count"] == 2

    def test_rejects_when_no_project(self, api):
        api._project.close_project()
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
