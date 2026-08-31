"""update_segment overlap rejection + track-namespace guard (v3.0.1 M2-1).

P1-3 scope: rejection paths only. The linkage follow/reconcile steps
(SPEC M2-1 step 4) land in Phase 3 and extend this file.
"""

from __future__ import annotations

import pytest

from core.project_service import ProjectService


def _create_service(tmp_path, monkeypatch) -> ProjectService:
    monkeypatch.setattr("core.project_service.get_projects_dir", lambda: tmp_path)
    svc = ProjectService()
    media = tmp_path / "v.mp4"
    media.write_bytes(b"stub")
    svc.create_project("overlap-test", str(media), {"duration": 100.0})
    return svc


def _seed_two_segments(svc: ProjectService) -> None:
    svc.update_transcript([
        {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
        {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
    ])


@pytest.fixture
def svc(tmp_path, monkeypatch) -> ProjectService:
    service = _create_service(tmp_path, monkeypatch)
    _seed_two_segments(service)
    return service


class TestTrackNamespaceGuard:
    def test_update_segment_rejects_track_namespace(self, svc):
        res = svc.update_segment("track_trk1_seg_1.000", {"text": "x"})
        assert res["success"] is False
        assert "update_track_segment" in res["error"]
        assert "track_" in res["error"]

    def test_rejection_happens_before_validation(self, svc):
        # Namespace guard fires even for an unknown segment / empty updates.
        res = svc.update_segment("track_missing", {})
        assert res["success"] is False
        assert "update_track_segment" in res["error"]


class TestOverlapRejection:
    def test_rejects_start_overlapping_previous(self, svc):
        # s2 start dragged into s1's range.
        res = svc.update_segment("s2", {"start": 3.0})
        assert res["success"] is False
        assert "s2" in res["error"] and "s1" in res["error"]
        assert "overlaps" in res["error"]
        # error carries both ranges
        assert "[3.000, 15.000]" in res["error"]
        assert "[0.000, 5.000]" in res["error"]

    def test_rejects_end_overlapping_next(self, svc):
        # s1 end dragged into s2's range.
        res = svc.update_segment("s1", {"end": 12.0})
        assert res["success"] is False
        assert "s1" in res["error"] and "s2" in res["error"]

    def test_rejects_when_spanning_both(self, svc):
        # A middle segment stretched across both neighbors reports the
        # first conflict encountered (deterministic: transcript order).
        svc.update_transcript([
            {"id": "m1", "type": "subtitle", "start": 20.0, "end": 22.0, "text": "mid"},
            {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
            {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
        ])
        res = svc.update_segment("m1", {"start": 2.0, "end": 25.0})
        assert res["success"] is False
        # transcript order: m1 is first in the seeded list; the first
        # non-self segment with an overlap is s1.
        assert "s1" in res["error"]

    def test_allows_touching_previous_end(self, svc):
        # s2 start exactly at s1 end -> legal.
        res = svc.update_segment("s2", {"start": 5.0})
        assert res["success"] is True

    def test_allows_touching_next_start(self, svc):
        # s1 end exactly at s2 start -> legal.
        res = svc.update_segment("s1", {"end": 10.0})
        assert res["success"] is True

    def test_allows_sub_epsilon_touch(self, svc):
        # 1e-9 gap is "touching" under the 1e-6 epsilon.
        res = svc.update_segment("s2", {"start": 5.0 + 1e-9})
        assert res["success"] is True

    def test_text_only_update_skips_overlap_check(self, svc):
        # Text edits on a segment whose geometry already touches a
        # neighbor must not be blocked.
        res = svc.update_segment("s1", {"text": "renamed"})
        assert res["success"] is True

    def test_normal_time_update_passes(self, svc):
        res = svc.update_segment("s1", {"end": 8.0})
        assert res["success"] is True
        segs = {s.id: s for s in svc.current.active_timeline.transcript.segments}
        assert segs["s1"].end == 8.0

    def test_unknown_segment_error_unchanged(self, svc):
        res = svc.update_segment("nope", {"start": 1.0})
        assert res["success"] is False
        assert "Segment not found" in res["error"]

    def test_silence_segment_same_rules(self, svc):
        svc.update_transcript([
            {"id": "sil1", "type": "silence", "start": 20.0, "end": 25.0, "text": ""},
            {"id": "sil2", "type": "silence", "start": 30.0, "end": 35.0, "text": ""},
        ])
        res = svc.update_segment("sil1", {"end": 32.0})
        assert res["success"] is False
        assert "sil2" in res["error"]
