"""v3.0.0 P4-2 M11-2: multi-track subtitle structure contract tests.

Locks:
- Construction guard: update_transcript / add_silence_results / add_segment
  preserve transcript.tracks / bindings / engine / language (model_copy).
- ProjectPatch tracks/bindings layers round-trip.
- _enforce_segment_sort_invariant never touches extension tracks.
- Old projects without the tracks/bindings fields open unchanged.
- import_srt_as_track: id namespace isolation + 300 ms tolerance binding.
- Track export at original timestamps (via export_track_subtitle
  map_deletions=False since v3.0.2 removed the export_track_srt wrapper).
"""

from __future__ import annotations

import pytest

from core.models import (
    Project,
    ProjectPatch,
    Segment,
    SegmentType,
    SubtitleTrack,
    TrackBinding,
)
from core.project_service import ProjectService


@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    return service


def _main_segments() -> list[Segment]:
    return [
        Segment(id="seg_1.000", type=SegmentType.SUBTITLE, start=1.0, end=2.0, text="主轨一"),
        Segment(id="seg_3.000", type=SegmentType.SUBTITLE, start=3.0, end=4.0, text="主轨二"),
    ]


def _track(track_id: str = "trk_ab12cd34", segs: list[Segment] | None = None) -> SubtitleTrack:
    if segs is None:
        segs = [
            Segment(
                id=f"track_{track_id}_seg_{start:.3f}",
                type=SegmentType.SUBTITLE,
                start=start,
                end=end,
                text=text,
            )
            for start, end, text in [(1.0, 2.0, "hello"), (3.0, 4.0, "world")]
        ]
    return SubtitleTrack(
        id=track_id, role="extension", name="en", language="en", segments=segs
    )


def _install_tracks(svc, track: SubtitleTrack, bindings: list[TrackBinding]) -> None:
    tl = svc.active_timeline
    transcript = tl.transcript.model_copy(
        update={"tracks": [track], "bindings": bindings}
    )
    svc._current = svc._current.model_copy(
        update={"timelines": [tl.model_copy(update={"transcript": transcript})]}
    )


# ---------------------------------------------------------------------------
# Construction guard
# ---------------------------------------------------------------------------


class TestConstructionGuard:
    def test_update_transcript_preserves_tracks(self, svc):
        _install_tracks(svc, _track(), [])
        res = svc.update_transcript(
            [{"id": "seg_new", "type": "subtitle", "start": 0.0, "end": 1.0, "text": "new"}]
        )
        assert res["success"]
        tr = svc.active_timeline.transcript
        assert [t.id for t in tr.tracks] == ["trk_ab12cd34"]
        assert tr.engine == "srt" and tr.language == "zh-CN"

    def test_add_silence_results_preserves_tracks(self, svc):
        _install_tracks(svc, _track(), [])
        res = svc.add_silence_results([{"start": 5.0, "end": 6.0}])
        assert res["success"]
        tr = svc.active_timeline.transcript
        assert [t.id for t in tr.tracks] == ["trk_ab12cd34"]
        assert any(s.type == SegmentType.SILENCE for s in tr.segments)

    def test_add_segment_preserves_tracks(self, svc):
        _install_tracks(svc, _track(), [])
        res = svc.add_segment(0.2, 0.8, "added")
        assert res["success"]
        tr = svc.active_timeline.transcript
        assert [t.id for t in tr.tracks] == ["trk_ab12cd34"]
        assert any(s.text == "added" for s in tr.segments)

    def test_update_transcript_meta_preserves_tracks(self, svc):
        _install_tracks(svc, _track(), [])
        svc.update_transcript_meta(engine="whisper", language="en-US")
        tr = svc.active_timeline.transcript
        assert (tr.engine, tr.language) == ("whisper", "en-US")
        assert [t.id for t in tr.tracks] == ["trk_ab12cd34"]


# ---------------------------------------------------------------------------
# ProjectPatch round-trip
# ---------------------------------------------------------------------------


class TestPatchRoundTrip:
    def test_tracks_bindings_layers_round_trip(self):
        binding = TrackBinding(
            id="bind_1",
            track_id="trk_ab12cd34",
            main_segment_id="seg_1.000",
            extension_segment_id="track_trk_ab12cd34_seg_1.000",
            start_offset=0.05,
            end_offset=-0.1,
        )
        patch = ProjectPatch(revision=1, tracks=[_track()], bindings=[binding])
        data = patch.model_dump(mode="json")
        restored = ProjectPatch.model_validate(data)
        assert restored.tracks == [_track()]
        assert restored.bindings == [binding]

    def test_patch_without_track_layers_is_none(self):
        patch = ProjectPatch(revision=1, segments=[_main_segments()[0]])
        assert patch.tracks is None and patch.bindings is None


# ---------------------------------------------------------------------------
# Sort invariant: main track only
# ---------------------------------------------------------------------------


class TestSortInvariantScope:
    def test_invariant_does_not_touch_tracks(self, svc):
        unsorted_track = _track(
            segs=[
                Segment(id="track_x_seg_3.000", type=SegmentType.SUBTITLE, start=3.0, end=4.0, text="b"),
                Segment(id="track_x_seg_1.000", type=SegmentType.SUBTITLE, start=1.0, end=2.0, text="a"),
            ]
        )
        _install_tracks(svc, unsorted_track, [])
        svc._enforce_segment_sort_invariant()
        main = svc.active_timeline.transcript.segments
        assert [s.start for s in main] == sorted(s.start for s in main)
        # Track order untouched (still "unsorted").
        track_segs = svc.active_timeline.transcript.tracks[0].segments
        assert [s.text for s in track_segs] == ["b", "a"]


# ---------------------------------------------------------------------------
# Old-project compatibility
# ---------------------------------------------------------------------------


