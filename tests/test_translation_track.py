"""v3.0.4 P1-4 M1-4: create_translation_track batch-write contract tests.

Locks (SPEC M1-4, R1.3):
- Single-patch persistence: ONE tracks+bindings patch per track with the
  revision advancing by exactly +1, even at the 1000-segment scale (the
  add_track_segment loop -- one patch per segment -- is forbidden).
- Undo layer integrity: the patch's tracks/bindings layers are the
  pre-write state plus the new track and its bindings, so one layered
  undo (apply_undo) reverts the whole track.
- Write-side guards with zero writes: timeline pinning and duplicate
  same-language translation track rejection.
- Idempotent reconciliation: vanished segment ids are reported in
  uncovered_ids (partial) or reject the whole write (all vanished /
  empty items).
- Track segment ids live in the ``track_{track_id}_seg_{start:.3f}``
  namespace, times are copied verbatim from the CURRENT main segments,
  bindings are exact 1:1 with zero offsets; bind=False skips bindings.
"""

from __future__ import annotations

import pytest

from core.models import Segment, SegmentType
from core.project_service import ProjectService


@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    return service


def _install_main_segments(svc: ProjectService, segs: list[Segment]) -> None:
    """Install main-track segments the way the service sees them 'now'."""
    tl = svc.active_timeline
    svc._current = svc._current.model_copy(
        update={
            "timelines": [
                tl.model_copy(
                    update={
                        "transcript": tl.transcript.model_copy(
                            update={"segments": segs}
                        )
                    }
                )
            ]
        }
    )


def _main_segments(count: int) -> list[Segment]:
    return [
        Segment(
            id=f"seg_{1.0 + i * 2.0:.3f}",
            type=SegmentType.SUBTITLE,
            start=1.0 + i * 2.0,
            end=2.0 + i * 2.0,
            text=f"原文{i}",
        )
        for i in range(count)
    ]


def _items(segs: list[Segment]) -> list[dict]:
    """Handler-shaped items: main id + copied main times + translation."""
    return [
        {"segment_id": s.id, "start": s.start, "end": s.end, "text": f"trans {i}"}
        for i, s in enumerate(segs)
    ]


# ---------------------------------------------------------------------------
# Single-patch persistence (M5: thousand-segment scale)
# ---------------------------------------------------------------------------


class TestSinglePatch:
    @pytest.mark.parametrize("count", [3, 1000])
    def test_revision_exactly_plus_one(self, svc, count):
        segs = _main_segments(count)
        _install_main_segments(svc, segs)
        rev_before = svc._revision

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", _items(segs)
        )

        assert res["success"]
        data = res["data"]
        # ONE patch: revision advanced by exactly one for the whole track.
        assert data["revision"] == rev_before + 1
        assert svc._revision == rev_before + 1
        # Both layers ride that single patch.
        (track,) = [t for t in data["tracks"] if t["role"] == "translation"]
        assert len(track["segments"]) == count
        assert len(data["bindings"]) == count
        meta = data["meta"]["translation"]
        assert meta["written_count"] == count
        assert meta["target_count"] == count
        assert meta["uncovered_ids"] == []
        assert meta["track_id"] == track["id"]
        # Persisted state matches the patch.
        assert len(svc.active_timeline.transcript.tracks[0].segments) == count
        assert len(svc.active_timeline.transcript.bindings) == count

    def test_undo_layers_revert_whole_track(self, svc):
        segs = _main_segments(5)
        _install_main_segments(svc, segs)
        pre_tracks = [
            t.model_dump(mode="json") for t in svc.active_timeline.transcript.tracks
        ]
        pre_bindings = [
            b.model_dump(mode="json") for b in svc.active_timeline.transcript.bindings
        ]

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", _items(segs)
        )
        assert res["success"]
        data = res["data"]
        new_track_id = data["meta"]["translation"]["track_id"]

        # The patch layers are exactly pre-state + new track / bindings:
        # replacing the layer contents with the pre-state (what one undo
        # step does) removes the whole track including its bindings.
        assert [t["id"] for t in data["tracks"]] == [t["id"] for t in pre_tracks] + [
            new_track_id
        ]
        assert len(data["bindings"]) == len(pre_bindings) + len(segs)

        undo = svc.apply_undo(
            {"tracks": pre_tracks, "bindings": pre_bindings},
            base_revision=data["revision"],
        )
        assert undo["success"]
        tr = svc.active_timeline.transcript
        assert [t.id for t in tr.tracks] == [t["id"] for t in pre_tracks]
        assert [b.id for b in tr.bindings] == [b["id"] for b in pre_bindings]


