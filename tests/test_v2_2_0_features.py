"""Tests for v2.2.0 features.

1. Subtitle correction with partial_delete edit hints
2. Highlight reel export (build_highlight_export_edits + get_highlight_ranges)
3. Manual highlight management without LLM
"""

from __future__ import annotations

from core.export_service import (
    build_highlight_export_edits,
    get_highlight_ranges,
)
from core.llm_service import _build_structured_user_message
from core.models import AnalysisResult, Segment, SegmentType
from core.timeline_utils import (
    collect_partial_delete_hints,
)

# ------------------------------------------------------------------
# Feature A: Subtitle correction with partial_delete hints
# ------------------------------------------------------------------


class TestCollectPartialDeleteHints:
    """Tests for collect_partial_delete_hints()."""

    def _make_segments(self) -> list[Segment]:
        return [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0, end=1, text="a"),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=1, end=2, text="b"),
            Segment(id="s3", type=SegmentType.SUBTITLE, start=2, end=3, text="c"),
        ]

    def test_no_partial_delete_returns_empty(self):
        """No partial_delete AnalysisResults -> empty hints."""
        from core.models import AnalysisData, Timeline

        timeline = Timeline(
            id="default",
            label="Default",
            analysis=AnalysisData(results=[
                AnalysisResult(
                    id="ar1",
                    type="llm_smart_delete",
                    segment_ids=["s1"],
                    category="semantic_dup",
                    detail="redundant",
                ),
            ]),
        )
        hints = collect_partial_delete_hints(timeline)
        assert hints == {}

    def test_partial_delete_hint_collected(self):
        """partial_delete AnalysisResult -> hint with reason."""
        from core.models import AnalysisData, Timeline

        timeline = Timeline(
            id="default",
            label="Default",
            analysis=AnalysisData(results=[
                AnalysisResult(
                    id="ar1",
                    type="llm_smart_delete",
                    segment_ids=["s2"],
                    category="partial_delete",
                    detail="前半口误后半修正",
                ),
            ]),
        )
        hints = collect_partial_delete_hints(timeline)
        assert "s2" in hints
        assert "口误" in hints["s2"]

    def test_partial_delete_default_reason_when_empty(self):
        """Empty detail -> default hint text."""
        from core.models import AnalysisData, Timeline

        timeline = Timeline(
            id="default",
            label="Default",
            analysis=AnalysisData(results=[
                AnalysisResult(
                    id="ar1",
                    type="llm_smart_delete",
                    segment_ids=["s1"],
                    category="partial_delete",
                    detail="",
                ),
            ]),
        )
        hints = collect_partial_delete_hints(timeline)
        assert "s1" in hints
        assert hints["s1"]  # should have some non-empty text


class TestBuildStructuredUserMessageEditHint:
    """Tests for edit_hint forwarding in _build_structured_user_message."""

    def test_no_edit_hint(self):
        """Segments without edit_hint -> no edit_hint in output."""
        segments = [{"id": "s1", "text": "hello", "start": 0, "end": 1}]
        msg = _build_structured_user_message(segments)
        import json

        parsed = json.loads(msg)
        assert "edit_hint" not in parsed["segments"][0]

    def test_with_edit_hint(self):
        """Segments with edit_hint -> edit_hint forwarded."""
        segments = [
            {"id": "s1", "text": "hello", "start": 0, "end": 1},
            {"id": "s2", "text": "world", "start": 1, "end": 2, "edit_hint": "句内重复"},
        ]
        msg = _build_structured_user_message(segments)
        import json

        parsed = json.loads(msg)
        assert "edit_hint" not in parsed["segments"][0]
        assert parsed["segments"][1]["edit_hint"] == "句内重复"


# ------------------------------------------------------------------
# Feature B: Highlight reel export
# ------------------------------------------------------------------


class TestGetHighlightRanges:
    """Tests for get_highlight_ranges with dict segments (v2.2.0)."""

    def test_dict_segments_supported(self):
        """get_highlight_ranges should work with dict segments."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s2", "s3"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
            {"id": "s3", "start": 20, "end": 30},
        ]
        ranges = get_highlight_ranges(results, segments)
        assert ranges == [(10, 20), (20, 30)]

    def test_empty_results(self):
        """No results -> empty ranges."""
        segments = [{"id": "s1", "start": 0, "end": 10}]
        ranges = get_highlight_ranges([], segments)
        assert ranges == []

    def test_manual_and_llm_highlights(self):
        """Both manual_highlight and llm_highlight AnalysisResults contribute."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1"]),
            AnalysisResult(id="ar2", type="llm_highlight", segment_ids=["s3"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 5},
            {"id": "s2", "start": 5, "end": 10},
            {"id": "s3", "start": 10, "end": 15},
        ]
        ranges = get_highlight_ranges(results, segments)
        assert ranges == [(0, 5), (10, 15)]

    def test_ignores_non_highlight_analysis_types(self):
        """Regression: llm_smart_delete / llm_subtitle_correction segment_ids
        must NOT be treated as highlights.

        Before the fix, get_highlight_ranges collected segment_ids from ALL
        AnalysisResult types, so a project that had run P0 smart-delete
        analysis would export ~the entire suggested-delete set as the
        "highlight reel" instead of just the marked highlights.
        """
        results = [
            # The single real highlight
            AnalysisResult(id="hl-1", type="llm_highlight", segment_ids=["s2"]),
            # P0 smart-delete suggestion carrying many segment_ids
            AnalysisResult(
                id="sd-1", type="llm_smart_delete",
                segment_ids=["s1", "s3", "s4"],
            ),
            # P1 subtitle correction carrying another segment_id
            AnalysisResult(
                id="sc-1", type="llm_subtitle_correction", segment_ids=["s4"],
            ),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 5},
            {"id": "s2", "start": 5, "end": 10},
            {"id": "s3", "start": 10, "end": 15},
            {"id": "s4", "start": 15, "end": 20},
        ]
        ranges = get_highlight_ranges(results, segments)
        # Only s2 (the llm_highlight) should remain
        assert ranges == [(5, 10)]


