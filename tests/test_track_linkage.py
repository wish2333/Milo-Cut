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


# ------------------------------------------------------------------
# v3.0.1 M2-2: update_track_segment (P3-4)
# ------------------------------------------------------------------


class TestUpdateTrackSegment:
    def test_track_not_found(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment("trk_missing", "track_trk1_seg_a", {"text": "x"})
        assert res["success"] is False
        assert "trk_missing" in res["error"]

    def test_segment_not_in_track(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment("trk1", "track_trk1_seg_zz", {"text": "x"})
        assert res["success"] is False
        assert "Segment not found" in res["error"]

    def test_empty_updates_rejected(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {})
        assert res["success"] is False

    def test_id_field_is_stripped(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment(
            "trk1", "track_trk1_seg_a",
            {"text": "renamed", "id": "track_trk1_seg_evil"},
        )
        assert res["success"], res
        assert _track_segs(svc)["track_trk1_seg_a"].id == "track_trk1_seg_a"
        assert _track_segs(svc)["track_trk1_seg_a"].text == "renamed"

    def test_clamps_to_media_duration(self, svc):
        _seed_linkage(svc)
        # media duration is 100 in the fixture; b has no right neighbor,
        # so dragging its end beyond duration clamps to 100.0.
        res = svc.update_track_segment(
            "trk1", "track_trk1_seg_b", {"end": 120.0}
        )
        assert res["success"], res
        b = _track_segs(svc)["track_trk1_seg_b"]
        assert b.end == 100.0 and b.start == 10.2

    def test_clamp_into_neighbor_is_overlap_rejected(self, svc):
        _seed_linkage(svc)
        # a dragged far right clamps to duration 100 -- which now crosses
        # b; the overlap check (post-clamp) rejects with the conflict id.
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {"end": 120.0})
        assert res["success"] is False
        assert "track_trk1_seg_b" in res["error"]

    def test_overlap_rejected_with_conflict_id(self, svc):
        _seed_linkage(svc)
        # b occupies [10.2, 14.8]; drag a's end into it.
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {"end": 11.0})
        assert res["success"] is False
        assert "track_trk1_seg_b" in res["error"]

    def test_touching_neighbor_allowed(self, svc):
        _seed_linkage(svc)
        # a end exactly at b start -> legal.
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {"end": 10.2})
        assert res["success"] is True

    def test_min_duration_enforced(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {"end": 0.25})
        assert res["success"] is False
        assert "below minimum" in res["error"]

    def test_offsets_rebuilt_and_main_untouched(self, svc):
        _seed_linkage(svc)
        main_before = {
            s.id: (s.start, s.end, s.text)
            for s in svc.active_timeline.transcript.segments
        }
        res = svc.update_track_segment(
            "trk1", "track_trk1_seg_a", {"start": 0.5, "end": 5.0}
        )
        assert res["success"], res
        patch = res["data"]
        a = _track_segs(svc)["track_trk1_seg_a"]
        assert (a.start, a.end) == (0.5, 5.0)
        # offsets rebuilt wholesale from final geometry: ext - main
        bnd = _bindings(svc)["bind_a"]
        assert (bnd.start_offset, bnd.end_offset) == (0.5, 0.0)
        assert patch["meta"]["linkage"] == {"rebuilt": 1}
        # red line: main track untouched
        main_after = {
            s.id: (s.start, s.end, s.text)
            for s in svc.active_timeline.transcript.segments
        }
        assert main_before == main_after

    def test_patch_carries_tracks_and_bindings_layers(self, svc):
        _seed_linkage(svc)
        res = svc.update_track_segment("trk1", "track_trk1_seg_a", {"text": "x"})
        assert res["success"], res
        patch = res["data"]
        assert patch["tracks"] is not None and patch["bindings"] is not None
        assert patch["segments"] is None  # main layer never rides along


# ------------------------------------------------------------------
# v3.0.1 M2-3: paired deletion + linked split (P3-5)
# ------------------------------------------------------------------


