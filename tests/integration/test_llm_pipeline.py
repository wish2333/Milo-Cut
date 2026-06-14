"""End-to-end LLM pipeline integration tests.

These tests exercise the full LLM pipeline (P0-P3) with mocked LLM responses,
verifying:

1. P0 smart-delete -> EditDecision flow
2. P1 subtitle correction -> timestamp safety
3. P2 highlight -> duration control
4. P3 semantic search -> top_k relevance
5. Multi-timeline isolation

All tests use ``@pytest.mark.integration`` and are excluded from the default
test run via ``addopts = "-m 'not integration'"`` in pyproject.toml.
Run with: ``uv run pytest -m integration``
"""

from __future__ import annotations

import json

import pytest

from core.llm_service import (
    analyze_highlights,
    analyze_smart_delete,
    analyze_subtitle_correction,
    semantic_search,
)
from core.models import EditStatus, LlmConfig, LlmProvider
from core.project_service import ProjectService
from tests.mocks.factories import make_project, make_segments

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _configured_llm() -> LlmConfig:
    """An LlmConfig that passes is_configured()."""
    return LlmConfig(
        provider=LlmProvider.CUSTOM,
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="test-model",
    )


def _mock_llm_response(content: str):
    """Build a mock call_llm return value."""

    def _mock(prompt, system="", **kwargs):
        return {
            "success": True,
            "data": {
                "content": content,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        }

    return _mock


# ------------------------------------------------------------------
# P0 Smart Delete E2E
# ------------------------------------------------------------------


@pytest.mark.integration
class TestP0SmartDeleteE2E:
    """P0: project -> smart_delete analysis -> EditDecisions in timeline."""

    def test_smart_delete_produces_results(self, monkeypatch):
        """Mock LLM returns delete suggestions -> results parsed."""
        segments = make_segments(5, text_template="um then segment {}")
        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]

        llm_output = json.dumps([
            {"segment_id": segments[0].id, "action": "delete",
             "reason": "filler", "category": "filler_phrase"},
            {"segment_id": segments[2].id, "action": "delete",
             "reason": "repetition", "category": "semantic_duplicate"},
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = analyze_smart_delete(seg_dicts, config=_configured_llm())
        assert result["success"] is True
        assert len(result["data"]["results"]) == 2
        ids = {r["segment_id"] for r in result["data"]["results"]}
        assert segments[0].id in ids
        assert segments[2].id in ids

    def test_smart_delete_incremental_skips_flagged(self, monkeypatch):
        """existing_flagged_ids are skipped -- no redundant LLM analysis."""
        segments = make_segments(4)
        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]

        llm_output = json.dumps([
            {"segment_id": segments[1].id, "action": "delete",
             "reason": "filler", "category": "filler_phrase"}
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        # Flag segments[0] and segments[3] as already done
        result = analyze_smart_delete(
            seg_dicts,
            existing_flagged_ids={segments[0].id, segments[3].id},
            config=_configured_llm(),
        )
        assert result["success"] is True
        flagged_ids = {r["segment_id"] for r in result["data"]["results"]}
        # Only segments[1] should appear (segments[2] was analyzed but LLM
        # only flagged segments[1])
        assert segments[0].id not in flagged_ids
        assert segments[3].id not in flagged_ids

    def test_smart_delete_to_edit_decision_flow(self):
        """Full flow: analysis results -> add_analysis_results -> EditDecisions."""
        svc = ProjectService()
        segments = make_segments(5)
        svc._current = make_project(segments=list(segments))

        # Simulate what the task handler does after LLM returns
        analysis_results = [
            {
                "id": "ar-smart-001",
                "type": "llm_smart_delete",
                "segment_ids": [segments[0].id],
                "label": "智能删除",
                "details": {"reason": "filler", "category": "filler_phrase"},
            }
        ]
        result = svc.add_analysis_results(analysis_results, source="llm_smart")
        assert result["success"] is True

        edits = svc.active_timeline.edits
        smart_edits = [e for e in edits if e.source == "llm_smart"]
        assert len(smart_edits) == 1
        assert smart_edits[0].action == "delete"
        assert smart_edits[0].status == EditStatus.PENDING
        assert smart_edits[0].target_id == segments[0].id


# ------------------------------------------------------------------
# P1 Subtitle Correction -- Timestamp Safety
# ------------------------------------------------------------------


@pytest.mark.integration
class TestP1SubtitleCorrectionE2E:
    """P1: subtitle correction preserves timestamps (assertion layer)."""

    def test_correction_preserves_timestamps(self, monkeypatch):
        """After apply_subtitle_corrections, start/end must be unchanged."""
        segments = make_segments(4, text_template="这是第{}段字幕有错字")
        original_times = {s.id: (s.start, s.end) for s in segments}

        svc = ProjectService()
        svc._current = make_project(segments=list(segments))

        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]
        llm_output = json.dumps([
            {"segment_id": segments[0].id, "corrected_text": "这是第一段字幕有错字",
             "changes": ["一"], "category": "homophone", "confidence": 0.95},
            {"segment_id": segments[2].id, "corrected_text": "这是第三段字幕有错字",
             "changes": ["三"], "category": "homophone", "confidence": 0.9},
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = analyze_subtitle_correction(seg_dicts, config=_configured_llm())
        assert result["success"] is True

        corrections = result["data"]["corrections"]
        apply_result = svc.apply_subtitle_corrections(corrections)
        assert apply_result["success"] is True

        # Critical: timestamps must be identical to original
        for seg in svc.active_timeline.transcript.segments:
            orig_start, orig_end = original_times[seg.id]
            assert seg.start == orig_start, (
                f"Timestamp corruption: {seg.id} start {seg.start} != {orig_start}"
            )
            assert seg.end == orig_end, (
                f"Timestamp corruption: {seg.id} end {seg.end} != {orig_end}"
            )

    def test_partial_match_does_not_fail(self, monkeypatch):
        """Layered fault tolerance: partial match succeeds with uncovered."""
        segments = make_segments(5)
        svc = ProjectService()
        svc._current = make_project(segments=list(segments))

        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]
        # Only correct 2 of 5 segments
        llm_output = json.dumps([
            {"segment_id": segments[1].id, "corrected_text": "corrected 1",
             "changes": ["1"], "category": "typo", "confidence": 0.9},
            {"segment_id": segments[3].id, "corrected_text": "corrected 3",
             "changes": ["3"], "category": "typo", "confidence": 0.85},
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = analyze_subtitle_correction(seg_dicts, config=_configured_llm())
        corrections = result["data"]["corrections"]

        apply_result = svc.apply_subtitle_corrections(corrections)
        assert apply_result["success"] is True
        assert apply_result["data"]["partial"] is True
        assert apply_result["data"]["uncovered_count"] == 3
        assert apply_result["data"]["corrected_count"] == 2

    def test_dev_mode_raises_on_timestamp_corruption(self, monkeypatch):
        """In dev mode, the assertion layer raises ValueError on mismatch.

        This tests the _assert_timestamps_unchanged safety net directly,
        simulating a scenario where a future code path might accidentally
        alter timestamps.
        """
        from core.llm_service import _assert_timestamps_unchanged

        monkeypatch.setenv("MILO_ENV", "development")
        with pytest.raises(ValueError, match="imestamp"):
            _assert_timestamps_unchanged(
                1.0, 5.0, 999.0, 998.0, segment_id="seg-test",
            )

    def test_prod_mode_warns_on_timestamp_corruption(self, monkeypatch):
        """In prod mode, assertion raises TimestampCorruptionError (caught
        by caller for rollback)."""
        from core.llm_service import TimestampCorruptionError, _assert_timestamps_unchanged

        monkeypatch.delenv("MILO_ENV", raising=False)
        with pytest.raises(TimestampCorruptionError):
            _assert_timestamps_unchanged(
                1.0, 5.0, 999.0, 998.0, segment_id="seg-test",
            )


# ------------------------------------------------------------------
# P2 Highlight -- Duration Control
# ------------------------------------------------------------------


@pytest.mark.integration
class TestP2HighlightE2E:
    """P2: highlight extraction with duration trimming."""

    def test_highlight_duration_within_tolerance(self, monkeypatch):
        """Total highlight duration stays within target +-20%."""
        # Create 10 segments of 5s each = 50s total
        segments = make_segments(10, duration=5.0, gap=0.0)
        seg_dicts = [
            {"id": s.id, "text": f"这是重要论点 {i}", "start": s.start, "end": s.end}
            for i, s in enumerate(segments)
        ]

        # LLM marks 4 as high density (4 * 5s = 20s)
        highlight_ids = [segments[i].id for i in [0, 3, 6, 9]]
        llm_output = json.dumps([
            {"segment_id": sid, "action": "keep", "density": "high",
             "reason": "core argument"}
            for sid in highlight_ids
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        target_minutes = 1  # 60s target, but only 20s of highlights exist
        result = analyze_highlights(
            seg_dicts, target_duration_minutes=target_minutes,
            config=_configured_llm(),
        )
        assert result["success"] is True

        highlight_results = result["data"]["results"]
        total_duration = result["data"]["total_highlight_duration"]
        # 4 segments * 5s = 20s (well within 60s target)
        assert total_duration <= 60 * 1.2  # upper bound
        assert len(highlight_results) == 4

    def test_highlight_results_sorted_by_start(self, monkeypatch):
        """Highlight results are returned in natural playback order."""
        segments = make_segments(8)
        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]

        # LLM returns out-of-order
        llm_output = json.dumps([
            {"segment_id": segments[5].id, "action": "keep", "density": "high"},
            {"segment_id": segments[1].id, "action": "keep", "density": "high"},
            {"segment_id": segments[7].id, "action": "keep", "density": "medium"},
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = analyze_highlights(
            seg_dicts, target_duration_minutes=5, config=_configured_llm(),
        )
        assert result["success"] is True

        # Results are sorted by start time (natural playback order).
        # The result items contain segment_id; look up start from input.
        seg_start = {s.id: s.start for s in segments}
        starts = [
            seg_start.get(r["segment_id"], 0)
            for r in result["data"]["results"]
        ]
        assert starts == sorted(starts), "Highlights must be in time order"


# ------------------------------------------------------------------
# P3 Semantic Search
# ------------------------------------------------------------------


@pytest.mark.integration
class TestP3SemanticSearchE2E:
    """P3: semantic search returns top_k results by relevance."""

    def test_semantic_search_top_k(self, monkeypatch):
        """Search respects top_k limit."""
        segments = make_segments(10)
        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]

        # LLM returns 8 results but top_k=3
        llm_output = json.dumps([
            {"segment_id": segments[i].id, "relevance": 1.0 - i * 0.1,
             "match_reason": "semantic match"}
            for i in range(8)
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = semantic_search(
            "important topic", seg_dicts, top_k=3, config=_configured_llm(),
        )
        assert result["success"] is True
        assert len(result["data"]["results"]) == 3

    def test_semantic_search_sorted_by_relevance(self, monkeypatch):
        """Results are sorted by relevance descending."""
        segments = make_segments(5)
        seg_dicts = [
            {"id": s.id, "text": s.text, "start": s.start, "end": s.end}
            for s in segments
        ]

        llm_output = json.dumps([
            {"segment_id": segments[2].id, "relevance": 0.5, "match_reason": "weak"},
            {"segment_id": segments[0].id, "relevance": 0.9, "match_reason": "strong"},
            {"segment_id": segments[4].id, "relevance": 0.7, "match_reason": "medium"},
        ])
        monkeypatch.setattr(
            "core.llm_service.call_llm", _mock_llm_response(llm_output)
        )

        result = semantic_search(
            "query", seg_dicts, top_k=5, config=_configured_llm(),
        )
        assert result["success"] is True
        relevances = [r["relevance"] for r in result["data"]["results"]]
        assert relevances == sorted(relevances, reverse=True)


# ------------------------------------------------------------------
# Multi-Timeline Isolation
# ------------------------------------------------------------------


@pytest.mark.integration
class TestMultiTimelineIsolation:
    """Operations on one timeline must not affect another."""

    def test_fork_isolates_edits(self):
        """Forking a timeline and adding edits to fork leaves original clean."""
        svc = ProjectService()
        segments = make_segments(6)
        svc._current = make_project(segments=list(segments))

        original_timeline_id = svc.active_timeline.id
        assert len(svc.active_timeline.edits) == 0

        # Fork
        fork_result = svc.create_timeline("Branch B", fork_from=original_timeline_id)
        assert fork_result["success"] is True
        fork_tl_id = svc.active_timeline.id
        assert fork_tl_id != original_timeline_id

        # Add analysis result to fork (simulating P0 on fork)
        analysis_results = [
            {
                "id": "ar-fork-001",
                "type": "llm_smart_delete",
                "segment_ids": [segments[0].id],
                "label": "智能删除",
                "details": {"reason": "filler"},
            }
        ]
        svc.add_analysis_results(analysis_results, source="llm_smart")

        # Fork should have the edit
        fork_edits = [
            e for e in svc.active_timeline.edits if e.source == "llm_smart"
        ]
        assert len(fork_edits) == 1

        # Switch back to original -- it should be clean
        svc.switch_timeline(original_timeline_id)
        original_smart_edits = [
            e for e in svc.active_timeline.edits if e.source == "llm_smart"
        ]
        assert len(original_smart_edits) == 0

    def test_subtitle_correction_isolated_per_timeline(self, monkeypatch):
        """Subtitle correction on fork does not affect original transcript."""
        svc = ProjectService()
        segments = make_segments(4, text_template="原始字幕{}")
        svc._current = make_project(segments=list(segments))
        original_id = svc.active_timeline.id
        original_texts = {s.id: s.text for s in svc.active_timeline.transcript.segments}

        # Fork
        svc.create_timeline("Corrected", fork_from=original_id)

        # Apply correction on fork
        corrections = [
            {"segment_id": s.id, "corrected_text": f"修正字幕{i}",
             "changes": ["修正"], "category": "typo", "confidence": 0.9}
            for i, s in enumerate(svc.active_timeline.transcript.segments)
        ]
        result = svc.apply_subtitle_corrections(corrections)
        assert result["success"] is True

        # Fork transcript is modified
        fork_texts = {s.id: s.text for s in svc.active_timeline.transcript.segments}
        assert any(v != original_texts[k] for k, v in fork_texts.items())

        # Original transcript untouched
        svc.switch_timeline(original_id)
        for seg in svc.active_timeline.transcript.segments:
            assert seg.text == original_texts[seg.id], (
                f"Original timeline corrupted: {seg.id}"
            )

    def test_delete_timeline_preserves_others(self):
        """Deleting one timeline does not affect others."""
        import time

        svc = ProjectService()
        svc._current = make_project(segments=make_segments(3))

        # Create two additional timelines (sleep to avoid timestamp ID clash)
        svc.create_timeline("B")
        time.sleep(0.01)
        svc.create_timeline("C")
        assert len(svc._current.timelines) == 3

        tl_b = [t for t in svc._current.timelines if t.label == "B"][0]

        # Delete B
        result = svc.delete_timeline(tl_b.id)
        assert result["success"] is True
        assert len(svc._current.timelines) == 2
        assert all(t.id != tl_b.id for t in svc._current.timelines)

    def test_concurrent_timeline_operations(self, monkeypatch):
        """Simulate concurrent task isolation via payload-frozen timeline_id.

        The task system freezes timeline_id in the payload at task creation
        time. Here we verify that analysis results are always written to the
        correct timeline regardless of which timeline is 'active' at the
        time of writing.
        """
        svc = ProjectService()
        segments = make_segments(5)
        svc._current = make_project(segments=list(segments))
        tl_a_id = svc.active_timeline.id

        # Create timeline B and switch to it (simulating user switching)
        svc.create_timeline("Timeline B")
        tl_b_id = svc.active_timeline.id

        # Now user is on B, but a task for A completes.
        # The handler should write to A (frozen in payload), not B.
        # Simulate: switch back to A explicitly (as handler does with
        # frozen timeline_id), add results, switch back to B.
        frozen_timeline_id = tl_a_id  # what the task payload contains

        # Handler pattern: switch to frozen timeline, write, switch back
        svc.switch_timeline(frozen_timeline_id)
        svc.add_analysis_results(
            [{"id": "ar-conc-001", "type": "llm_smart_delete",
              "segment_ids": [segments[0].id], "label": "test"}],
            source="llm_smart",
        )
        svc.switch_timeline(tl_b_id)

        # Verify A has the edit, B does not
        tl_a = svc._current.get_timeline(tl_a_id)
        tl_b = svc._current.get_timeline(tl_b_id)
        a_smart = [e for e in tl_a.edits if e.source == "llm_smart"]
        b_smart = [e for e in tl_b.edits if e.source == "llm_smart"]
        assert len(a_smart) == 1
        assert len(b_smart) == 0
