"""Sort-invariant regression tests for v2.3.2 stage 3 (G4/G13).

Validates that the active timeline's ``transcript.segments`` is always
sorted by ``start`` ascending after any write that could disturb
ordering. The frontend ``WorkspacePage.mergedSegments`` computed relies
on this invariant to skip its per-render O(S log S) sort.
"""

from __future__ import annotations

import pytest

from core.models import SegmentType
from core.project_service import ProjectService


def _create_service(tmp_path, monkeypatch) -> ProjectService:
    monkeypatch.setattr("core.project_service.get_projects_dir", lambda: tmp_path)
    svc = ProjectService()
    media = tmp_path / "v.mp4"
    media.write_bytes(b"stub")
    svc.create_project("sort-test", str(media), {"duration": 100.0})
    return svc


def _seed_unsorted_subtitles(svc: ProjectService) -> None:
    """Insert subtitles in a deliberately non-sorted order."""
    svc.update_transcript([
        {"id": "s3", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "third"},
        {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
        {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
    ])


def _assert_sorted(svc: ProjectService) -> None:
    starts = [s.start for s in svc.current.active_timeline.transcript.segments]
    assert starts == sorted(starts), f"Segments not sorted by start: {starts}"


@pytest.fixture
def svc(tmp_path, monkeypatch) -> ProjectService:
    return _create_service(tmp_path, monkeypatch)


class TestUpdateTranscriptSortInvariant:
    def test_unsorted_input_gets_sorted(self, svc: ProjectService) -> None:
        _seed_unsorted_subtitles(svc)
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        assert ids == ["s1", "s2", "s3"]

    def test_preserves_silence_segments_after_sort(self, svc: ProjectService) -> None:
        svc.add_silence_results([
            {"start": 20.0, "end": 21.0},
            {"start": 5.0, "end": 6.0},
        ])
        _seed_unsorted_subtitles(svc)
        _assert_sorted(svc)
        silence_starts = [
            s.start for s in svc.current.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        ]
        assert silence_starts == sorted(silence_starts)

    def test_empty_input_keeps_existing_silence_sorted(self, svc: ProjectService) -> None:
        svc.add_silence_results([
            {"start": 50.0, "end": 51.0},
            {"start": 5.0, "end": 6.0},
        ])
        svc.update_transcript([])
        _assert_sorted(svc)


class TestAddSegmentSortInvariant:
    def test_add_at_beginning(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "b"},
        ])
        svc.add_segment(5.0, 7.0, "new first", "subtitle")
        _assert_sorted(svc)
        first_id = svc.current.active_timeline.transcript.segments[0].id
        assert first_id.startswith("sub-user")

    def test_add_in_middle(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "b"},
        ])
        svc.add_segment(20.0, 22.0, "middle", "subtitle")
        _assert_sorted(svc)


class TestUpdateSegmentSortInvariant:
    def test_moving_start_earlier_triggers_resort(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "b"},
            {"id": "c", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "c"},
        ])
        # Move c wholly before a -- this should re-sort. (v3.0.1 M2-1: the
        # original start-only move to 5.0 now overlaps a and is rejected,
        # so the move is expressed as an overlap-free whole-segment move.)
        svc.update_segment("c", {"start": 2.0, "end": 4.0})
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        assert ids[0] == "c"

    def test_moving_start_later_triggers_resort(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "b"},
            {"id": "c", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "c"},
        ])
        # Move a to between b and c
        svc.update_segment("a", {"start": 27.0})
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        assert ids[0] == "b"
        assert ids[1] == "a"

    def test_text_only_update_preserves_order(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "b"},
        ])
        svc.update_segment("a", {"text": "changed"})
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        assert ids == ["a", "b"]

    def test_end_only_update_preserves_order(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
        ])
        svc.update_segment("a", {"end": 18.0})
        _assert_sorted(svc)


class TestSplitSegmentSortInvariant:
    def test_split_preserves_order(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 20.0, "text": "abcdefghij"},
            {"id": "b", "type": "subtitle", "start": 30.0, "end": 40.0, "text": "klmnopqrst"},
        ])
        svc.split_segment("a", 15.0)
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        assert "a-a" in ids and "a-b" in ids
        # a-a (start 10) -> a-b (start 15) -> b (start 30)
        assert ids == ["a-a", "a-b", "b"]


class TestMergeSegmentSortInvariant:
    def test_merge_preserves_order(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "alpha"},
            {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "beta"},
            {"id": "c", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "gamma"},
        ])
        svc.merge_segments(["a", "b"])
        _assert_sorted(svc)
        ids = [s.id for s in svc.current.active_timeline.transcript.segments]
        # Merged segment keeps id "a" with merged text; "b" is removed
        assert ids == ["a", "c"]


class TestImportSrtSortInvariant:
    def test_unsorted_srt_input_gets_sorted(self, svc: ProjectService) -> None:
        # SRT content with segments deliberately out of order
        unsorted_srt = """1
00:00:30,000 --> 00:00:35,000
third

2
00:00:00,000 --> 00:00:05,000
first

3
00:00:10,000 --> 00:00:15,000
second
"""
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(unsorted_srt)
            srt_path = f.name

        # The service exposes update_transcript; SRT import in main.py
        # parses the SRT then calls update_transcript. We simulate that
        # path here by parsing manually and feeding dicts out-of-order.
        from core.subtitle_service import parse_srt
        result = parse_srt(srt_path)
        assert result["success"] is True
        segments = result["data"]
        svc.update_transcript(segments)

        _assert_sorted(svc)
        texts = [s.text for s in svc.current.active_timeline.transcript.segments]
        assert texts == ["first", "second", "third"]


class TestSortInvariantProperty:
    """Property-style: any sequence of mutations preserves the invariant."""

    def test_mixed_mutation_sequence(self, svc: ProjectService) -> None:
        svc.update_transcript([
            {"id": "a", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "a"},
            {"id": "b", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "b"},
        ])
        # Add a segment in the middle
        svc.add_segment(20.0, 22.0, "mid", "subtitle")
        _assert_sorted(svc)
        # Move "b" to before everything
        svc.update_segment("b", {"start": 5.0})
        _assert_sorted(svc)
        # Split "a"
        svc.split_segment("a", 12.0)
        _assert_sorted(svc)
        # Merge the two split halves back
        a_children = [
            s.id for s in svc.current.active_timeline.transcript.segments
            if s.id.startswith("a-")
        ]
        if len(a_children) >= 2:
            svc.merge_segments(a_children)
            _assert_sorted(svc)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
