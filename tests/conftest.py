"""Shared fixtures for Milo-Cut tests.

Fixtures are thin wrappers over the centralized mock factories in
``tests.mocks``. New tests should prefer importing the factories directly.
"""

from __future__ import annotations

import pytest

from tests.mocks.factories import (
    SAMPLE_SRT_CONTENT,
    make_edit_decision,
    make_project,
    make_segment,
)


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test isolation."""
    return tmp_path


@pytest.fixture
def sample_segment():
    """Create a sample subtitle segment."""
    return make_segment(id="seg-0001", start=1.0, end=5.0, text="Hello world")


@pytest.fixture
def sample_segments():
    """Create a list of sample subtitle segments."""

    return [
        make_segment(id="seg-0001", start=1.0, end=5.0, text="Hello world"),
        make_segment(id="seg-0002", start=5.5, end=10.0, text="This is a test"),
        make_segment(id="seg-0003", start=10.5, end=15.0, text="Filler word here"),
        make_segment(
            id="seg-0004", start=15.5, end=20.0, text="不对重来说错了这段不要"
        ),
        make_segment(id="seg-0005", start=20.5, end=25.0, text="Normal sentence"),
        make_segment(id="seg-0006", start=25.5, end=30.0, text="Another segment"),
    ]


@pytest.fixture
def sample_silence_segment():
    """Create a sample silence segment."""
    from core.models import SegmentType

    return make_segment(
        id="sil-0001", type=SegmentType.SILENCE, start=5.0, end=5.5, text=""
    )


@pytest.fixture
def sample_edit_decision():
    """Create a sample edit decision."""
    return make_edit_decision(
        id="edit-0001",
        start=5.0,
        end=5.5,
        action="delete",
        source="silence_detection",
    )


@pytest.fixture
def sample_project(sample_segments, sample_silence_segment, sample_edit_decision):
    """Create a sample project with segments and edits."""
    return make_project(
        segments=list(sample_segments) + [sample_silence_segment],
        edits=[sample_edit_decision],
    )


@pytest.fixture
def sample_srt_content():
    """Sample SRT content for testing."""
    return SAMPLE_SRT_CONTENT


@pytest.fixture
def srt_file(tmp_dir, sample_srt_content):
    """Create a temporary SRT file."""
    path = tmp_dir / "test.srt"
    path.write_text(sample_srt_content, encoding="utf-8")
    return str(path)