# ---------------------------------------------------------------------------
# Write-side guards (zero writes)
# ---------------------------------------------------------------------------


class TestWriteSideGuards:
    def test_duplicate_language_rejected_zero_write(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        # The user created a same-language translation track while the
        # LLM task was running.
        assert svc.add_track("已有翻译", language="en", role="translation")["success"]
        rev_before = svc._revision

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", _items(segs)
        )

        assert not res["success"]
        assert "可清空或删除该轨后重试" in res["error"]
        # Zero writes: revision unchanged, track list untouched.
        assert svc._revision == rev_before
        assert len(svc.active_timeline.transcript.tracks) == 1
        assert svc.active_timeline.transcript.bindings == []

    def test_duplicate_check_ignores_other_roles_and_languages(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        assert svc.add_track("扩展轨", language="en", role="extension")["success"]
        assert svc.add_track("日语翻译", language="ja", role="translation")["success"]

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", _items(segs)
        )

        assert res["success"]
        assert len(svc.active_timeline.transcript.tracks) == 3

    def test_timeline_pinning_rejects_stale_timeline_id(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        stale_id = svc.active_timeline.id
        # The user switched timelines while the LLM task was running.
        assert svc.create_timeline("第二时间轴")["success"]
        rev_before = svc._revision

        res = svc.create_translation_track(stale_id, "English", "en", _items(segs))

        assert not res["success"]
        assert "Timeline no longer active" in res["error"]
        assert svc._revision == rev_before
        # Zero writes on BOTH timelines.
        for tl in svc._current.timelines:
            assert tl.transcript.tracks == []
            assert tl.transcript.bindings == []


# ---------------------------------------------------------------------------
# Idempotent reconciliation against the CURRENT main track
# ---------------------------------------------------------------------------


class TestReconciliation:
    def test_partial_uncovered_reported_and_written(self, svc):
        segs = _main_segments(4)
        _install_main_segments(svc, segs)
        items = _items(segs)
        # One target segment was deleted while the task ran.
        items[2]["segment_id"] = "seg_gone.000"

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", items
        )

        assert res["success"]
        meta = res["data"]["meta"]["translation"]
        assert meta["uncovered_ids"] == ["seg_gone.000"]
        assert meta["written_count"] == 3
        assert meta["target_count"] == 4
        (track,) = svc.active_timeline.transcript.tracks
        assert len(track.segments) == 3
        assert len(svc.active_timeline.transcript.bindings) == 3

    def test_all_uncovered_rejected_zero_write(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        items = [
            {"segment_id": f"gone_{i}", "start": 1.0, "end": 2.0, "text": "x"}
            for i in range(3)
        ]
        rev_before = svc._revision

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", items
        )

        assert not res["success"]
        assert res["error"] == "所有目标段已被删除"
        assert svc._revision == rev_before
        assert svc.active_timeline.transcript.tracks == []
        assert svc.active_timeline.transcript.bindings == []

    def test_empty_items_rejected_zero_write(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        rev_before = svc._revision

        res = svc.create_translation_track(svc.active_timeline.id, "English", "en", [])

        assert not res["success"]
        assert res["error"] == "所有目标段已被删除"
        assert svc._revision == rev_before


# ---------------------------------------------------------------------------
# Namespace, verbatim time copy, zero-offset bindings, bind=False
# ---------------------------------------------------------------------------


class TestNamespaceTimesAndBindings:
    def test_id_namespace_time_copy_and_zero_offsets(self, svc):
        segs = _main_segments(4)
        _install_main_segments(svc, segs)
        items = _items(segs)
        # Stale pipeline copies of the times must NOT win: the CURRENT
        # main segment's start/end is the source of truth.
        items[1]["start"] = 99.0
        items[1]["end"] = 99.5

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", items
        )

        assert res["success"]
        tr = svc.active_timeline.transcript
        (track,) = tr.tracks
        track_id = track.id
        assert track_id.startswith("trk_")
        assert track.role == "translation"
        assert track.language == "en"
        assert track.name == "English"

        for i, (main, ext) in enumerate(zip(segs, track.segments, strict=True)):
            # Namespace isolation, same generator as import_srt_as_track.
            assert ext.id == f"track_{track_id}_seg_{main.start:.3f}"
            assert ext.id.startswith(f"track_{track_id}_seg_")
            # Verbatim copy of the CURRENT main-track times.
            assert ext.start == main.start
            assert ext.end == main.end
            assert ext.text == f"trans {i}"

        by_main = {b["main_segment_id"]: b for b in res["data"]["bindings"]}
        assert set(by_main) == {s.id for s in segs}
        for main_id, b in by_main.items():
            main = next(s for s in segs if s.id == main_id)
            assert b["track_id"] == track_id
            assert b["extension_segment_id"] == f"track_{track_id}_seg_{main.start:.3f}"
            assert b["start_offset"] == 0.0
            assert b["end_offset"] == 0.0

        # Main track untouched.
        assert [s.id for s in tr.segments] == [s.id for s in segs]

    def test_bind_false_writes_segments_without_bindings(self, svc):
        segs = _main_segments(4)
        _install_main_segments(svc, segs)

        res = svc.create_translation_track(
            svc.active_timeline.id, "English", "en", _items(segs), bind=False
        )

        assert res["success"]
        tr = svc.active_timeline.transcript
        (track,) = tr.tracks
        assert len(track.segments) == 4
        assert tr.bindings == []
        assert res["data"]["bindings"] == []
        meta = res["data"]["meta"]["translation"]
        assert meta["written_count"] == 4


