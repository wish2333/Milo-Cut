"""Tests for P1 subtitle correction review (v2.1.0 Phase 2).

Covers the store -> get -> accept/reject -> batch-accept -> clear lifecycle
on ProjectService, with AnalysisResult persistence in Timeline.analysis.
"""

from __future__ import annotations

from core.models import AnalysisResult
from core.project_service import ProjectService
from tests.mocks.factories import make_project, make_segments


def _service_with_project(monkeypatch, tmp_dir, segments=None):
    """Build a ProjectService with a project containing the given segments."""
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_dir / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
    svc = ProjectService()
    segs = segments if segments is not None else make_segments(3)
    svc._current = make_project(segments=segs)
    return svc


def _corrections(segments):
    """Build correction dicts matching the segments (each has a typo fix)."""
    return [
        {
            "segment_id": segments[0].id,
            "corrected_text": segments[0].text + " (已修正)",
            "changes": ["修正错字"],
            "category": "homophone",
            "confidence": 0.9,
        },
        {
            "segment_id": segments[1].id,
            "corrected_text": segments[1].text + " [低置信修正]",
            "changes": ["可能改写"],
            "category": "proper_noun",
            "confidence": 0.6,
        },
    ]


# ------------------------------------------------------------------
# store_subtitle_corrections
# ------------------------------------------------------------------