class TestOldProjectCompat:
    def test_project_without_tracks_fields_opens(self, svc):
        data = svc._current.model_dump(mode="json")
        for tl in data["timelines"]:
            tl["transcript"].pop("tracks", None)
            tl["transcript"].pop("bindings", None)
        project = Project.model_validate(data)
        assert project.timelines[0].transcript.tracks == []
        assert project.timelines[0].transcript.bindings == []

    def test_save_open_round_trip_keeps_tracks(self, svc, monkeypatch, tmp_path):
        # Real media file so open_project passes the media existence check.
        media = tmp_path / "media.mp4"
        media.write_bytes(b"\x00" * 16)
        svc._current = svc._current.model_copy(
            update={"media": svc._current.media.model_copy(update={"path": str(media)})}
            if svc._current.media
            else svc._current
        )
        _install_tracks(svc, _track(), [])
        res = svc.save_project()
        assert res["success"]
        project_file = tmp_path / "projects" / "t" / "project.json"
        opened = svc.open_project(str(project_file))
        assert opened["success"]
        tr = svc.active_timeline.transcript
        assert [t.id for t in tr.tracks] == ["trk_ab12cd34"]
        assert tr.tracks[0].segments[0].text == "hello"


# ---------------------------------------------------------------------------
# import_srt_as_track
# ---------------------------------------------------------------------------


class TestImportSrtAsTrack:
    def _write_srt(self, path, cues):
        body = ""
        for idx, (start, end, text) in enumerate(cues, 1):
            body += f"{idx}\n00:00:{start:06.3f}".replace(".", ",") + " --> " + f"00:00:{end:06.3f}".replace(".", ",") + f"\n{text}\n\n"
        path.write_text(body, encoding="utf-8")

    def test_namespace_binding_and_offsets(self, svc, tmp_path):
        tl = svc.active_timeline
        svc._current = svc._current.model_copy(
            update={
                "timelines": [
                    tl.model_copy(
                        update={
                            "transcript": tl.transcript.model_copy(
                                update={"segments": _main_segments()}
                            )
                        }
                    )
                ]
            }
        )
        srt = tmp_path / "en.srt"
        # 1.05 within 300ms of main 1.0; 3.2 within 300ms of main 3.0; 8.9 no match.
        self._write_srt(srt, [(1.05, 2.0, "hello"), (3.2, 4.0, "world"), (8.9, 9.5, "orphan")])

        res = svc.import_srt_as_track(str(srt), language="en")
        assert res["success"]
        data = res["data"]
        assert data["revision"] > 0  # patch envelope, not legacy dump
        (track,) = data["tracks"]
        assert track["id"].startswith("trk_")
        assert track["language"] == "en"
        assert track["name"] == "en"
        ids = [s["id"] for s in track["segments"]]
        # Namespace isolation: track ids never look like main-track ids.
        assert all(i.startswith(f"track_{track['id']}_seg_") for i in ids)
        assert not any(i.startswith("seg") for i in ids)
        assert len(track["segments"]) == 3

        # 300 ms tolerance: two bound, orphan unmatched.
        bindings = data["bindings"]
        assert len(bindings) == 2
        assert bindings[0]["main_segment_id"] == "seg_1.000"
        assert bindings[0]["extension_segment_id"] == ids[0]
        assert bindings[0]["start_offset"] == pytest.approx(0.05)
        assert bindings[1]["main_segment_id"] == "seg_3.000"
        assert bindings[1]["start_offset"] == pytest.approx(0.2)

        # Main track untouched.
        assert [s.id for s in svc.active_timeline.transcript.segments] == [
            "seg_1.000", "seg_3.000",
        ]

    def test_empty_srt_rejected(self, svc, tmp_path):
        srt = tmp_path / "empty.srt"
        srt.write_text("\n\n", encoding="utf-8")
        res = svc.import_srt_as_track(str(srt))
        assert not res["success"]

    def test_second_import_appends_track(self, svc, tmp_path):
        srt = tmp_path / "a.srt"
        self._write_srt(srt, [(1.0, 2.0, "hello")])
        assert svc.import_srt_as_track(str(srt))["success"]
        assert svc.import_srt_as_track(str(srt))["success"]
        assert len(svc.active_timeline.transcript.tracks) == 2


# ---------------------------------------------------------------------------
# track export at original timestamps (v3.0.2 M1-3: the deprecated
# export_track_srt wrapper was removed; the same original-timestamp
# semantics go through export_track_subtitle(map_deletions=False))
# ---------------------------------------------------------------------------


class TestExportTrackOriginalTimestamps:
    def test_original_timestamps_no_deletion_mapping(self, tmp_path):
        from core.export_service import export_track_subtitle

        track = _track().model_dump(mode="json")
        out = tmp_path / "track.srt"
        res = export_track_subtitle(track, [], str(out), map_deletions=False)
        assert res["success"] and res["data"]["segment_count"] == 2
        content = out.read_text(encoding="utf-8")
        # Original times, NOT remapped through keep ranges.
        assert "00:00:01,000 --> 00:00:02,000" in content
        assert "00:00:03,000 --> 00:00:04,000" in content
        assert "hello" in content

    def test_silence_rows_filtered(self, tmp_path):
        from core.export_service import export_track_subtitle

        track = _track()
        segs = list(track.segments) + [
            Segment(id="track_x_seg_5.000", type=SegmentType.SILENCE, start=5.0, end=6.0)
        ]
        dumped = track.model_copy(update={"segments": segs}).model_dump(mode="json")
        out = tmp_path / "track.srt"
        res = export_track_subtitle(dumped, [], str(out), map_deletions=False)
        assert res["data"]["segment_count"] == 2
