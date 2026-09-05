"""v3.0.4 P2-3 M2-2: track-scoped pending corrections (store / get).

Locks (SPEC M2-2 / PLAN P2-3):
- Mutual-clearing is scope-exact: a store only clears the pending set
  of the SAME scope (``track_id=""`` = main track); every other scope's
  pending set is untouched, in both directions.
- Compat rule: legacy details written before v3.0.4 (no ``track_id``
  key) parse as "" = main-track scope -- a main-track store clears them,
  a track store does not. Unparseable details are never cleared
  (conservative).
- store writes both ``track_id`` and ``timeline_id`` into the detail
  JSON (timeline_id feeds the M2-3 accept/reject pinning guard).
- get_subtitle_corrections appends ``track_id`` / ``track_name`` per
  entry ("" = main track), resolves segment times inside the owning
  scope (missing segment falls back to 0.0), and skips entries whose
  extension track no longer exists (died with delete_track).
- Defensive: storing into a non-empty track_id that matches no track
  fails explicitly and clears nothing.

Orchestration follows the SPEC M1-5 concurrency constraint: stores run
strictly one after another with intermediate state asserted -- no
concurrent writes are constructed.
"""

from __future__ import annotations

import json

from core.models import (
    AnalysisResult,
    Segment,
    SegmentType,
    SubtitleTrack,
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


def _corrs_for(segments, marker: str) -> list[dict]:
    return [
        {
            "segment_id": s.id,
            "corrected_text": s.text + marker,
            "changes": ["punctuation"],
            "category": "punctuation",
            "confidence": 0.9,
        }
        for s in segments
    ]


def _pending(svc, scope=None) -> list[AnalysisResult]:
    """Raw pending corrections, optionally filtered by track scope.

    Reads tl.analysis.results directly and parses detail JSON by hand --
    independent of the service under test.
    """
    tl = svc._current.get_timeline("default")
    out = []
    for r in tl.analysis.results:
        if r.type != "llm_subtitle_correction":
            continue
        if scope is not None:
            payload = json.loads(r.detail)
            if payload.get("track_id", "") != scope:
                continue
        out.append(r)
    return out


def _install_results(svc, results: list[AnalysisResult]) -> None:
    tl = svc._current.get_timeline("default")
    svc._update_timeline_by_id(
        "default", analysis=tl.analysis.model_copy(update={"results": results})
    )


# ================================================================
# Scoped mutual-clearing (both directions, serialized calls)
# ================================================================


class TestScopedMutualClearing:
    def test_track_store_keeps_main_pending(self, tmp_dir, monkeypatch):
        """Forward: storing on the track must not touch the main pending
        set being reviewed."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])

        r1 = svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        assert r1["data"]["stored_count"] == 2
        r2 = svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )
        assert r2["data"]["stored_count"] == 2

        assert len(_pending(svc, "")) == 2  # main untouched
        assert len(_pending(svc, "trk_a")) == 2
        assert len(_pending(svc)) == 4

    def test_main_store_keeps_track_pending(self, tmp_dir, monkeypatch):
        """Reverse: storing on the main track must not touch the track's
        pending set."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])

        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )

        assert len(_pending(svc, "trk_a")) == 2  # track untouched
        assert len(_pending(svc, "")) == 2
        assert len(_pending(svc)) == 4

    def test_track_rerun_clears_only_that_track(self, tmp_dir, monkeypatch):
        """Re-running the track store replaces only the track's pending
        set (2 not 4); the main pending set is untouched."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])

        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix 2]"), "default", track_id="trk_a"
        )

        assert len(_pending(svc, "trk_a")) == 2  # not 4
        assert len(_pending(svc, "")) == 2  # main never touched

    def test_main_rerun_count_regression(self, tmp_dir, monkeypatch):
        """Main-track regression: two main stores -> pending count 2 not 4
        (scoped-world mirror of test_store_clears_previous_corrections,
        with extension tracks present)."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])

        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix 2]"), "default"
        )

        assert len(_pending(svc, "")) == 2  # not 4


# ================================================================
# Compat rule: legacy details without a track_id key
# ================================================================


def _legacy_result(main_seg: Segment) -> AnalysisResult:
    """v3.0.3-shaped correction record: detail has no track_id key."""
    return AnalysisResult(
        id=f"corr-legacy-{main_seg.id}",
        type="llm_subtitle_correction",
        segment_ids=[main_seg.id],
        confidence=0.9,
        detail=json.dumps(
            {
                "original_text": main_seg.text,
                "corrected_text": main_seg.text + " [legacy]",
                "changes": ["punctuation"],
                "category": "punctuation",
            },
            ensure_ascii=False,
        ),
    )


