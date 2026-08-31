"""Tests for core.project_service."""

from core import migrations
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

    def test_get_edit_summary_excludes_pending(self, tmp_dir, monkeypatch):
        """Regression for v2.3.1: summary must only count CONFIRMED deletes.

        Earlier get_edit_summary filtered `status in (PENDING, CONFIRMED)`,
        which made the export modal show inflated edit_count / delete_duration
        / delete_percent compared to the top-right status badge (which uses
        frontend useExport.confirmedEdits, status=="confirmed" only). The two
        displays must stay numerically identical.
        """
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 100.0})
        # 3 silence segments -> 3 PENDING edits
        svc.add_silence_results([
            {"start": 5.0, "end": 5.5},    # 0.5s
            {"start": 10.0, "end": 11.0},  # 1.0s
            {"start": 20.0, "end": 22.0},  # 2.0s
        ])
        edits = svc.current.active_timeline.edits
        assert len(edits) == 3
        assert all(e.status == EditStatus.PENDING for e in edits)

        # Pre-confirm: summary should report ZERO (all still pending)
        result_all_pending = svc.get_edit_summary()
        assert result_all_pending["success"] is True
        assert result_all_pending["data"]["edit_count"] == 0
        assert result_all_pending["data"]["delete_duration"] == 0.0

        # Confirm only the first edit
        svc.update_edit_decision(edits[0].id, EditStatus.CONFIRMED)

        result_one_confirmed = svc.get_edit_summary()
        assert result_one_confirmed["success"] is True
        assert result_one_confirmed["data"]["edit_count"] == 1
        assert abs(result_one_confirmed["data"]["delete_duration"] - 0.5) < 0.01

        # Reject the second; confirm the third
        svc.update_edit_decision(edits[1].id, EditStatus.REJECTED)
        svc.update_edit_decision(edits[2].id, EditStatus.CONFIRMED)

        result_mixed = svc.get_edit_summary()
        assert result_mixed["success"] is True
        assert result_mixed["data"]["edit_count"] == 2
        # 0.5 + 2.0 = 2.5s, NOT 0.5+1.0+2.0=3.5s
        assert abs(result_mixed["data"]["delete_duration"] - 2.5) < 0.01

    def test_generate_subtitle_keep_ranges_creates_confirmed_edits(
        self, tmp_dir, monkeypatch, sample_segments
    ):
        """Regression for v2.3.1 Bug C: subtitle_trim edits must be CONFIRMED.

        Before: created as PENDING, which made export silently ignore them
        while frontend preview (WorkspacePage.vue:194, PreviewPlayer.vue:30)
        treated source=subtitle_trim as implicitly confirmed. Result: user
        saw jumps in preview but exported file kept the gaps.
        """
        from core.export_service import _get_confirmed_deletions
        from core.export_timeline import _build_keep_ranges

        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True
        assert result["data"]["new_edits"] > 0

        edits = svc.current.active_timeline.edits
        subtitle_trim_edits = [e for e in edits if e.source == "subtitle_trim"]
        assert len(subtitle_trim_edits) > 0

        # Core regression: every subtitle_trim edit is CONFIRMED at creation
        assert all(e.status == EditStatus.CONFIRMED for e in subtitle_trim_edits), (
            f"subtitle_trim edits must be CONFIRMED, got statuses: "
            f"{[e.status for e in subtitle_trim_edits]}"
        )
        assert all(e.action == "delete" for e in subtitle_trim_edits)

        # End-to-end: these edits are now picked up by export pipelines
        edit_dicts = [e.model_dump() for e in subtitle_trim_edits]

        # export_video / export_audio / export_srt / export_vtt path
        confirmed_deletions = _get_confirmed_deletions(edit_dicts)
        assert len(confirmed_deletions) == len(subtitle_trim_edits), (
            "export_service._get_confirmed_deletions must pick up all subtitle_trim edits"
        )

        # export_edl / export_xmeml / export_otio path
        total_duration = max(s.end for s in svc.current.active_timeline.transcript.segments)
        keep_ranges = _build_keep_ranges([], edit_dicts, total_duration, fps=30.0)
        # With all subtitle_trim deletes applied, keep_ranges excludes every gap
        assert len(keep_ranges) >= 1
        kept_total = sum(e - s for s, e in keep_ranges)
        deleted_total = sum(e[1] - e[0] for e in confirmed_deletions)
        assert abs((kept_total + deleted_total) - total_duration) < 0.5, (
            "keep + delete must cover the full timeline"
        )

    def test_subtitle_trim_edits_counted_in_summary(
        self, tmp_dir, monkeypatch, sample_segments
    ):
        """After Bug C fix, get_edit_summary counts subtitle_trim edits too.

        This keeps the export modal in sync with the top-right badge.
        """
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])

        svc.generate_subtitle_keep_ranges(padding=0.3)

        result = svc.get_edit_summary()
        assert result["success"] is True
        assert result["data"]["edit_count"] > 0
        assert result["data"]["delete_duration"] > 0
        # No silence_detection / user edits involved; every counted edit is subtitle_trim
        subtitle_trim_edits = [
            e for e in svc.current.active_timeline.edits if e.source == "subtitle_trim"
        ]
        assert result["data"]["edit_count"] == len(subtitle_trim_edits)

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

    def test_delete_edit_decisions_batch_cascades_to_analysis_results(self, tmp_dir, monkeypatch):
        """Bug F: deleting edits should also clean associated AnalysisResults."""
        svc = self._create_service(tmp_dir, monkeypatch)
        mp = str(self._create_media_file(tmp_dir))
        svc.create_project("cascade-test", mp, {"duration": 60.0})

        # Add a subtitle segment so add_analysis_results can match it
        from core.models import Segment, SegmentType
        test_seg = Segment(id="s_test", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="test")
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [test_seg]}
            )
        )

        # Add an AnalysisResult with associated EditDecision
        ar_results = [{
            "id": "ar_test_1",
            "type": "llm_smart_delete",
            "segment_ids": ["s_test"],
            "confidence": 0.9,
            "detail": "test",
        }]
        svc.add_analysis_results(ar_results, source="llm_smart")

        # Verify both AnalysisResult and EditDecision exist
        tl = svc.active_timeline
        assert len(tl.analysis.results) == 1
        assert tl.analysis.results[0].id == "ar_test_1"
        smart_edits = [e for e in tl.edits if e.source == "llm_smart"]
        assert len(smart_edits) == 1
        assert smart_edits[0].analysis_id == "ar_test_1"

        # Delete the edit decision
        result = svc.delete_edit_decisions_batch([smart_edits[0].id])
        assert result["success"]

        # Verify both EditDecision AND AnalysisResult are gone
        tl = svc.active_timeline
        smart_edits_after = [e for e in tl.edits if e.source == "llm_smart"]
        assert len(smart_edits_after) == 0, "EditDecision should be removed"
        remaining_ars = [r for r in tl.analysis.results if r.id == "ar_test_1"]
        assert len(remaining_ars) == 0, "AnalysisResult should be cascade-removed"

    def test_migrate_highlights_fixes_legacy_actions(self, tmp_dir, monkeypatch):
        """Phase 4: _migrate_highlights should fix action=delete to keep for highlights."""
        from core.models import AnalysisResult, EditDecision, EditStatus

        svc = self._create_service(tmp_dir, monkeypatch)
        mp = str(self._create_media_file(tmp_dir))
        svc.create_project("migrate-test", mp, {"duration": 60.0})

        # Add a subtitle segment
        from core.models import Segment, SegmentType
        test_seg = Segment(id="s_migrate", type=SegmentType.SUBTITLE, start=0.0, end=10.0, text="test")
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [test_seg]}
            )
        )

        seg_id = "s_migrate"

        # Simulate legacy: add analysis result + edit with action="delete"
        ar = AnalysisResult(
            id="llm_hl_old",
            type="llm_highlight",
            segment_ids=[seg_id],
            confidence=1.0,
            detail="old highlight",
        )
        legacy_edit = EditDecision(
            id="edit-llm_hl_old",
            start=0.0,
            end=10.0,
            action="delete",  # Bug E: wrong action
            source="llm_highlight",
            analysis_id="llm_hl_old",
            status=EditStatus.PENDING,
            priority=100,
            target_type="segment",
            target_id=seg_id,
        )
        svc._update_active_timeline(
            analysis=svc.active_timeline.analysis.model_copy(
                update={"results": list(svc.active_timeline.analysis.results) + [ar]}
            ),
            edits=list(svc.active_timeline.edits) + [legacy_edit],
        )

        # Run migration
        migrations.migrate_highlights(svc)

        # Verify action is now "keep"
        tl = svc.active_timeline
        hl_edits = [e for e in tl.edits if e.source == "llm_highlight"]
        assert len(hl_edits) == 1
        assert hl_edits[0].action == "keep", (
            f"Migration should fix action to 'keep', got '{hl_edits[0].action}'"
        )

    # --- Bug fix: silence detection must not overwrite user/AI decisions ---

    def _add_subtitle_with_user_edit(
        self, svc, seg_id, start, end, action="delete", status="rejected"
    ):
        """Helper: add a subtitle segment and a user-source edit on it."""
        from core.models import EditDecision, EditStatus, Segment, SegmentType
        seg = Segment(id=seg_id, type=SegmentType.SUBTITLE, start=start, end=end, text="x")
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [seg]}
            ),
        )
        user_edit = EditDecision(
            id=f"edit-user-{seg_id}",
            start=start,
            end=end,
            action=action,
            source="user",
            status=EditStatus(status),
            priority=200,
            target_type="segment",
            target_id=seg_id,
        )
        svc._update_active_timeline(
            edits=list(svc.active_timeline.edits) + [user_edit],
        )

    def test_silence_respects_user_rejected_edit(self, tmp_dir, monkeypatch):
        """Bug: silence detection must NOT create a delete edit overlapping a
        user-rejected subtitle (user said 'keep'). Reproduces the overwrite bug."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        # User rejected delete on subtitle 5.0-8.0 (wants to KEEP it)
        self._add_subtitle_with_user_edit(
            svc, "seg-keep", start=5.0, end=8.0, action="delete", status="rejected"
        )
        # Silence detection finds silence 5.5-7.5 (inside the rejected subtitle)
        result = svc.add_silence_results([{"start": 5.5, "end": 7.5}])
        assert result["success"] is True
        # Silence SEGMENT is created (informational)
        sil_segs = [s for s in svc.current.active_timeline.transcript.segments
                    if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 1
        # But NO silence edit should be created (respects user reject)
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 0, (
            "Silence detection must not create a delete edit that overwrites a user rejected range. "
            f"Got: {sil_edits}"
        )

    def test_silence_respects_user_confirmed_edit(self, tmp_dir, monkeypatch):
        """User already confirmed delete on a subtitle; silence detection in
        the same range must not create a competing edit."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._add_subtitle_with_user_edit(
            svc, "seg-del", start=10.0, end=15.0, action="delete", status="confirmed"
        )
        result = svc.add_silence_results([{"start": 10.5, "end": 14.5}])
        assert result["success"] is True
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 0, (
            "Silence detection must not duplicate a user-confirmed delete range."
        )

    def test_silence_respects_llm_confirmed_edit(self, tmp_dir, monkeypatch):
        """LLM smart-delete already confirmed by user; silence detection in
        overlapping range must not override."""
        from core.models import EditDecision, EditStatus
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        # Simulate a confirmed LLM smart-delete edit
        llm_edit = EditDecision(
            id="edit-llm-1",
            start=20.0,
            end=25.0,
            action="delete",
            source="llm_smart_delete",
            status=EditStatus.CONFIRMED,
            priority=100,
            target_type="range",
        )
        svc._update_active_timeline(
            edits=list(svc.active_timeline.edits) + [llm_edit],
        )
        result = svc.add_silence_results([{"start": 21.0, "end": 24.0}])
        assert result["success"] is True
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 0, (
            "Silence detection must not override a confirmed LLM decision."
        )

    def test_silence_dedupes_existing_silence_edit(self, tmp_dir, monkeypatch):
        """Re-running silence detection in a range already covered by a silence
        edit must not create a duplicate edit (segment is OK for idempotency)."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        # First run: creates silence edit at 5.0-6.0
        svc.add_silence_results([{"start": 5.0, "end": 6.0}])
        # Second run: overlapping range 5.2-5.8
        result = svc.add_silence_results([{"start": 5.2, "end": 5.8}])
        assert result["success"] is True
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 1, (
            f"Silence detection must dedupe overlapping silence edits. Got {len(sil_edits)}."
        )

    def test_silence_creates_for_uncovered_range(self, tmp_dir, monkeypatch):
        """Control: no prior decisions in this range -> silence edit is created normally."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        result = svc.add_silence_results([{"start": 30.0, "end": 35.0}])
        assert result["success"] is True
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 1

    def test_silence_partial_overlap_blocks_when_significant(self, tmp_dir, monkeypatch):
        """Silence range overlapping a user edit by > 0.3s is blocked; minor
        touch (< 0.3s) is allowed since it's just edge adjacency."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        # User rejected 10.0-15.0
        self._add_subtitle_with_user_edit(
            svc, "seg-keep", start=10.0, end=15.0, action="delete", status="rejected"
        )
        # Overlap > 0.3s: 14.5-16.0 overlaps by 0.5s -> blocked
        svc.add_silence_results([{"start": 14.5, "end": 16.0}])
        sil_edits = [e for e in svc.current.active_timeline.edits
                     if e.source == "silence_detection"]
        assert len(sil_edits) == 0, "Overlap > 0.3s with user edit must block."

    def test_migrate_silence_overlapping_user_rejected(self, tmp_dir, monkeypatch):
        """Migration: existing silence_detection confirmed-delete edits that
        overlap a user-rejected-delete edit should be marked rejected on project open.
        Reproduces and repairs the user's corrupted project data scenario."""
        from core.models import EditDecision, EditStatus, Segment, SegmentType
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("repair-test", self._create_media_file(tmp_dir), {"duration": 60.0})

        # Simulate corrupted state: user rejected seg, but silence_detection confirmed-delete
        seg = Segment(id="seg-x", type=SegmentType.SUBTITLE, start=100.0, end=110.0, text="x")
        user_reject = EditDecision(
            id="edit-user-seg-x", start=100.0, end=110.0,
            action="delete", source="user", status=EditStatus.REJECTED,
            priority=200, target_type="segment", target_id="seg-x",
        )
        sil_confirmed = EditDecision(
            id="edit-sil-bad", start=101.0, end=109.0,
            action="delete", source="silence_detection", status=EditStatus.CONFIRMED,
            target_type="segment", target_id="sil-bad",
        )
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [seg]}
            ),
            edits=[user_reject, sil_confirmed],
        )

        # Run migration
        migrations.migrate_overlapping_silence_edits(svc)

        # Verify: the silence edit should now be rejected (respecting user decision)
        sil_edits = [e for e in svc.active_timeline.edits if e.source == "silence_detection"]
        assert len(sil_edits) == 1
        assert sil_edits[0].status == EditStatus.REJECTED, (
            f"Migration must reject silence edits overlapping user-rejected ranges. "
            f"Got status={sil_edits[0].status}"
        )

    def test_silence_does_not_wipe_analysis_results(self, tmp_dir, monkeypatch):
        """CRITICAL REGRESSION: add_silence_results must NOT replace the analysis
        data object. Older versions did `analysis=AnalysisData(last_run=...)` which
        silently wiped all LLM analysis results (smart_delete, subtitle_correction,
        highlight) and then _migrate_highlights removed the now-orphaned edits.
        This is the root cause of 'silence detection overwrites AI suggestions'."""
        from core.models import AnalysisData, AnalysisResult
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})

        # Seed existing analysis results (simulating prior LLM smart-delete run)
        existing_ar = AnalysisResult(
            id="ar-llm-1",
            type="llm_smart_delete",
            segment_ids=["seg-0001"],
            confidence=0.9,
            detail="filler",
        )
        svc._update_active_timeline(
            analysis=AnalysisData(
                last_run="2025-01-01T00:00:00",
                results=[existing_ar],
            )
        )

        # Run silence detection
        result = svc.add_silence_results([{"start": 30.0, "end": 35.0}])
        assert result["success"] is True

        # Analysis results MUST be preserved
        analysis = svc.current.active_timeline.analysis
        assert len(analysis.results) == 1, (
            f"Silence detection must not wipe analysis results. "
            f"Got {len(analysis.results)} results."
        )
        assert analysis.results[0].id == "ar-llm-1"

    # --- LLM re-run must not overwrite user decisions ---

    def _seed_subtitles_and_user_edit(
        self, svc, seg_id, start, end, user_action="delete", user_status="rejected"
    ):
        """Helper: add a subtitle segment and a user-source edit bound to it."""
        from core.models import EditDecision, EditStatus, Segment, SegmentType
        seg = Segment(id=seg_id, type=SegmentType.SUBTITLE, start=start, end=end, text="x")
        user_edit = EditDecision(
            id=f"edit-user-{seg_id}",
            start=start, end=end,
            action=user_action, source="user",
            status=EditStatus(user_status),
            priority=200, target_type="segment", target_id=seg_id,
        )
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [seg]}
            ),
            edits=list(svc.active_timeline.edits) + [user_edit],
        )

    def test_llm_skips_edit_for_user_rejected_segment(self, tmp_dir, monkeypatch):
        """Re-running LLM smart-delete must NOT create a competing edit on a
        segment the user has already rejected deletion on (wants to keep).
        Without protection, the new PENDING LLM edit becomes topActive in
        resolveSegmentState and flips the segment back to 'pending delete'."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        # User rejected delete on seg-keep (wants to KEEP it)
        self._seed_subtitles_and_user_edit(
            svc, "seg-keep", start=10.0, end=15.0,
            user_action="delete", user_status="rejected",
        )

        results = [{
            "id": "ar-llm-1",
            "type": "llm_smart_delete",
            "segment_ids": ["seg-keep"],
            "confidence": 0.9,
            "detail": "filler",
        }]
        result = svc.add_analysis_results(results, source="llm_smart")
        assert result["success"] is True

        # AnalysisResult is still stored (record-keeping)
        assert len(svc.current.active_timeline.analysis.results) == 1
        # But NO EditDecision should be created for this segment
        llm_edits = [e for e in svc.current.active_timeline.edits if e.source == "llm_smart"]
        assert len(llm_edits) == 0, (
            f"LLM must not create a competing edit on a user-rejected segment. Got: {llm_edits}"
        )

    def test_llm_skips_edit_for_user_confirmed_segment(self, tmp_dir, monkeypatch):
        """User already confirmed delete; LLM re-run must not duplicate."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._seed_subtitles_and_user_edit(
            svc, "seg-del", start=20.0, end=25.0,
            user_action="delete", user_status="confirmed",
        )
        results = [{
            "id": "ar-llm-2",
            "type": "llm_smart_delete",
            "segment_ids": ["seg-del"],
            "confidence": 0.8,
            "detail": "off-topic",
        }]
        svc.add_analysis_results(results, source="llm_smart")
        llm_edits = [e for e in svc.current.active_timeline.edits if e.source == "llm_smart"]
        assert len(llm_edits) == 0, "LLM must not duplicate a user-confirmed decision."

    def test_llm_creates_edit_for_unedited_segment(self, tmp_dir, monkeypatch):
        """Control: segment with no user edit -> LLM edit is created normally."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        self._seed_subtitles_and_user_edit(
            svc, "seg-other", start=10.0, end=15.0,
            user_action="delete", user_status="confirmed",
        )
        # Also add a segment the user has NOT touched
        from core.models import Segment, SegmentType
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={
                    "segments": list(svc.active_timeline.transcript.segments) + [
                        Segment(id="seg-free", type=SegmentType.SUBTITLE,
                                start=30.0, end=35.0, text="y")
                    ]
                }
            )
        )
        results = [{
            "id": "ar-llm-3",
            "type": "llm_smart_delete",
            "segment_ids": ["seg-free"],
            "confidence": 0.7,
            "detail": "filler",
        }]
        svc.add_analysis_results(results, source="llm_smart")
        llm_edits = [e for e in svc.current.active_timeline.edits if e.source == "llm_smart"]
        assert len(llm_edits) == 1, "LLM must create edit for unedited segment."

    def test_llm_skips_when_any_segment_in_result_has_user_edit(self, tmp_dir, monkeypatch):
        """AnalysisResult references multiple segments; if ANY has a user edit,
        the whole result's edit is skipped (user has reviewed part of this group)."""
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", self._create_media_file(tmp_dir), {"duration": 60.0})
        from core.models import Segment, SegmentType
        # seg-A has user edit, seg-B does not
        self._seed_subtitles_and_user_edit(
            svc, "seg-A", start=10.0, end=15.0,
            user_action="delete", user_status="rejected",
        )
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={
                    "segments": list(svc.active_timeline.transcript.segments) + [
                        Segment(id="seg-B", type=SegmentType.SUBTITLE,
                                start=15.0, end=20.0, text="b")
                    ]
                }
            )
        )
        # LLM suggests deleting both A and B as a group
        results = [{
            "id": "ar-llm-group",
            "type": "llm_smart_delete",
            "segment_ids": ["seg-A", "seg-B"],
            "confidence": 0.85,
            "detail": "repetition",
        }]
        svc.add_analysis_results(results, source="llm_smart")
        llm_edits = [e for e in svc.current.active_timeline.edits if e.source == "llm_smart"]
        assert len(llm_edits) == 0, (
            "If any segment in the result has a user edit, skip the whole edit."
        )

    def test_migrate_highlights_removes_orphan_edits(self, tmp_dir, monkeypatch):
        """Phase 4: _migrate_highlights should remove orphan edits whose analysis_id is gone."""
        from core.models import EditDecision, EditStatus

        svc = self._create_service(tmp_dir, monkeypatch)
        mp = str(self._create_media_file(tmp_dir))
        svc.create_project("orphan-test", mp, {"duration": 60.0})

        # Add a subtitle segment
        from core.models import Segment, SegmentType
        test_seg = Segment(id="s_orphan", type=SegmentType.SUBTITLE, start=0.0, end=10.0, text="test")
        svc._update_active_timeline(
            transcript=svc.active_timeline.transcript.model_copy(
                update={"segments": list(svc.active_timeline.transcript.segments) + [test_seg]}
            )
        )

        seg_id = "s_orphan"

        orphan_edit = EditDecision(
            id="edit-manual_hl_orphan",
            start=0.0,
            end=10.0,
            action="keep",
            source="manual_highlight",
            analysis_id="manual_hl_gone",  # No matching AnalysisResult
            status=EditStatus.PENDING,
            priority=100,
            target_type="segment",
            target_id=seg_id,
        )
        svc._update_active_timeline(
            edits=list(svc.active_timeline.edits) + [orphan_edit],
        )

        # Run migration
        migrations.migrate_highlights(svc)

        # Verify orphan is removed
        tl = svc.active_timeline
        orphans = [e for e in tl.edits if e.analysis_id == "manual_hl_gone"]
        assert len(orphans) == 0, f"Orphan edit should be removed: {orphans}"
