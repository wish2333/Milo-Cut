"""v3.0.4 P2-4 M2-3: accept/reject superset patch-ification (incl. debt #14).

Locks (SPEC M2-3 / PLAN P2-4):
- accept main track: logic unchanged, success payload is a SUPERSET --
  ``segment_id`` stays (review-UI / test_subtitle_correction_review.py:157
  compat) and ``patch`` joins with segments + analysis layers; the
  revision bumps exactly +1 per accept.
- accept extension track: writes the corrected text into the track
  segment (whole-track replacement), bindings are untouched (text has no
  geometry semantics), the patch carries tracks + analysis layers (no
  segments layer), and the main-track segments are unchanged.
- reject: superset too -- patch carries the analysis layer only, the
  result is removed, segment text is untouched.
- reattach_words with words=[] (SRT import / translation tracks) returns
  [] and never raises.
- timeline pinning (R3): a detail whose ``timeline_id`` differs from the
  active timeline fails accept AND reject with zero writes; legacy
  details without the key pass (compat rule).
- accept_high_confidence_corrections reuses the single-accept path, so
  its per-item results naturally carry the ``patch`` key.
"""

from __future__ import annotations

import json

from core.models import (
    AnalysisResult,
    Segment,
    SegmentType,
    SubtitleTrack,
    TrackBinding,
)
from core.project_service import ProjectService
from tests.mocks.factories import make_project, make_segments

_TRACK_TIME_BASE = 100.0  # distinct from main-segment times on purpose


def _service(monkeypatch, tmp_dir, main_segments, tracks=()):
    """ProjectService over a 'default' project with extension tracks."""
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_dir / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
    svc = ProjectService()
    project = make_project(segments=main_segments)
    tl = project.timelines[0]
    project = project.model_copy(
        update={
            "timelines": [
                tl.model_copy(
                    update={
                        "transcript": tl.transcript.model_copy(
                            update={"tracks": list(tracks)}
                        )
                    }
                )
            ]
        }
    )
    svc._current = project
    return svc


def _track(track_id: str, name: str, texts: list[str]) -> SubtitleTrack:
    """Extension track on its own time base (never overlaps main times)."""
    segs = [
        Segment(
            id=f"track_{track_id}_seg_{_TRACK_TIME_BASE + i:.3f}",
            type=SegmentType.SUBTITLE,
            start=_TRACK_TIME_BASE + i,
            end=_TRACK_TIME_BASE + i + 1.0,
            text=text,
        )
        for i, text in enumerate(texts)
    ]
    return SubtitleTrack(
        id=track_id, role="extension", name=name, language="en", segments=segs
    )


def _binding(track_id: str, main_seg_id: str, ext_seg_id: str) -> TrackBinding:
    return TrackBinding(
        id=f"bnd-{ext_seg_id}",
        track_id=track_id,
        main_segment_id=main_seg_id,
        extension_segment_id=ext_seg_id,
    )


def _corrs_for(segments, marker: str, confidence: float = 0.9) -> list[dict]:
    return [
        {
            "segment_id": s.id,
            "corrected_text": s.text + marker,
            "changes": ["punctuation"],
            "category": "punctuation",
            "confidence": confidence,
        }
        for s in segments
    ]


def _tl(svc, timeline_id: str = "default"):
    return svc._current.get_timeline(timeline_id)


# ================================================================
# accept -- main track superset
# ================================================================


