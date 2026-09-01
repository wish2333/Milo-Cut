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


# ------------------------------------------------------------------
# v3.0.1 M2-1 step 4: linkage follow + reconcile (P3-3)
# ------------------------------------------------------------------

from core.models import Segment, SubtitleTrack, TrackBinding  # noqa: E402


def _seed_linkage(svc: ProjectService) -> None:
    """Main segments + one extension track with two bound segments."""
    _seed_two_segments(svc)
    tl = svc.active_timeline
    track = SubtitleTrack(
        id="trk1",
        role="extension",
        name="en",
        language="en",
        segments=[
            Segment(id="track_trk1_seg_a", start=0.2, end=4.8, text="en-1"),
            Segment(id="track_trk1_seg_b", start=10.2, end=14.8, text="en-2"),
        ],
    )
    bindings = [
        TrackBinding(id="bind_a", track_id="trk1", main_segment_id="s1",
                     extension_segment_id="track_trk1_seg_a",
                     start_offset=0.2, end_offset=-0.2),
        TrackBinding(id="bind_b", track_id="trk1", main_segment_id="s2",
                     extension_segment_id="track_trk1_seg_b",
                     start_offset=0.2, end_offset=-0.2),
    ]
    svc._update_active_timeline(
        transcript=tl.transcript.model_copy(update={"tracks": [track], "bindings": bindings})
    )


def _track_segs(svc: ProjectService) -> dict:
    track = svc.active_timeline.transcript.tracks[0]
    return {s.id: s for s in track.segments}


def _bindings(svc: ProjectService) -> dict:
    return {b.id: b for b in svc.active_timeline.transcript.bindings}