class TestLegacyCompat:
    def test_legacy_detail_cleared_by_main_store(self, tmp_dir, monkeypatch):
        """No track_id key -> "" main scope -> a main store replaces it."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        _install_results(svc, [_legacy_result(main[0])])

        res = svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        assert res["data"]["stored_count"] == 2

        ids = {r.id for r in _pending(svc)}
        assert f"corr-legacy-{main[0].id}" not in ids  # legacy replaced
        assert len(_pending(svc)) == 2

    def test_legacy_detail_survives_track_store(self, tmp_dir, monkeypatch):
        """A track store must never clear a legacy (main-scoped) record."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        _install_results(svc, [_legacy_result(main[0])])

        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )

        ids = {r.id for r in _pending(svc)}
        assert f"corr-legacy-{main[0].id}" in ids  # survived
        assert len(_pending(svc)) == 3  # legacy + 2 track entries

    def test_unparseable_detail_never_cleared(self, tmp_dir, monkeypatch):
        """Conservative rule: a correction result whose detail is not JSON
        is never matched by the mutual-clearing."""
        main = make_segments(2)
        svc = _service(monkeypatch, tmp_dir, main)
        broken = AnalysisResult(
            id="corr-broken-1",
            type="llm_subtitle_correction",
            segment_ids=[main[0].id],
            confidence=0.9,
            detail="not json {",
        )
        _install_results(svc, [broken])

        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )

        ids = {r.id for r in _pending(svc)}
        assert "corr-broken-1" in ids  # kept, not guessed away
        assert len(_pending(svc)) == 3  # broken + 2 new


# ================================================================
# Defensive missing-track store (service layer; handler blocks earlier)
# ================================================================


class TestStoreMissingTrack:
    def test_missing_track_fails_and_clears_nothing(self, tmp_dir, monkeypatch):
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        assert len(_pending(svc)) == 2

        res = svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default",
            track_id="trk_missing",
        )
        assert not res["success"]
        assert "Track" in res["error"] and "trk_missing" in res["error"]
        # Nothing was cleared and nothing was stored.
        assert len(_pending(svc)) == 2


# ================================================================
# get_subtitle_corrections: scope-aware output
# ================================================================


class TestGetScopeOutput:
    def test_output_appends_track_id_and_name(self, tmp_dir, monkeypatch):
        """Main entries: track_id="" and track_name=""; track entries:
        the owning track's id and name."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )

        data = svc.correction.get_subtitle_corrections("default")["data"]
        main_entries = [d for d in data if d["track_id"] == ""]
        track_entries = [d for d in data if d["track_id"] == "trk_a"]
        assert len(main_entries) == 2
        assert len(track_entries) == 2
        for d in main_entries:
            assert d["track_id"] == ""
            assert d["track_name"] == ""  # frontend reads "" as main track
        for d in track_entries:
            assert d["track_id"] == "trk_a"
            assert d["track_name"] == "Track A"

    def test_segment_times_resolve_within_scope(self, tmp_dir, monkeypatch):
        """Track entries resolve start/end against the TRACK segment (own
        time base), never against main-track segments; a scope-missing
        segment id falls back to 0.0."""
        main = make_segments(2)  # times around 0-10s
        track = _track("trk_a", "Track A", ["alpha"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )
        ghost = AnalysisResult(
            id="corr-ghost-1",
            type="llm_subtitle_correction",
            segment_ids=["track_trk_a_seg_ghost"],
            confidence=0.9,
            detail=json.dumps(
                {
                    "original_text": "ghost",
                    "corrected_text": "ghost!",
                    "track_id": "trk_a",
                    "timeline_id": "default",
                },
                ensure_ascii=False,
            ),
        )
        _install_results(svc, _pending(svc) + [ghost])

        data = svc.correction.get_subtitle_corrections("default")["data"]
        live = next(d for d in data if d["id"] != "corr-ghost-1")
        assert live["start"] == track.segments[0].start  # 100.0, not main time
        assert live["end"] == track.segments[0].end
        ghost_out = next(d for d in data if d["id"] == "corr-ghost-1")
        assert ghost_out["start"] == 0.0 and ghost_out["end"] == 0.0  # fallback

    def test_dangling_track_entries_filtered(self, tmp_dir, monkeypatch):
        """After delete_track the track's pending entries vanish from the
        list (died with the track); main entries stay."""
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )

        assert svc.delete_track("trk_a")["success"]

        data = svc.correction.get_subtitle_corrections("default")["data"]
        assert len(data) == 2  # only main entries survive the filter
        assert all(d["track_id"] == "" for d in data)


# ================================================================
# detail JSON keys: track_id + timeline_id (M2-3 pinning feed)
# ================================================================


class TestDetailKeys:
    def test_store_writes_track_and_timeline_keys(self, tmp_dir, monkeypatch):
        main = make_segments(2)
        track = _track("trk_a", "Track A", ["alpha", "beta"])
        svc = _service(monkeypatch, tmp_dir, main, [track])
        svc.correction.store_subtitle_corrections(
            _corrs_for(main, " [main fix]"), "default"
        )
        svc.correction.store_subtitle_corrections(
            _corrs_for(track.segments, " [ext fix]"), "default", track_id="trk_a"
        )

        for r in _pending(svc):
            detail = json.loads(r.detail)
            assert "timeline_id" in detail
            assert detail["timeline_id"] == "default"  # pinning key (M2-3)
            assert "track_id" in detail
            assert detail["track_id"] in ("", "trk_a")
        scopes = {json.loads(r.detail)["track_id"] for r in _pending(svc)}
        assert scopes == {"", "trk_a"}
