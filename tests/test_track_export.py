"""v3.0.1 M6-1 tests: extension-track export enters the deletion-mapping
pipeline (same mapping functions as the main track -- R9.1), plus the
bilingual merged export (P4-2).
"""


from core.export_service import (
    export_bilingual_subtitle,
    export_track_srt,
    export_track_subtitle,
)


def seg(id: str, start: float, end: float, text: str) -> dict:
    return {"id": id, "type": "subtitle", "start": start, "end": end, "text": text}


def edit(id: str, start: float, end: float) -> dict:
    return {
        "id": id,
        "target_id": "seg-x",
        "target_type": "segment",
        "action": "delete",
        "status": "confirmed",
        "priority": 100,
        "source": "manual",
        "start": start,
        "end": end,
    }


TRACK = {
    "id": "trk1",
    "role": "extension",
    "name": "en",
    "language": "en",
    "segments": [
        seg("track_trk1_seg_a", 1.0, 3.0, "hello"),
        seg("track_trk1_seg_b", 5.0, 8.0, "world"),  # straddles deletion 6-7
        seg("track_trk1_seg_c", 9.0, 11.0, "gone"),  # fully inside deletion 9-11.5
    ],
}
EDITS = [edit("ed-1", 6.0, 7.0), edit("ed-2", 9.0, 11.5)]


class TestExportTrackSubtitle:
    def test_map_deletions_drops_covered_and_maps_straddler(self, tmp_path):
        out = tmp_path / "track.srt"
        res = export_track_subtitle(TRACK, EDITS, str(out), media_duration=12.0)
        assert res["success"], res
        text = out.read_text(encoding="utf-8")
        # "gone" is fully covered -> dropped (logged, not written)
        assert "gone" not in text
        # "hello" untouched (deletions start at 6.0)
        assert "1\n00:00:01,000 --> 00:00:03,000\nhello" in text
        # "world" [5,8] vs deletion [6,7]: the two keep-overlaps
        # ([5,6] on (0,6) and [7,8] on (7,12)) concatenate to [5,7] on the
        # exported timeline (same straddler semantics as the main track).
        assert "00:00:05,000 --> 00:00:07,000" in text

    def test_map_deletions_false_passes_through(self, tmp_path):
        out = tmp_path / "track.srt"
        res = export_track_subtitle(
            TRACK, EDITS, str(out), media_duration=12.0, map_deletions=False
        )
        assert res["success"], res
        text = out.read_text(encoding="utf-8")
        assert "00:00:05,000 --> 00:00:08,000" in text
        assert "gone" in text

    def test_vtt_format(self, tmp_path):
        out = tmp_path / "track.vtt"
        res = export_track_subtitle(
            TRACK, EDITS, str(out), media_duration=12.0, fmt="vtt"
        )
        assert res["success"], res
        text = out.read_text(encoding="utf-8")
        assert text.startswith("WEBVTT")
        assert "00:00:01.000 --> 00:00:03.000" in text

    def test_legacy_srt_wrapper_keeps_original_timestamps(self, tmp_path):
        out = tmp_path / "legacy.srt"
        res = export_track_srt(TRACK, str(out))
        assert res["success"], res
        assert "00:00:05,000 --> 00:00:08,000" in out.read_text(encoding="utf-8")

    def test_main_and_track_share_one_mapping(self, tmp_path):
        # Same main segment mapped via export_srt and via the track channel
        # must land on the same exported timestamps (R9.1: one mapping).
        from core.export_service import export_srt

        main = [seg("s1", 5.0, 8.0, "main")]
        out_main = tmp_path / "main.srt"
        res = export_srt(main, EDITS, str(out_main), media_duration=12.0)
        assert res["success"], res
        out_track = tmp_path / "track2.srt"
        res = export_track_subtitle(
            {"id": "t", "segments": [seg("e1", 5.0, 8.0, "ext")]},
            EDITS,
            str(out_track),
            media_duration=12.0,
        )
        assert res["success"], res
        assert "00:00:05,000 --> 00:00:07,000" in out_main.read_text(encoding="utf-8")
        assert "00:00:05,000 --> 00:00:07,000" in out_track.read_text(encoding="utf-8")


class TestExportBilingual:
    def test_bilingual_pairs_bound_segments_only(self, tmp_path):
        out = tmp_path / "bi.srt"
        bindings = [
            {"main_segment_id": "s1", "extension_segment_id": "e1"},
        ]
        main = [seg("s1", 1.0, 3.0, "你好"), seg("s2", 5.0, 8.0, "世界")]
        track = {"id": "t", "segments": [seg("e1", 1.2, 3.2, "hello"), seg("e2", 5.0, 8.0, "world")]}
        res = export_bilingual_subtitle(
            main, track, bindings, [], str(out), media_duration=12.0
        )
        assert res["success"], res
        text = out.read_text(encoding="utf-8")
        # paired main gets two lines
        assert "你好\nhello" in text
        # unbound main is single-line
        assert "世界" in text and "world" not in text

    def test_bilingual_vtt(self, tmp_path):
        out = tmp_path / "bi.vtt"
        main = [seg("s1", 1.0, 3.0, "你好")]
        track = {"id": "t", "segments": [seg("e1", 1.2, 3.2, "hello")]}
        bindings = [{"main_segment_id": "s1", "extension_segment_id": "e1"}]
        res = export_bilingual_subtitle(
            main, track, bindings, [], str(out), media_duration=12.0, fmt="vtt"
        )
        assert res["success"], res
        text = out.read_text(encoding="utf-8")
        assert text.startswith("WEBVTT")
        assert "你好\nhello" in text