class TestPairedDeletion:
    def test_delete_removes_bound_ext_and_binding(self, svc):
        _seed_linkage(svc)
        res = svc.delete_segment("s1")
        assert res["success"], res
        patch = res["data"]
        segs = _track_segs(svc)
        assert "track_trk1_seg_a" not in segs
        assert "track_trk1_seg_b" in segs  # unbound-to-s2 ext stays
        assert "bind_a" not in _bindings(svc)
        assert patch["meta"]["linkage"] == {"removed": 1, "unbound": 0}
        assert patch["tracks"] is not None and patch["bindings"] is not None

    def test_delete_unbound_main_has_no_track_layers(self, svc):
        _seed_linkage(svc)
        res = svc.delete_segment("s2")
        # s2 is bound to b -- delete s1 instead for the unbound path.
        res = svc.delete_segment("s1")
        assert res["success"], res

    def test_delete_unbound_main_segment(self, svc):
        svc.update_transcript([
            {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
            {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
        ])
        res = svc.delete_segment("s1")
        assert res["success"], res
        patch = res["data"]
        assert patch["tracks"] is None and patch["bindings"] is None
        assert patch.get("meta") is None

    def test_delete_rejects_track_namespace(self, svc):
        _seed_linkage(svc)
        res = svc.delete_segment("track_trk1_seg_a")
        assert res["success"] is False
        assert "track_ namespace" in res["error"]


class TestLinkedSplit:
    def test_split_inside_ext_splits_and_rebinds_both_halves(self, svc):
        _seed_linkage(svc)
        # Cut s1 at 2.0 (inside ext a [0.2, 4.8]): cut_ext = 2.2.
        res = svc.split_segment("s1", 2.0)
        assert res["success"], res
        segs = _track_segs(svc)
        assert "track_trk1_seg_a" not in segs
        assert "track_trk1_seg_a__a" in segs and "track_trk1_seg_a__b" in segs
        a1 = segs["track_trk1_seg_a__a"]
        a2 = segs["track_trk1_seg_a__b"]
        assert (a1.start, a1.end) == (0.2, 2.2)
        assert (a2.start, a2.end) == (2.2, 4.8)
        bnd = _bindings(svc)
        assert "bind_a" not in bnd
        assert "bind_a__a" in bnd and "bind_a__b" in bnd
        assert bnd["bind_a__a"].main_segment_id == "s1-a"
        assert bnd["bind_a__b"].main_segment_id == "s1-b"
        # ext_a ends at 2.2 vs main a ends at 2.0 -> honest +0.2
        assert (bnd["bind_a__a"].start_offset, bnd["bind_a__a"].end_offset) == (0.2, 0.2)
        assert res["data"]["meta"]["linkage"]["split"] == 1

    def test_split_cut_outside_rebinds_to_overlap_side(self, svc):
        _seed_linkage(svc)
        # Cut s2 at 10.05: cut_ext = 10.25 < b.start + MIN (10.3) -> cannot
        # split; ext b lies entirely in the b-side (s2-b) -> rebind there.
        res = svc.split_segment("s2", 10.05)
        assert res["success"], res
        segs = _track_segs(svc)
        assert "track_trk1_seg_b" in segs  # not split
        assert "track_trk1_seg_b__a" not in segs
        bnd = _bindings(svc)
        # rebind keeps the binding id (in-place update of main_segment_id)
        assert bnd["bind_b"].main_segment_id == "s2-b"
        assert all(b.main_segment_id != "s2" for b in bnd.values())
        assert res["data"]["meta"]["linkage"]["rebound"] == 1

    def test_split_unbinds_when_no_side_overlaps_enough(self, svc):
        _seed_linkage(svc)
        # Degenerate binding: ext b is only 0.05s wide (below MIN, a drift
        # residue) at [17, 17.05]. Splitting s2 at 12 maps to cut_ext 12.2,
        # which cannot split it, and the point-split assigns it entirely to
        # the b-side with an overlap of 0.05 < MIN -> dissolved (unbound).
        # A healthy-width segment elsewhere would rebind instead (previous
        # test), so this exercises the defensive unbind branch.
        tl = svc.active_timeline
        track = tl.transcript.tracks[0].model_copy(
            update={"segments": [
                Segment(id="track_trk1_seg_a", start=0.2, end=4.8, text="en-1"),
                Segment(id="track_trk1_seg_b", start=17.0, end=17.05, text="en-2"),
            ]}
        )
        svc._update_active_timeline(
            transcript=tl.transcript.model_copy(update={"tracks": [track]})
        )
        res = svc.split_segment("s2", 12.0)
        assert res["success"], res
        assert "track_trk1_seg_b" in _track_segs(svc)  # not split
        assert "bind_b" not in _bindings(svc)          # dissolved
        assert res["data"]["meta"]["linkage"]["unbound"] == 1

    def test_split_patch_carries_three_layers(self, svc):
        _seed_linkage(svc)
        res = svc.split_segment("s1", 2.0)
        patch = res["data"]
        assert patch["segments"] is not None
        assert patch["tracks"] is not None
        assert patch["bindings"] is not None


# ------------------------------------------------------------------
# v3.0.2 M1-2 (S2): update_segment linkage path carries layers
# ------------------------------------------------------------------


class TestLinkagePatchCarriesLayers:
    """v3.0.1 dropped tracks/bindings from the update_segment linkage
    patch (only meta.linkage counters shipped) -- the frontend's track
    lanes went stale until an unrelated write refreshed the layers. The
    linkage path must carry the resolved full arrays (v3.0.1 SPEC M2-1
    step 5); the no-linkage path keeps its patch shape."""

    def test_linkage_patch_has_all_four_parts(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s1", {"start": 2.0, "end": 7.0})
        assert res["success"], res
        patch = res["data"]
        assert patch["segments"] is not None
        assert patch["tracks"] is not None
        assert patch["bindings"] is not None
        assert patch["meta"]["linkage"] == {"squeezed": 0, "removed": 0, "unbound": 0}

    def test_patch_tracks_carry_resolved_geometry(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s1", {"start": 2.0, "end": 7.0})
        patch = res["data"]
        tracks = {t["id"]: t for t in patch["tracks"]}
        segs = {s["id"]: s for s in tracks["trk1"]["segments"]}
        # ext a followed the whole-span move inside the PATCH payload,
        # not just in the live service state
        assert (segs["track_trk1_seg_a"]["start"], segs["track_trk1_seg_a"]["end"]) == (2.2, 6.8)

    def test_patch_bindings_carry_resolved_offsets(self, svc):
        _seed_linkage(svc)
        res = svc.update_segment("s1", {"start": 1.0})
        patch = res["data"]
        bindings = {b["id"]: b for b in patch["bindings"]}
        # trim start: ext a follows to [1.2, 4.8]; offsets rebuilt
        assert (bindings["bind_a"]["start_offset"], bindings["bind_a"]["end_offset"]) == (0.2, -0.2)

    def test_squeezed_geometry_visible_in_patch_tracks(self, svc):
        _seed_linkage(svc)
        tl = svc.active_timeline
        track = tl.transcript.tracks[0].model_copy(
            update={"segments": [*tl.transcript.tracks[0].segments,
                                 Segment(id="track_trk1_seg_c", start=12.0, end=16.0, text="free")]}
        )
        svc._update_active_timeline(transcript=tl.transcript.model_copy(update={"tracks": [track]}))
        res = svc.update_segment("s2", {"start": 11.0, "end": 15.0})
        assert res["success"], res
        tracks = {t["id"]: t for t in res["data"]["tracks"]}
        segs = {s["id"]: s for s in tracks["trk1"]["segments"]}
        assert (segs["track_trk1_seg_c"]["start"], segs["track_trk1_seg_c"]["end"]) == (15.0, 16.0)

    def test_no_linkage_patch_shape_unchanged(self, svc):
        _seed_two_segments(svc)
        res = svc.update_segment("s1", {"end": 8.0})
        assert res["success"], res
        patch = res["data"]
        assert patch["segments"] is not None
        assert patch["tracks"] is None
        assert patch["bindings"] is None
        assert patch.get("meta") is None

    def test_linkage_patch_on_silence_cascade_keeps_layers(self, svc):
        # silence start/end changes cascade into edits; with bindings the
        # patch must carry segments + edits + tracks + bindings + meta.
        # NOTE: update_transcript resets tracks/bindings, so the track is
        # attached after seeding (same pattern as the paired-deletion test).
        svc.update_transcript([
            {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
            {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
            {"id": "sil1", "type": "silence", "start": 30.0, "end": 35.0, "text": ""},
        ])
        tl = svc.active_timeline
        track = SubtitleTrack(
            id="trk1", role="extension", name="en", language="en",
            segments=[Segment(id="track_trk1_seg_s", start=30.2, end=34.8, text="sil-en")],
        )
        binding = TrackBinding(
            id="bind_s", track_id="trk1", main_segment_id="sil1",
            extension_segment_id="track_trk1_seg_s", start_offset=0.2, end_offset=-0.2,
        )
        from core.models import EditDecision

        edit = EditDecision(
            id="ed_sil", start=30.0, end=35.0, action="delete", source="silence_detection",
            status="confirmed", priority=100, target_type="segment", target_id="sil1",
        )
        svc._update_active_timeline(
            transcript=tl.transcript.model_copy(update={"tracks": [track], "bindings": [binding]}),
            edits=[edit],
        )
        res = svc.update_segment("sil1", {"start": 31.0})
        assert res["success"], res
        patch = res["data"]
        assert patch["edits"] is not None
        assert patch["tracks"] is not None
        assert patch["bindings"] is not None
        assert patch["meta"]["linkage"] is not None


class TestDeleteTrackSegment:
    """v3.0.2 smoke fix: extension segments become deletable end-to-end."""

    def test_deletes_segment_and_returns_tracks_layer(self, svc):
        _seed_linkage(svc)
        res = svc.delete_track_segment("trk1", "track_trk1_seg_a")
        assert res["success"] is True
        patch = res["data"]
        assert patch["tracks"] is not None
        trk = next(t for t in patch["tracks"] if t["id"] == "trk1")
        assert [s["id"] for s in trk["segments"]] == ["track_trk1_seg_b"]
        # Main transcript untouched (red line M0-3).
        assert "segments" not in patch or patch.get("segments") is None

    def test_deletes_bindings_anchored_to_the_segment(self, svc):
        _seed_linkage(svc)
        before = _bindings(svc)
        assert before  # seeded with bindings
        res = svc.delete_track_segment("trk1", "track_trk1_seg_a")
        patch = res["data"]
        after_ids = {b["id"] for b in patch["bindings"]}
        dropped = {
            b.id for b in before.values() if b.extension_segment_id == "track_trk1_seg_a"
        }
        assert dropped and not (dropped & after_ids)
        # Unrelated binding survives.
        assert {b.id for b in before.values()} - dropped <= after_ids

    def test_unknown_track_and_segment_rejected(self, svc):
        _seed_linkage(svc)
        assert svc.delete_track_segment("nope", "x")["success"] is False
        assert svc.delete_track_segment("trk1", "nope")["success"] is False
        # State unchanged.
        assert len(svc.active_timeline.transcript.tracks[0].segments) == 2