class TestBuildHighlightExportEdits:
    """Tests for build_highlight_export_edits()."""

    def test_basic_highlight_deletions(self):
        """Non-highlight ranges become confirmed deletes."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s2", "s3"]),
            AnalysisResult(id="ar2", type="llm_highlight", segment_ids=["s5"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
            {"id": "s3", "start": 20, "end": 30},
            {"id": "s4", "start": 30, "end": 40},
            {"id": "s5", "start": 40, "end": 50},
        ]
        edits = build_highlight_export_edits(segments, results, media_duration=50)
        assert len(edits) == 2  # s1 (0-10) and s4 (30-40)
        starts = sorted(e["start"] for e in edits)
        assert starts == [0, 30]
        for e in edits:
            assert e["action"] == "delete"
            assert e["status"] == "confirmed"

    def test_no_highlights_returns_empty(self):
        """No highlights -> empty edits (caller should handle)."""
        segments = [{"id": "s1", "start": 0, "end": 10}]
        edits = build_highlight_export_edits(segments, [], media_duration=10)
        assert edits == []

    def test_highlight_at_start_no_leading_delete(self):
        """Highlight at beginning -> no deletion before it."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        edits = build_highlight_export_edits(segments, results, media_duration=20)
        assert len(edits) == 1
        assert edits[0]["start"] == 10
        assert edits[0]["end"] == 20

    def test_highlight_covers_all_no_deletions(self):
        """Highlights cover entire video -> no deletions."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1", "s2"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        edits = build_highlight_export_edits(segments, results, media_duration=20)
        assert edits == []

    def test_includes_manual_highlights(self):
        """Manual highlights (type=llm_highlight from add_highlight_segment) included."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        edits = build_highlight_export_edits(segments, results, media_duration=20)
        # s2 (10-20) should be deleted since only s1 is highlight
        assert len(edits) == 1
        assert edits[0]["start"] == 10

    def test_trailing_gap_excluded(self):
        """Media duration > last segment end -> trailing gap becomes deletion."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        # Media is 30s but last segment ends at 20s -> trailing gap included in deletion
        edits = build_highlight_export_edits(segments, results, media_duration=30)
        # s1 is highlight (0-10), everything from 10 to 30 is deleted (s2 + trailing)
        assert len(edits) == 1
        assert edits[0]["start"] == 10
        assert edits[0]["end"] == 30

    def test_overlapping_highlight_ranges_merged(self):
        """Overlapping highlight ranges are merged before computing deletions."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1"]),
            AnalysisResult(id="ar2", type="llm_highlight", segment_ids=["s2"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 15},
            {"id": "s2", "start": 10, "end": 25},  # overlaps with s1
            {"id": "s3", "start": 25, "end": 30},
        ]
        edits = build_highlight_export_edits(segments, results, media_duration=30)
        # Merged highlight range is 0-25, so only 25-30 is deleted
        assert len(edits) == 1
        assert edits[0]["start"] == 25
        assert edits[0]["end"] == 30

    def test_existing_confirmed_deletes_subtracted(self):
        """v2.2.0 BUG2 fix: user-confirmed deletes inside highlight ranges
        are honored -- the deleted portion is NOT re-included in the reel."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1", "s2"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        # User deleted 4-6 (inside highlight s1 range)
        existing_edits = [
            {"id": "ed1", "start": 4, "end": 6, "action": "delete", "status": "confirmed"},
        ]
        edits = build_highlight_export_edits(
            segments, results, media_duration=20, existing_edits=existing_edits
        )
        # Highlight range was 0-20, minus 4-6 -> keep 0-4 and 6-20
        # So deletions should be 4-6 only (nothing outside highlight)
        assert len(edits) == 1
        assert edits[0]["start"] == 4
        assert edits[0]["end"] == 6

    def test_existing_deletes_outside_highlights_redundant(self):
        """Confirmed deletes outside highlight ranges don't cause duplicates."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s2"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        # User deleted 0-5 (outside highlight, already in non-highlight deletion)
        existing_edits = [
            {"id": "ed1", "start": 0, "end": 5, "action": "delete", "status": "confirmed"},
        ]
        edits = build_highlight_export_edits(
            segments, results, media_duration=20, existing_edits=existing_edits
        )
        # Highlight is s2 (10-20), non-highlight 0-10 already deleted.
        # User delete 0-5 is subset, no extra deletion needed.
        # Result: single deletion 0-10
        assert len(edits) == 1
        assert edits[0]["start"] == 0
        assert edits[0]["end"] == 10

    def test_existing_pending_edits_ignored(self):
        """Only confirmed deletes affect highlight ranges; pending ones ignored."""
        results = [
            AnalysisResult(id="ar1", type="llm_highlight", segment_ids=["s1", "s2"]),
        ]
        segments = [
            {"id": "s1", "start": 0, "end": 10},
            {"id": "s2", "start": 10, "end": 20},
        ]
        # Pending delete (not confirmed) should be ignored
        existing_edits = [
            {"id": "ed1", "start": 4, "end": 6, "action": "delete", "status": "pending"},
        ]
        edits = build_highlight_export_edits(
            segments, results, media_duration=20, existing_edits=existing_edits
        )
        # No deletions since highlight covers entire range and pending is ignored
        assert edits == []