class TestStoreCorrections:
    def test_store_writes_analysis_results(self, tmp_dir, monkeypatch):
        segs = make_segments(3)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        corrs = _corrections(segs)

        res = svc.correction.store_subtitle_corrections(corrs, "default")
        assert res["success"]
        assert res["data"]["stored_count"] == 2

        tl = svc.active_timeline
        corr_results = [r for r in tl.analysis.results if r.type == "llm_subtitle_correction"]
        assert len(corr_results) == 2
        for r in corr_results:
            assert r.id.startswith("corr-")
            assert r.confidence in (0.9, 0.6)

    def test_store_skips_noop_corrections(self, tmp_dir, monkeypatch):
        """Corrections where corrected_text equals original are skipped."""
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        corrs = [
            {"segment_id": segs[0].id, "corrected_text": segs[0].text, "category": "none", "confidence": 1.0},
            {"segment_id": segs[1].id, "corrected_text": segs[1].text + "!", "category": "punctuation", "confidence": 0.8},
        ]
        res = svc.correction.store_subtitle_corrections(corrs, "default")
        assert res["data"]["stored_count"] == 1  # only the changed one

    def test_store_clears_previous_corrections(self, tmp_dir, monkeypatch):
        """Re-running P1 replaces pending corrections, avoiding duplicates."""
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        tl = svc.active_timeline
        corr_results = [r for r in tl.analysis.results if r.type == "llm_subtitle_correction"]
        assert len(corr_results) == 2  # not 4

    def test_store_preserves_other_analysis_types(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        # Pre-existing filler analysis result
        filler = AnalysisResult(id="f1", type="llm_smart_delete", segment_ids=[segs[0].id])
        tl = svc.active_timeline
        svc._update_active_timeline(
            analysis=tl.analysis.model_copy(update={"results": [filler]})
        )

        svc.correction.store_subtitle_corrections(_corrections(segs), "default")
        tl_after = svc.active_timeline
        types = [r.type for r in tl_after.analysis.results]
        assert "llm_smart_delete" in types
        assert types.count("llm_subtitle_correction") == 2

    def test_store_unknown_timeline_fails(self, tmp_dir, monkeypatch):
        svc = _service_with_project(monkeypatch, tmp_dir)
        res = svc.correction.store_subtitle_corrections([], "nonexistent")
        assert not res["success"]


# ------------------------------------------------------------------
# get_subtitle_corrections
# ------------------------------------------------------------------


class TestGetCorrections:
    def test_get_returns_parsed_detail(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        res = svc.correction.get_subtitle_corrections("default")
        assert res["success"]
        data = res["data"]
        assert len(data) == 2
        first = data[0]
        assert "original_text" in first
        assert "corrected_text" in first
        assert "changes" in first
        assert "category" in first
        assert "start" in first and "end" in first  # for time-link rendering
        assert first["segment_id"] == segs[0].id

    def test_get_empty_when_none(self, tmp_dir, monkeypatch):
        svc = _service_with_project(monkeypatch, tmp_dir)
        res = svc.correction.get_subtitle_corrections("default")
        assert res["success"]
        assert res["data"] == []


# ------------------------------------------------------------------
# accept / reject
# ------------------------------------------------------------------


class TestAcceptReject:
    def test_accept_applies_text_and_removes_result(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        corrs = _corrections(segs)
        svc.correction.store_subtitle_corrections(corrs, "default")

        corrections = svc.correction.get_subtitle_corrections("default")["data"]
        target = corrections[0]

        res = svc.correction.accept_subtitle_correction(target["id"])
        assert res["success"]
        assert res["data"]["segment_id"] == segs[0].id

        # Segment text updated
        tl = svc.active_timeline
        seg = next(s for s in tl.transcript.segments if s.id == segs[0].id)
        assert seg.text == corrs[0]["corrected_text"]
        assert seg.dirty_flags.get("llm_corrected") is True

        # Analysis result removed
        remaining = [r for r in tl.analysis.results if r.type == "llm_subtitle_correction"]
        assert len(remaining) == 1  # only the low-confidence one left

    def test_reject_removes_result_without_touching_text(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        original_text = segs[0].text
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        corrections = svc.correction.get_subtitle_corrections("default")["data"]
        res = svc.correction.reject_subtitle_correction(corrections[0]["id"])
        assert res["success"]

        tl = svc.active_timeline
        seg = next(s for s in tl.transcript.segments if s.id == segs[0].id)
        assert seg.text == original_text  # unchanged
        remaining = [r for r in tl.analysis.results if r.type == "llm_subtitle_correction"]
        assert len(remaining) == 1

    def test_accept_unknown_id_fails(self, tmp_dir, monkeypatch):
        svc = _service_with_project(monkeypatch, tmp_dir)
        res = svc.correction.accept_subtitle_correction("corr-nonexistent")
        assert not res["success"]

    def test_reject_unknown_id_fails(self, tmp_dir, monkeypatch):
        svc = _service_with_project(monkeypatch, tmp_dir)
        res = svc.correction.reject_subtitle_correction("corr-nonexistent")
        assert not res["success"]


# ------------------------------------------------------------------
# accept_high_confidence_corrections (batch)
# ------------------------------------------------------------------


class TestBatchAccept:
    def test_batch_accepts_above_threshold(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        corrs = _corrections(segs)  # confidences 0.9 and 0.6
        svc.correction.store_subtitle_corrections(corrs, "default")

        res = svc.correction.accept_high_confidence_corrections("default", threshold=0.8)
        assert res["success"]
        assert res["data"]["accepted_count"] == 1  # only the 0.9 one
        assert res["data"]["remaining_count"] == 1  # the 0.6 one stays

        # High-conf segment text updated
        tl = svc.active_timeline
        seg0 = next(s for s in tl.transcript.segments if s.id == segs[0].id)
        assert seg0.text == corrs[0]["corrected_text"]
        seg1 = next(s for s in tl.transcript.segments if s.id == segs[1].id)
        assert seg1.text == segs[1].text  # unchanged

    def test_batch_default_threshold_08(self, tmp_dir, monkeypatch):
        """D-68: default threshold is 0.8."""
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        res = svc.correction.accept_high_confidence_corrections("default")  # no threshold
        assert res["data"]["accepted_count"] == 1  # 0.9 >= 0.8

    def test_batch_all_high_confidence(self, tmp_dir, monkeypatch):
        """When all corrections meet threshold, all accepted, none remain."""
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        corrs = [
            {"segment_id": segs[0].id, "corrected_text": segs[0].text + " A", "category": "homophone", "confidence": 0.95},
            {"segment_id": segs[1].id, "corrected_text": segs[1].text + " B", "category": "homophone", "confidence": 0.88},
        ]
        svc.correction.store_subtitle_corrections(corrs, "default")

        res = svc.correction.accept_high_confidence_corrections("default", threshold=0.8)
        assert res["data"]["accepted_count"] == 2
        assert res["data"]["remaining_count"] == 0


# ------------------------------------------------------------------
# clear_subtitle_corrections
# ------------------------------------------------------------------


class TestClearCorrections:
    def test_clear_removes_all_pending(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        res = svc.correction.clear_subtitle_corrections("default")
        assert res["success"]
        assert res["data"]["cleared_count"] == 2

        remaining = svc.correction.get_subtitle_corrections("default")["data"]
        assert remaining == []

    def test_clear_when_empty(self, tmp_dir, monkeypatch):
        svc = _service_with_project(monkeypatch, tmp_dir)
        res = svc.correction.clear_subtitle_corrections("default")
        assert res["success"]
        assert res["data"]["cleared_count"] == 0

    def test_clear_preserves_other_analysis(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service_with_project(monkeypatch, tmp_dir, segs)
        from core.models import AnalysisResult
        filler = AnalysisResult(id="f1", type="llm_smart_delete", segment_ids=[segs[0].id])
        tl = svc.active_timeline
        svc._update_active_timeline(
            analysis=tl.analysis.model_copy(update={"results": [filler]})
        )
        svc.correction.store_subtitle_corrections(_corrections(segs), "default")

        svc.correction.clear_subtitle_corrections("default")
        tl_after = svc.active_timeline
        types = [r.type for r in tl_after.analysis.results]
        assert "llm_smart_delete" in types
        assert "llm_subtitle_correction" not in types
