"""Tests for core.models data models."""

import pytest
from pydantic import ValidationError

from core.models import (
    AnalysisData,
    AnalysisResult,
    EditDecision,
    EditStatus,
    Project,
    Segment,
    SegmentType,
    TaskType,
)


class TestTaskType:
    def test_phase0_types_exist(self):
        assert TaskType.SILENCE_DETECTION == "silence_detection"
        assert TaskType.EXPORT_VIDEO == "export_video"
        assert TaskType.EXPORT_SUBTITLE == "export_subtitle"

class TestSegment:
    def test_frozen(self, sample_segment):
        with pytest.raises(ValidationError):
            sample_segment.text = "changed"

    def test_default_type(self):
        seg = Segment(id="s1", start=0.0, end=1.0, text="test")
        assert seg.type == SegmentType.SUBTITLE

    def test_dirty_flags_default(self, sample_segment):
        assert sample_segment.dirty_flags == {}

    def test_silence_type(self):
        seg = Segment(id="s1", type=SegmentType.SILENCE, start=0.0, end=1.0)
        assert seg.type == SegmentType.SILENCE
        assert seg.text == ""


class TestEditDecision:
    def test_defaults(self):
        ed = EditDecision(id="e1", start=0.0, end=1.0)
        assert ed.action == "delete"
        assert ed.status == EditStatus.PENDING
        assert ed.priority == 100

    def test_frozen(self, sample_edit_decision):
        with pytest.raises(ValidationError):
            sample_edit_decision.status = EditStatus.CONFIRMED


class TestAnalysisResult:
    def test_create(self):
        ar = AnalysisResult(
            id="ar-1",
            type="llm_smart_delete",
            segment_ids=["seg-0001"],
            confidence=0.9,
            detail="test",
        )
        assert ar.type == "llm_smart_delete"
        assert ar.confidence == 0.9

    def test_frozen(self):
        ar = AnalysisResult(id="ar-1", type="llm_smart_delete")
        with pytest.raises(ValidationError):
            ar.type = "llm_highlight"


class TestAnalysisData:
    def test_default_results(self):
        ad = AnalysisData()
        assert ad.results == []
        assert ad.last_run is None

    def test_with_results(self):
        ar = AnalysisResult(id="ar-1", type="llm_smart_delete")
        ad = AnalysisData(results=[ar])
        assert len(ad.results) == 1


class TestProject:
    def test_default_schema_version(self, sample_project):
        assert sample_project.schema_version == 2

    def test_model_dump_roundtrip(self, sample_project):
        data = sample_project.model_dump()
        restored = Project.model_validate(data)
        assert restored.project.name == "test-project"
        assert len(restored.active_timeline.transcript.segments) == 7

    def test_model_copy_update(self, sample_project):
        updated = sample_project.model_copy(
            update={
                "project": sample_project.project.model_copy(update={"name": "new-name"}),
            }
        )
        assert updated.project.name == "new-name"
        assert sample_project.project.name == "test-project"
