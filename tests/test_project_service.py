"""Tests for core.project_service."""

from core.models import EditStatus, SegmentType
from core.project_service import ProjectService


class TestProjectService:
    def _create_service(self, tmp_dir, monkeypatch):
        """Create a ProjectService with isolated paths."""
        monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_dir / "projects")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        svc = ProjectService()
        return svc

    def _create_media_file(self, tmp_dir) -> str:
        """Create a temporary media file for testing."""
        media_file = tmp_dir / "test.mp4"
        media_file.write_bytes(b"fake media content")
        return str(media_file)

    def test_create_and_open(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        assert result["success"] is True
        assert svc.current is not None
        assert svc.current.project.name == "test"

    def test_save_and_reload(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        save_result = svc.save_project()
        assert save_result["success"] is True

        # Reopen
        svc2 = self._create_service(tmp_dir, monkeypatch)
        project_path = tmp_dir / "projects" / "test" / "project.json"
        open_result = svc2.open_project(str(project_path))
        assert open_result["success"] is True
        assert svc2.current.project.name == "test"

    def test_close_project(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.close_project()
        assert svc.current is None

    def test_update_transcript(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        segs = [s.model_dump() for s in sample_segments]
        result = svc.update_transcript(segs)
        assert result["success"] is True
        assert len(svc.current.active_timeline.transcript.segments) == len(sample_segments)

    def test_add_silence_results(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        silences = [{"start": 5.0, "end": 5.5}, {"start": 10.0, "end": 11.0}]
        result = svc.add_silence_results(silences)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 2
        assert len(svc.current.active_timeline.edits) == 2

    def test_update_edit_decision(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        edit_id = svc.current.active_timeline.edits[0].id
        result = svc.update_edit_decision(edit_id, "confirmed")
        assert result["success"] is True
        assert svc.current.active_timeline.edits[0].status == EditStatus.CONFIRMED

    def test_update_segment(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.update_segment("seg-0001", {"text": "Updated text"})
        assert result["success"] is True
        seg = next(s for s in svc.current.active_timeline.transcript.segments if s.id == "seg-0001")
        assert seg.text == "Updated text"

    def test_merge_segments(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.merge_segments(["seg-0001", "seg-0002"])
        assert result["success"] is True
        merged = [s for s in svc.current.active_timeline.transcript.segments if s.id == "seg-0001"]
        assert len(merged) == 1
        assert "Hello world" in merged[0].text
        assert "This is a test" in merged[0].text

    def test_split_segment(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.split_segment("seg-0001", 3.0)
        assert result["success"] is True
        segs = svc.current.active_timeline.transcript.segments
        a = next((s for s in segs if s.id == "seg-0001-a"), None)
        b = next((s for s in segs if s.id == "seg-0001-b"), None)
        assert a is not None
        assert b is not None
        assert a.end == 3.0
        assert b.start == 3.0

    def test_search_replace(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.search_replace("Hello", "Hi")
        assert result["success"] is True
        assert result["data"]["count"] == 1
        seg = next(s for s in svc.current.active_timeline.transcript.segments if s.id == "seg-0001")
        assert seg.text == "Hi world"

    def test_mark_segments(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.mark_segments(["seg-0001"], "delete")
        assert result["success"] is True
        assert len(svc.current.active_timeline.edits) > 0

    def test_confirm_all_suggestions(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}, {"start": 10.0, "end": 11.0}])
        result = svc.confirm_all_suggestions()
        assert result["success"] is True
        assert result["data"]["confirmed_count"] == 2
        assert all(e.status == EditStatus.CONFIRMED for e in svc.current.active_timeline.edits)

    def test_reject_all_suggestions(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        result = svc.reject_all_suggestions()
        assert result["success"] is True
        assert svc.current.active_timeline.edits[0].status == EditStatus.REJECTED

    def test_get_edit_summary(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        svc.confirm_all_suggestions()
        result = svc.get_edit_summary()
        assert result["success"] is True
        assert result["data"]["edit_count"] == 1

    def test_add_analysis_results(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        results = [
            {
                "id": "ar-1",
                "type": "llm_smart_delete",
                "segment_ids": ["seg-0001"],
                "confidence": 0.9,
                "detail": "test",
            }
        ]
        result = svc.add_analysis_results(results, source="test")
        assert result["success"] is True
        assert len(svc.current.active_timeline.analysis.results) == 1
        assert len(svc.current.active_timeline.edits) > 0

    def test_update_segment_text(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.update_segment_text("seg-0001", "New text")
        assert result["success"] is True
        seg = next(s for s in svc.current.active_timeline.transcript.segments if s.id == "seg-0001")
        assert seg.text == "New text"
        assert seg.dirty_flags.get("text_edited") is True

    def test_get_settings(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.get_settings()
        assert result["success"] is True
        assert "silence_threshold_db" in result["data"]

    def test_get_recent_projects_empty(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.get_recent_projects()
        assert result["success"] is True
        assert result["data"] == []

    # --- D-1: Margin shrink ---

    def test_add_silence_results_with_margin(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        silences = [{"start": 5.0, "end": 6.0}, {"start": 10.0, "end": 11.0}]
        result = svc.add_silence_results(silences, margin=0.1)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 2
        assert abs(sil_segs[0].start - 5.1) < 0.01
        assert abs(sil_segs[0].end - 5.9) < 0.01

    def test_add_silence_results_margin_consumes_short(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        silences = [{"start": 5.0, "end": 5.1}]  # 0.1s duration, margin=0.1 -> consumed
        result = svc.add_silence_results(silences, margin=0.1)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 0

    def test_add_silence_results_margin_zero(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        silences = [{"start": 5.0, "end": 6.0}]
        result = svc.add_silence_results(silences, margin=0.0)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 1
        assert abs(sil_segs[0].start - 5.0) < 0.01

    # --- D-2: Subtitle padding trim ---

    def _add_subtitles(self, svc, subtitles):
        """Helper: add subtitle segments to the project. subtitles = [(start, end, text), ...]"""
        from core.models import SegmentType
        from tests.mocks import make_segment

        segs = [
            make_segment(id=f"sub-{i:04d}", type=SegmentType.SUBTITLE, start=s, end=e, text=t)
            for i, (s, e, t) in enumerate(subtitles)
        ]
        svc.update_transcript([s.model_dump() for s in segs])

    def test_trim_silences_no_overlap(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(10.0, 12.0, "sub")])
        silences = [{"start": 1.0, "end": 3.0, "duration": 2.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 1
        assert abs(result[0]["start"] - 1.0) < 0.01
        assert abs(result[0]["end"] - 3.0) < 0.01

    def test_trim_silences_full_enclosure(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        silences = [{"start": 4.0, "end": 9.0, "duration": 5.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 2
        assert abs(result[0]["start"] - 4.0) < 0.01
        assert abs(result[0]["end"] - 4.7) < 0.01
        assert abs(result[1]["start"] - 8.3) < 0.01
        assert abs(result[1]["end"] - 9.0) < 0.01

    def test_trim_silences_partial_overlap(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        silences = [{"start": 6.0, "end": 10.0, "duration": 4.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 1
        assert abs(result[0]["start"] - 8.3) < 0.01
        assert abs(result[0]["end"] - 10.0) < 0.01

    def test_trim_silences_padding_zero(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        silences = [{"start": 4.0, "end": 9.0, "duration": 5.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.0)
        assert len(result) == 1  # passthrough

    def test_trim_silences_fully_inside_extended(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        silences = [{"start": 6.0, "end": 7.0, "duration": 1.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 0  # fully consumed

    def test_trim_silences_adjacent_subtitles_merge(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 6.0, "a"), (6.2, 7.0, "b")])
        silences = [{"start": 4.0, "end": 8.0, "duration": 4.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        # extended: [4.7, 6.3] + [5.9, 7.3] -> merged [4.7, 7.3]
        assert len(result) == 2
        assert abs(result[0]["start"] - 4.0) < 0.01
        assert abs(result[0]["end"] - 4.7) < 0.01
        assert abs(result[1]["start"] - 7.3) < 0.01
        assert abs(result[1]["end"] - 8.0) < 0.01

    def test_trim_silences_no_subtitles(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        silences = [{"start": 4.0, "end": 9.0, "duration": 5.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 1  # no subtitles -> passthrough

    def test_trim_silences_ignores_confirmed_deleted_subtitles(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        # Confirm-delete the subtitle via update_edit_decision
        sub_id = next(s.id for s in svc.current.active_timeline.transcript.segments if s.type == "subtitle")
        svc.add_silence_results([{"start": 5.0, "end": 8.0}])
        # Mark the silence edit as confirmed so the subtitle gets a confirmed-delete edit
        # Instead, directly add a confirmed delete edit for the subtitle
        from core.models import EditStatus
        from tests.mocks import make_edit_decision

        confirmed_edit = make_edit_decision(
            id="ed-sub-del",
            start=5.0,
            end=8.0,
            action="delete",
            source="user",
            status=EditStatus.CONFIRMED,
            target_id=sub_id,
        )
        svc._update_active_timeline(
            edits=list(svc.active_timeline.edits) + [confirmed_edit],
        )
        silences = [{"start": 4.0, "end": 9.0, "duration": 5.0}]
        result = svc._trim_silences_around_subtitles(silences, padding=0.3)
        assert len(result) == 1  # deleted subtitle ignored, silence unchanged
        assert abs(result[0]["start"] - 4.0) < 0.01
        assert abs(result[0]["end"] - 9.0) < 0.01

    def test_add_silence_results_with_subtitle_padding(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitles(svc, [(5.0, 8.0, "sub")])
        silences = [{"start": 4.0, "end": 9.0}]
        result = svc.add_silence_results(silences, subtitle_padding=0.3)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 2
        assert abs(sil_segs[0].start - 4.0) < 0.01
        assert abs(sil_segs[0].end - 4.7) < 0.01

    def test_split_segment_inherits_and_independent_segment_edits(self, tmp_dir, monkeypatch, sample_segments):
        """v2.1.1 A-2.4: segment-targeted ED must be cloned to both a and b
        so each sub-segment has an independent decision after split."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])

        # Mark seg-0001 as delete -> creates segment-targeted ED
        result = svc.mark_segments(["seg-0001"], "delete")
        assert result["success"] is True
        original_edits = svc.current.active_timeline.edits
        assert len(original_edits) == 1
        assert original_edits[0].target_type == "segment"
        assert original_edits[0].target_id == "seg-0001"

        # Split seg-0001 at 3.0
        result = svc.split_segment("seg-0001", 3.0)
        assert result["success"] is True
        edits_after_split = svc.current.active_timeline.edits
        # Original ED dropped, two clones added (a + b)
        assert len(edits_after_split) == 2
        edit_a = next(e for e in edits_after_split if e.target_id == "seg-0001-a")
        edit_b = next(e for e in edits_after_split if e.target_id == "seg-0001-b")
        # Both inherit action and original status
        assert edit_a.action == "delete"
        assert edit_b.action == "delete"

        # Flip only a -> b must be unaffected (independence check)
        svc.update_edit_decision(edit_a.id, "rejected")
        edit_a_after = next(e for e in svc.current.active_timeline.edits if e.id == edit_a.id)
        edit_b_after = next(e for e in svc.current.active_timeline.edits if e.id == edit_b.id)
        assert edit_a_after.status == EditStatus.REJECTED
        assert edit_b_after.status == EditStatus.PENDING

    def test_split_segment_cuts_range_edits_crossing_position(self, tmp_dir, monkeypatch, sample_segments):
        """v2.1.1 A-2.4: range-targeted ED crossing the split position must be
        cut into two EDs at position; non-crossing EDs stay as-is."""
        from core.models import EditDecision
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])

        # seg-0001 spans roughly [0, 5]; inject 3 range EDs manually:
        # - crossing_ed [2, 4]: crosses split at 3 -> should be cut
        # - left_ed     [1, 2]: fully left -> keep
        # - right_ed    [4, 5]: fully right -> keep
        crossing_ed = EditDecision(id="rx", start=2.0, end=4.0, action="delete",
                                   target_type="range", target_id=None)
        left_ed = EditDecision(id="rl", start=1.0, end=2.0, action="delete",
                               target_type="range", target_id=None)
        right_ed = EditDecision(id="rr", start=4.0, end=5.0, action="delete",
                                target_type="range", target_id=None)
        svc._update_active_timeline(edits=list(svc.active_timeline.edits) + [crossing_ed, left_ed, right_ed])

        result = svc.split_segment("seg-0001", 3.0)
        assert result["success"] is True
        edits = svc.current.active_timeline.edits
        ids = {e.id for e in edits}
        # crossing_ed is split into _a and _b; original rx dropped
        assert "rx_a" in ids and "rx_b" in ids and "rx" not in ids
        rx_a = next(e for e in edits if e.id == "rx_a")
        rx_b = next(e for e in edits if e.id == "rx_b")
        assert rx_a.start == 2.0 and rx_a.end == 3.0
        assert rx_b.start == 3.0 and rx_b.end == 4.0
        # left/right EDs untouched
        assert "rl" in ids and "rr" in ids