# ---------------------------------------------------------------------------
# v3.0.5 R5.3 (M5.3 ruling 5): merge_translation_track (resumable write side)
# ---------------------------------------------------------------------------


def _install_existing_track(svc, bound: list[Segment], language: str = "en") -> str:
    """Create a translation track via the production write path, binding
    the `bound` main segments (the resume-target state)."""
    res = svc.create_translation_track(
        svc.active_timeline.id, "English", language, _items(bound)
    )
    assert res["success"]
    return res["data"]["meta"]["translation"]["track_id"]


class TestMergeTranslationTrack:
    def test_single_patch_revision_plus_one_and_meta(self, svc):
        segs = _main_segments(5)
        _install_main_segments(svc, segs)
        track_id = _install_existing_track(svc, segs[:3])
        rev_before = svc._revision

        res = svc.merge_translation_track(
            svc.active_timeline.id, track_id, _items(segs[3:])
        )

        assert res["success"]
        data = res["data"]
        # ONE patch for the whole merge batch (never per-segment).
        assert data["revision"] == rev_before + 1
        assert svc._revision == rev_before + 1
        track = next(t for t in data["tracks"] if t["id"] == track_id)
        assert len(track["segments"]) == 5  # 3 existing + 2 merged
        assert len(data["bindings"]) == 5
        meta = data["meta"]["translation"]
        assert meta["track_id"] == track_id
        assert meta["merged_count"] == 2
        assert meta["written_count"] == 2
        assert meta["target_count"] == 2
        assert meta["uncovered_ids"] == []
        # merged segment ids live in the track namespace, times verbatim
        merged_ids = {s["id"] for s in track["segments"]}
        assert merged_ids >= {
            f"track_{track_id}_seg_{s.start:.3f}" for s in segs[3:]
        }
        # persisted state matches the patch
        persisted = next(
            t for t in svc.active_timeline.transcript.tracks if t.id == track_id
        )
        assert len(persisted.segments) == 5

    def test_timeline_pinning_rejected_zero_write(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)
        track_id = _install_existing_track(svc, segs[:1])
        rev_before = svc._revision

        res = svc.merge_translation_track(
            "other-timeline", track_id, _items(segs[1:])
        )

        assert not res["success"]
        assert "已切换时间轴" in res["error"]
        assert svc._revision == rev_before

    def test_missing_track_rejected(self, svc):
        segs = _main_segments(3)
        _install_main_segments(svc, segs)

        res = svc.merge_translation_track(
            svc.active_timeline.id, "trk_nope", _items(segs)
        )

        assert not res["success"]
        assert "翻译轨不存在" in res["error"]

    def test_binding_collision_rejected_zero_write(self, svc):
        segs = _main_segments(4)
        _install_main_segments(svc, segs)
        track_id = _install_existing_track(svc, segs[:2])
        rev_before = svc._revision

        # items include an ALREADY-bound main id: gap derivation makes this
        # a "should not happen" -- defensive refusal beats silent overwrite.
        res = svc.merge_translation_track(
            svc.active_timeline.id, track_id, _items([segs[2], segs[0]])
        )

        assert not res["success"]
        assert "已绑定" in res["error"]
        assert svc._revision == rev_before

    def test_uncovered_reported_for_vanished_ids(self, svc):
        segs = _main_segments(3)
        # segs[1] is deleted mid-run: the main track only keeps 0 and 2.
        _install_main_segments(svc, [segs[0], segs[2]])
        track_id = _install_existing_track(svc, [segs[0]])

        res = svc.merge_translation_track(
            svc.active_timeline.id, track_id, _items([segs[2], segs[1]])
        )

        assert res["success"]
        meta = res["data"]["meta"]["translation"]
        assert meta["merged_count"] == 1
        assert meta["uncovered_ids"] == [segs[1].id]