class TestAcceptMainTrackSuperset:
    def test_returns_segment_id_plus_patch_with_revision_bump(self, tmp_dir, monkeypatch):
        """Superset contract: segment_id stays (:157 compat), patch joins
        with segments + analysis layers, revision bumps exactly +1."""
        segs = make_segments(2)
        svc = _service(monkeypatch, tmp_dir, segs)
        corrs = _corrs_for(segs, " [fix]")
        svc.correction.store_subtitle_corrections(corrs, "default")

        target_id = svc.correction.get_subtitle_corrections("default")["data"][0]["id"]
        before_rev = svc._revision

        res = svc.correction.accept_subtitle_correction(target_id)
        assert res["success"]

        # Legacy key preserved verbatim.
        assert res["data"]["segment_id"] == segs[0].id
        # New superset key.
        patch = res["data"]["patch"]
        assert isinstance(patch, dict)
        assert patch["segments"] is not None
        assert patch["analysis"] is not None
        assert patch["tracks"] is None  # main-track accept never touches tracks
        assert patch["bindings"] is None
        # Revision monotonic: exactly +1 (no full refresh path involved).
        assert patch["revision"] == before_rev + 1
        assert svc._revision == before_rev + 1
        assert patch["timeline_id"] == "default"
        # The analysis layer reflects the result removal.
        result_ids = [r["id"] for r in patch["analysis"]["results"]]
        assert target_id not in result_ids
        # The segments layer reflects the corrected text.
        patched_seg = next(s for s in patch["segments"] if s["id"] == segs[0].id)
        assert patched_seg["text"] == corrs[0]["corrected_text"]

    def test_batch_accept_reuses_single_accept_superset(self, tmp_dir, monkeypatch):
        """accept_high_confidence_corrections delegates to the single
        accept, so every accepted item's data carries the patch key."""
        segs = make_segments(2)
        svc = _service(monkeypatch, tmp_dir, segs)
        corrs = _corrs_for(segs, " [fix]", confidence=0.95)
        svc.correction.store_subtitle_corrections(corrs, "default")

        captured: list[dict] = []
        orig_accept = svc.correction.accept_subtitle_correction

        def _spy(rid: str) -> dict:
            res = orig_accept(rid)
            if res.get("success"):
                captured.append(res["data"])
            return res

        svc.correction.accept_subtitle_correction = _spy  # type: ignore[method-assign]

        res = svc.correction.accept_high_confidence_corrections("default", threshold=0.8)
        assert res["success"]
        assert res["data"]["accepted_count"] == 2
        assert captured, "batch must reuse the single-accept path"
        assert all("patch" in d for d in captured)


# ================================================================
# accept -- extension track path
# ================================================================