class TestLinkageFollow:
    def test_move_follows_and_offsets_stable(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s1", {"start": 2.0, "end": 7.0})
        assert res["success"], res
        patch = res["data"]
        # whole-span shift: ext a moved by the same +2 delta
        a = _track_segs(svc)["track_trk1_seg_a"]
        assert (a.start, a.end) == (2.2, 6.8)
        # offsets unchanged (pure move) -- rebuilt values identical
        bnd = _bindings(svc)["bind_a"]
        assert (bnd.start_offset, bnd.end_offset) == (0.2, -0.2)
        # meta carries zero-cost linkage
        assert patch["meta"]["linkage"] == {"squeezed": 0, "removed": 0, "unbound": 0}

    def test_trim_follows_single_edge(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s1", {"start": 1.0})
        assert res["success"], res
        a = _track_segs(svc)["track_trk1_seg_a"]
        assert a.start == 1.2 and a.end == 4.8

    def test_follow_wins_inside_covered_range(self, svc):
        # P3-3 errata: a BOUND segment's synced geometry is its expected
        # state -- being inside the main range is NOT a conflict. b follows
        # s2 (+1) to [11.2, 14.8] and stays whole; offsets unchanged.
        _seed_linkage(svc)
        res = svc.update_segment("s2", {"start": 11.0, "end": 15.0})
        assert res["success"], res
        b = _track_segs(svc)["track_trk1_seg_b"]
        assert (b.start, b.end) == (11.2, 14.8)
        bnd = _bindings(svc)["bind_b"]
        assert (bnd.start_offset, bnd.end_offset) == (0.2, -0.2)
        assert res["data"]["meta"]["linkage"]["squeezed"] == 0

    def test_unbound_segment_squeezed_by_covered_range(self, svc):
        _seed_linkage(svc)
        # Unbound segment c straddles the new main range [11, 15]: keep the
        # longest uncovered side [15, 16] -> squeezed (passive rule).
        tl = svc.active_timeline
        track = tl.transcript.tracks[0].model_copy(
            update={"segments": [*tl.transcript.tracks[0].segments,
                                 Segment(id="track_trk1_seg_c", start=12.0, end=16.0, text="free")]}
        )
        svc._update_active_timeline(transcript=tl.transcript.model_copy(update={"tracks": [track]}))
        res = svc.update_segment("s2", {"start": 11.0, "end": 15.0})
        assert res["success"], res
        segs = _track_segs(svc)
        assert (segs["track_trk1_seg_c"].start, segs["track_trk1_seg_c"].end) == (15.0, 16.0)
        assert res["data"]["meta"]["linkage"]["squeezed"] == 1

    def test_unbound_segment_deleted_when_fully_covered(self, svc):
        _seed_linkage(svc)
        tl = svc.active_timeline
        track = tl.transcript.tracks[0].model_copy(
            update={"segments": [*tl.transcript.tracks[0].segments,
                                 Segment(id="track_trk1_seg_c", start=12.0, end=13.0, text="free")]}
        )
        svc._update_active_timeline(transcript=tl.transcript.model_copy(update={"tracks": [track]}))
        res = svc.update_segment("s2", {"start": 11.0, "end": 15.0})
        assert res["success"], res
        assert "track_trk1_seg_c" not in _track_segs(svc)
        assert res["data"]["meta"]["linkage"]["removed"] == 1

    def test_bound_segment_deleted_when_follow_overlaps_sibling(self, svc):
        # Follow lands on an occupied lane slot -> delete + unbind (MVP
        # ruling: no fine squeezing). s3's ext d follows onto b's slot.
        # NOTE: update_transcript resets tracks/bindings, so the three main
        # segments are seeded FIRST and the track is attached afterwards.
        svc.update_transcript([
            {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
            {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
            {"id": "s3", "type": "subtitle", "start": 30.0, "end": 35.0, "text": "third"},
        ])
        tl = svc.active_timeline
        track = SubtitleTrack(id="trk1", role="extension", name="en", language="en",
            segments=[
                Segment(id="track_trk1_seg_a", start=0.2, end=4.8, text="en-1"),
                Segment(id="track_trk1_seg_b", start=10.2, end=14.8, text="en-2"),
                Segment(id="track_trk1_seg_b2", start=21.0, end=22.0, text="en-3"),
            ])
        bindings = [
            TrackBinding(id="bind_a", track_id="trk1", main_segment_id="s1",
                         extension_segment_id="track_trk1_seg_a", start_offset=0.2, end_offset=-0.2),
            TrackBinding(id="bind_b", track_id="trk1", main_segment_id="s2",
                         extension_segment_id="track_trk1_seg_b", start_offset=0.2, end_offset=-0.2),
            TrackBinding(id="bind_d", track_id="trk1", main_segment_id="s3",
                         extension_segment_id="track_trk1_seg_b2", start_offset=-9.0, end_offset=-13.0),
        ]
        svc._update_active_timeline(transcript=tl.transcript.model_copy(
            update={"tracks": [track], "bindings": bindings}
        ))
        # d is bound to s3 (offset -9 puts it at [21, 22]). Moving s2 to
        # [20, 25] (legal on the main track) makes b follow onto [20.2,
        # 24.8], overlapping d [21, 22]; d is bound to s3 so it never
        # passively moves -> b (the follower) is deleted + unbound.
        res = svc.update_segment("s2", {"start": 20.0, "end": 25.0})
        assert res["success"], res
        segs = _track_segs(svc)
        assert "track_trk1_seg_b" not in segs
        assert "bind_b" not in _bindings(svc)
        # the other-main bound segment stays put in its slot
        assert (segs["track_trk1_seg_b2"].start, segs["track_trk1_seg_b2"].end) == (21.0, 22.0)
        assert res["data"]["meta"]["linkage"]["removed"] == 1
        assert res["data"]["meta"]["linkage"]["unbound"] == 1

    def test_main_track_never_rewritten_by_reconcile(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s2", {"start": 11.0, "end": 15.0})
        assert res["success"], res
        segs = {s.id: s for s in svc.active_timeline.transcript.segments}
        # red line M0-3.1: s1 untouched; s2 exactly the requested geometry
        assert (segs["s1"].start, segs["s1"].end) == (0.0, 5.0)
        assert (segs["s2"].start, segs["s2"].end) == (11.0, 15.0)

    def test_no_bindings_patch_has_no_track_layers(self, svc):
        _seed_two_segments(svc)
        res = svc.update_segment("s1", {"start": 1.0})
        assert res["success"], res
        patch = res["data"]
        assert patch["tracks"] is None
        assert patch["bindings"] is None
        assert patch.get("meta") is None
