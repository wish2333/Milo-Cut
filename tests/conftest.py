"""Shared fixtures for Milo-Cut tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.models import (
    AnalysisData,
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    TranscriptData,
)


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test isolation."""
    return tmp_path


@pytest.fixture
def sample_segment():
    """Create a sample subtitle segment."""
    return Segment(
        id="seg-0001",
        type=SegmentType.SUBTITLE,
        start=1.0,
        end=5.0,
        text="Hello world",
    )


@pytest.fixture
def sample_segments():
    """Create a list of sample subtitle segments."""
    return [
        Segment(id="seg-0001", type=SegmentType.SUBTITLE, start=1.0, end=5.0, text="Hello world"),
        Segment(id="seg-0002", type=SegmentType.SUBTITLE, start=5.5, end=10.0, text="This is a test"),
        Segment(id="seg-0003", type=SegmentType.SUBTITLE, start=10.5, end=15.0, text="Filler word here"),
        Segment(id="seg-0004", type=SegmentType.SUBTITLE, start=15.5, end=20.0, text="不对重来说错了这段不要"),
        Segment(id="seg-0005", type=SegmentType.SUBTITLE, start=20.5, end=25.0, text="Normal sentence"),
        Segment(id="seg-0006", type=SegmentType.SUBTITLE, start=25.5, end=30.0, text="Another segment"),
    ]


@pytest.fixture
def sample_silence_segment():
    """Create a sample silence segment."""
    return Segment(
        id="sil-0001",
        type=SegmentType.SILENCE,
        start=5.0,
        end=5.5,
        text="",
    )


@pytest.fixture
def sample_edit_decision():
    """Create a sample edit decision."""
    return EditDecision(
        id="edit-0001",
        start=5.0,
        end=5.5,
        action="delete",
        source="silence_detection",
        status=EditStatus.PENDING,
    )


@pytest.fixture
def sample_project(sample_segments, sample_silence_segment, sample_edit_decision):
    """Create a sample project with segments and edits."""
    return Project(
        project=ProjectMeta(name="test-project"),
        media=MediaInfo(path="/tmp/test.mp4", duration=60.0),
        transcript=TranscriptData(segments=list(sample_segments) + [sample_silence_segment]),
        analysis=AnalysisData(),
        edits=[sample_edit_decision],
    )


@pytest.fixture
def sample_srt_content():
    """Sample SRT content for testing."""
    return """1
00:00:01,000 --> 00:00:05,000
Hello world

2
00:00:05,500 --> 00:00:10,000
This is a test

3
00:00:10,500 --> 00:00:15,000
Filler word here
"""


@pytest.fixture
def srt_file(tmp_dir, sample_srt_content):
    """Create a temporary SRT file."""
    path = tmp_dir / "test.srt"
    path.write_text(sample_srt_content, encoding="utf-8")
    return str(path)