class TestAcceptExtensionTrack:
    def _setup(self, monkeypatch, tmp_dir):
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        binding = _binding("trk_a", main[0].id, track.segments[0].id)
        svc = _service(monkeypatch, tmp_dir, main, [track])
        # Install one binding so the "bindings untouched" contract is
        # observable (count AND content).
        tl = _tl(svc)
        svc._update_timeline_by_id(
            "default",
            transcript=tl.transcript.model_copy(update={"bindings": [binding]}),
        )
        corrs = _corrs_for(track.segments, " [ext fix]")
        stored = svc.correction.store_subtitle_corrections(corrs, "default", track_id="trk_a")
        assert stored["data"]["stored_count"] == 2
        return svc, main, corrs

    def test_accept_writes_track_segment_and_leaves_bindings_untouched(
        self, tmp_dir, monkeypatch
    ):
        svc, main, corrs = self._setup(monkeypatch, tmp_dir)
        entry = svc.correction.get_subtitle_corrections("default")["data"][0]
        bindings_before = [b.model_dump() for b in _tl(svc).transcript.bindings]
        main_before = [s.model_dump() for s in _tl(svc).transcript.segments]
        before_rev = svc._revision

        res = svc.correction.accept_subtitle_correction(entry["id"])
        assert res["success"]
        assert res["data"]["segment_id"] == entry["segment_id"]
        assert res["data"]["track_id"] == "trk_a"

        tl = _tl(svc)
        # Track segment text updated in place (whole-track replacement).
        track = next(t for t in tl.transcript.tracks if t.id == "trk_a")
        seg = next(s for s in track.segments if s.id == entry["segment_id"])
        assert seg.text == corrs[0]["corrected_text"]
        assert seg.dirty_flags.get("llm_corrected") is True

        # Bindings: zero change in count and content.
        assert [b.model_dump() for b in tl.transcript.bindings] == bindings_before

        # Main-track segments: zero change.
        assert [s.model_dump() for s in tl.transcript.segments] == main_before

        # Patch layers = tracks + analysis exactly (no segments layer).
        patch = res["data"]["patch"]
        assert patch["tracks"] is not None
        assert patch["analysis"] is not None
        assert patch["segments"] is None
        assert patch["bindings"] is None
        assert patch["revision"] == before_rev + 1
        # The tracks layer carries the corrected segment.
        patched_track = next(t for t in patch["tracks"] if t["id"] == "trk_a")
        patched_seg = next(
            s for s in patched_track["segments"] if s["id"] == entry["segment_id"]
        )
        assert patched_seg["text"] == corrs[0]["corrected_text"]

    def test_accept_track_segment_with_empty_words(self, tmp_dir, monkeypatch):
        """SRT-import / translation track segments carry words=[] -- the
        accept must succeed with reattach_words returning [] (never
        TimestampCorruptionError)."""
        svc, _main, corrs = self._setup(monkeypatch, tmp_dir)
        entries = svc.correction.get_subtitle_corrections("default")["data"]

        res = svc.correction.accept_subtitle_correction(entries[0]["id"])
        assert res["success"]

        tl = _tl(svc)
        track = next(t for t in tl.transcript.tracks if t.id == "trk_a")
        seg = next(s for s in track.segments if s.id == entries[0]["segment_id"])
        assert seg.text == corrs[0]["corrected_text"]
        assert seg.words == []  # reattach skipped, empty list returned verbatim

    def test_accept_missing_track_fails(self, tmp_dir, monkeypatch):
        """A dangling track scope (track deleted after store) fails
        explicitly instead of writing anything."""
        main = make_segments(1)
        track = _track("trk_gone", "Ghost", ["x"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [fix]"), "default", track_id="trk_gone"
        )
        # Delete the track out from under the pending correction.
        tl = _tl(svc)
        svc._update_timeline_by_id(
            "default",
            transcript=tl.transcript.model_copy(
                update={"tracks": [t for t in tl.transcript.tracks if t.id != "trk_gone"]}
            ),
        )
        entry = svc.correction.get_subtitle_corrections("default")["data"]
        assert entry == []  # dangling entries are filtered on read

        # Reach the raw result id directly (get filters it; accept must
        # still fail cleanly on the stale scope).
        raw = next(
            r for r in _tl(svc).analysis.results
            if r.type == "llm_subtitle_correction"
        )
        res = svc.correction.accept_subtitle_correction(raw.id)
        assert not res["success"]
        assert "Track" in res["error"]


# ================================================================
# reject superset
# ================================================================


class TestRejectSuperset:
    def test_reject_returns_analysis_only_patch(self, tmp_dir, monkeypatch):
        segs = make_segments(2)
        svc = _service(monkeypatch, tmp_dir, segs)
        original_text = segs[0].text
        svc.correction.store_subtitle_corrections(_corrs_for(segs, " [fix]"), "default")
        entry = svc.correction.get_subtitle_corrections("default")["data"][0]
        before_rev = svc._revision

        res = svc.correction.reject_subtitle_correction(entry["id"])
        assert res["success"]
        assert res["data"]["segment_id"] == segs[0].id

        patch = res["data"]["patch"]
        # Layer ruling: reject only removes the result -> analysis only.
        assert patch["analysis"] is not None
        assert patch["segments"] is None
        assert patch["tracks"] is None
        assert patch["revision"] == before_rev + 1

        # Result removed, segment text untouched.
        tl = _tl(svc)
        remaining = [
            r for r in tl.analysis.results if r.type == "llm_subtitle_correction"
        ]
        assert len(remaining) == 1
        seg = next(s for s in tl.transcript.segments if s.id == segs[0].id)
        assert seg.text == original_text


# ================================================================
# timeline pinning (R3)
# ================================================================


def _fork_and_activate(svc, fork_id: str = "fork") -> None:
    """Fork the 'default' timeline (sharing its analysis results, as
    create_timeline fork does) and make the fork active -- the drift
    scenario the pinning guard defends against."""
    tl = svc._current.get_timeline("default")
    fork = tl.model_copy(update={"id": fork_id, "label": "Fork"})
    svc._current = svc._current.model_copy(
        update={
            "timelines": [t for t in svc._current.timelines] + [fork],
            "active_timeline_id": fork_id,
        }
    )


class TestTimelinePinning:
    def _stored(self, monkeypatch, tmp_dir):
        segs = make_segments(2)
        svc = _service(monkeypatch, tmp_dir, segs)
        corrs = _corrs_for(segs, " [fix]")
        svc.correction.store_subtitle_corrections(corrs, "default")
        entry = svc.correction.get_subtitle_corrections("default")["data"][0]
        return svc, entry, corrs

    def test_accept_on_other_timeline_fails_with_zero_writes(self, tmp_dir, monkeypatch):
        svc, entry, _corrs = self._stored(monkeypatch, tmp_dir)
        _fork_and_activate(svc)
        before_rev = svc._revision
        tl_before = svc._current.get_timeline("fork").model_dump()

        res = svc.correction.accept_subtitle_correction(entry["id"])
        assert not res["success"]
        assert "其他时间轴" in res["error"]
        # Zero writes: revision and the active timeline are untouched.
        assert svc._revision == before_rev
        assert svc._current.get_timeline("fork").model_dump() == tl_before

    def test_reject_on_other_timeline_fails_with_zero_writes(self, tmp_dir, monkeypatch):
        svc, entry, _corrs = self._stored(monkeypatch, tmp_dir)
        _fork_and_activate(svc)
        before_rev = svc._revision
        tl_before = svc._current.get_timeline("fork").model_dump()

        res = svc.correction.reject_subtitle_correction(entry["id"])
        assert not res["success"]
        assert "其他时间轴" in res["error"]
        assert svc._revision == before_rev
        assert svc._current.get_timeline("fork").model_dump() == tl_before

    def test_owning_timeline_still_accepts(self, tmp_dir, monkeypatch):
        """Pinned id == active id -> normal superset accept."""
        svc, entry, corrs = self._stored(monkeypatch, tmp_dir)
        res = svc.correction.accept_subtitle_correction(entry["id"])
        assert res["success"]
        assert "patch" in res["data"]
        seg = next(
            s for s in _tl(svc).transcript.segments if s.id == entry["segment_id"]
        )
        assert seg.text == corrs[0]["corrected_text"]

    def test_legacy_detail_without_timeline_key_passes(self, tmp_dir, monkeypatch):
        """v3.0.3 details carry no timeline_id key -- compat rule: pass."""
        segs = make_segments(1)
        svc = _service(monkeypatch, tmp_dir, segs)
        legacy = AnalysisResult(
            id="corr-legacy-0001",
            type="llm_subtitle_correction",
            segment_ids=[segs[0].id],
            confidence=0.9,
            detail=json.dumps(
                {
                    "original_text": segs[0].text,
                    "corrected_text": segs[0].text + " [legacy]",
                    "changes": ["punctuation"],
                    "category": "punctuation",
                    # no track_id / timeline_id keys (v3.0.3 shape)
                },
                ensure_ascii=False,
            ),
        )
        tl = _tl(svc)
        svc._update_timeline_by_id(
            "default",
            analysis=tl.analysis.model_copy(update={"results": [legacy]}),
        )

        res = svc.correction.accept_subtitle_correction("corr-legacy-0001")
        assert res["success"]
        assert res["data"]["segment_id"] == segs[0].id
        assert "patch" in res["data"]
        seg = next(s for s in _tl(svc).transcript.segments if s.id == segs[0].id)
        assert seg.text.endswith("[legacy]")
