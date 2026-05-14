"""Tests for core.project_service."""

import json
from pathlib import Path

from core.models import EditStatus, SegmentType
from core.project_service import ProjectService


class TestProjectService:
    def _create_service(self, tmp_dir, monkeypatch):
        """Create a ProjectService with isolated paths."""
        monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_dir / "projects")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        svc = ProjectService()
        return svc

    def test_create_and_open(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        assert result["success"] is True
        assert svc.current is not None
        assert svc.current.project.name == "test"

    def test_save_and_reload(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
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
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.close_project()
        assert svc.current is None

    def test_update_transcript(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        segs = [s.model_dump() for s in sample_segments]
        result = svc.update_transcript(segs)
        assert result["success"] is True
        assert len(svc.current.transcript.segments) == len(sample_segments)

    def test_add_silence_results(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        silences = [{"start": 5.0, "end": 5.5}, {"start": 10.0, "end": 11.0}]
        result = svc.add_silence_results(silences)
        assert result["success"] is True
        sil_segs = [s for s in svc.current.transcript.segments if s.type == SegmentType.SILENCE]
        assert len(sil_segs) == 2
        assert len(svc.current.edits) == 2

    def test_update_edit_decision(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        edit_id = svc.current.edits[0].id
        result = svc.update_edit_decision(edit_id, "confirmed")
        assert result["success"] is True
        assert svc.current.edits[0].status == EditStatus.CONFIRMED

    def test_update_segment(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.update_segment("seg-0001", {"text": "Updated text"})
        assert result["success"] is True
        seg = next(s for s in svc.current.transcript.segments if s.id == "seg-0001")
        assert seg.text == "Updated text"

    def test_merge_segments(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.merge_segments(["seg-0001", "seg-0002"])
        assert result["success"] is True
        merged = [s for s in svc.current.transcript.segments if s.id == "seg-0001"]
        assert len(merged) == 1
        assert "Hello world" in merged[0].text
        assert "This is a test" in merged[0].text

    def test_split_segment(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.split_segment("seg-0001", 3.0)
        assert result["success"] is True
        segs = svc.current.transcript.segments
        a = next((s for s in segs if s.id == "seg-0001-a"), None)
        b = next((s for s in segs if s.id == "seg-0001-b"), None)
        assert a is not None
        assert b is not None
        assert a.end == 3.0
        assert b.start == 3.0

    def test_search_replace(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.search_replace("Hello", "Hi")
        assert result["success"] is True
        assert result["data"]["count"] == 1
        seg = next(s for s in svc.current.transcript.segments if s.id == "seg-0001")
        assert seg.text == "Hi world"

    def test_mark_segments(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.mark_segments(["seg-0001"], "delete")
        assert result["success"] is True
        assert len(svc.current.edits) > 0

    def test_confirm_all_suggestions(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}, {"start": 10.0, "end": 11.0}])
        result = svc.confirm_all_suggestions()
        assert result["success"] is True
        assert result["data"]["confirmed_count"] == 2
        assert all(e.status == EditStatus.CONFIRMED for e in svc.current.edits)

    def test_reject_all_suggestions(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        result = svc.reject_all_suggestions()
        assert result["success"] is True
        assert svc.current.edits[0].status == EditStatus.REJECTED

    def test_get_edit_summary(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.add_silence_results([{"start": 5.0, "end": 5.5}])
        svc.confirm_all_suggestions()
        result = svc.get_edit_summary()
        assert result["success"] is True
        assert result["data"]["edit_count"] == 1

    def test_add_analysis_results(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        results = [{"id": "ar-1", "type": "filler", "segment_ids": ["seg-0001"], "confidence": 0.9, "detail": "test"}]
        result = svc.add_analysis_results(results, source="test")
        assert result["success"] is True
        assert len(svc.current.analysis.results) == 1
        assert len(svc.current.edits) > 0

    def test_update_segment_text(self, tmp_dir, monkeypatch, sample_segments):
        svc = self._create_service(tmp_dir, monkeypatch)
        svc.create_project("test", "/tmp/test.mp4", {"duration": 60.0})
        svc.update_transcript([s.model_dump() for s in sample_segments])
        result = svc.update_segment_text("seg-0001", "New text")
        assert result["success"] is True
        seg = next(s for s in svc.current.transcript.segments if s.id == "seg-0001")
        assert seg.text == "New text"
        assert seg.dirty_flags.get("text_edited") is True

    def test_get_settings(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.get_settings()
        assert result["success"] is True
        assert "filler_words" in result["data"]

    def test_get_recent_projects_empty(self, tmp_dir, monkeypatch):
        svc = self._create_service(tmp_dir, monkeypatch)
        result = svc.get_recent_projects()
        assert result["success"] is True
        assert result["data"] == []
