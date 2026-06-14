"""Centralized test mock factories.

All test data construction should go through these factories to avoid
field-sync issues when models change (see audit L-02).

Usage::

    from tests.mocks import make_segment, make_project

    seg = make_segment(id="s1", text="hello")
    proj = make_project(segments=[seg])
"""

from __future__ import annotations

from core.models import (
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    TranscriptData,
)

# Common sample SRT content used across subtitle + export tests
SAMPLE_SRT_CONTENT = """1
00:00:01,000 --> 00:00:05,000
Hello world

2
00:00:05,500 --> 00:00:10,000
This is a test

3
00:00:10,500 --> 00:00:15,000
Filler word here
"""

# Default segment list mirroring conftest.sample_segments
SAMPLE_SEGMENTS_RAW = [
    {"id": "seg-0001", "start": 1.0, "end": 5.0, "text": "Hello world"},
    {"id": "seg-0002", "start": 5.5, "end": 10.0, "text": "This is a test"},
    {"id": "seg-0003", "start": 10.5, "end": 15.0, "text": "Filler word here"},
    {"id": "seg-0004", "start": 15.5, "end": 20.0, "text": "不对重来说错了这段不要"},
    {"id": "seg-0005", "start": 20.5, "end": 25.0, "text": "Normal sentence"},
    {"id": "seg-0006", "start": 25.5, "end": 30.0, "text": "Another segment"},
]


def make_segment(
    *,
    id: str = "s1",
    type: SegmentType = SegmentType.SUBTITLE,
    start: float = 0.0,
    end: float = 5.0,
    text: str = "sample text",
    **kwargs,
) -> Segment:
    """Build a Segment with sensible defaults."""
    return Segment(id=id, type=type, start=start, end=end, text=text, **kwargs)


def make_segments(
    count: int = 3,
    *,
    prefix: str = "seg",
    start_offset: float = 0.0,
    duration: float = 5.0,
    gap: float = 0.5,
    text_template: str = "segment {}",
) -> list[Segment]:
    """Build a list of consecutive subtitle segments."""
    segments = []
    current = start_offset
    for i in range(count):
        segments.append(
            make_segment(
                id=f"{prefix}-{i + 1:04d}",
                start=current,
                end=current + duration,
                text=text_template.format(i + 1),
            )
        )
        current += duration + gap
    return segments


def make_edit_decision(
    *,
    id: str = "edit-0001",
    start: float = 5.0,
    end: float = 5.5,
    action: str = "delete",
    source: str = "manual",
    status: EditStatus = EditStatus.PENDING,
    **kwargs,
) -> EditDecision:
    """Build an EditDecision with sensible defaults."""
    return EditDecision(
        id=id,
        start=start,
        end=end,
        action=action,
        source=source,
        status=status,
        **kwargs,
    )


def make_project(
    *,
    segments: list[Segment] | None = None,
    edits: list[EditDecision] | None = None,
    name: str = "test-project",
    media: MediaInfo | None = None,
    **kwargs,
) -> Project:
    """Build a complete Project with all required fields populated.

    Uses the v2 multi-timeline schema: a single 'default' timeline containing
    the provided segments and edits.
    """
    from core.models import Timeline

    segs = segments if segments is not None else [make_segment()]
    timeline = Timeline(
        id="default",
        label="原始",
        source="default",
        transcript=TranscriptData(segments=segs),
        edits=edits if edits is not None else [],
    )
    return Project(
        project=ProjectMeta(name=name),
        media=media if media is not None else MediaInfo(path="/tmp/test.mp4", duration=60.0),
        timelines=[timeline],
        active_timeline_id="default",
        **kwargs,
    )


def make_llm_response(content: str, usage: dict | None = None) -> dict:
    """Build a mock call_llm return value matching the {success, data} envelope."""
    return {
        "success": True,
        "data": {
            "content": content,
            "usage": usage
            or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }
