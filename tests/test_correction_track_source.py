"""v3.0.4 P2-2 M2-1: _handle_subtitle_correction secondary-track branch.

Locks (SPEC M2-1 / PLAN P2-2):
- Non-empty ``track_id`` -> the segment source passed to the correction
  pipeline is the extension track itself.
- Confirmed-deletion mapping aligned with the track-aware export: a BOUND
  track segment whose main-track partner is confirmed-deleted is skipped;
  an UNBOUND track segment survives (main-track deletions never touched it).
- Partial delete hints are NOT collected / forwarded on the track path
  (main-track EditDecision concept, SPEC ruling).
- Missing track -> task FAILED with "Track not found" naming the track id.
- Default (no track_id) keeps the v3.0.3 main-track source: subtitle-type
  segments minus confirmed-deleted ones.
- Option B delivery: store_subtitle_corrections now takes ``track_id`` and
  records it in the detail JSON ("" = main track); mutual-clearing stays
  timeline-wide until M2-2 (P2-3).

Mock style follows tests/test_translation_expose.py (MiloCutApi.__new__ +
real ProjectService + synchronous ``TaskManager._execute_task`` driving).
"""

from __future__ import annotations

import json

import pytest

from core.models import (
    EditDecision,
    EditStatus,
    LlmConfig,
    LlmProvider,
    MiloTask,
    Segment,
    SegmentType,
    SubtitleTrack,
    TaskType,
    TrackBinding,
)
from core.project_service import ProjectService
from core.task_manager import TaskManager
from main import MiloCutApi

# ================================================================
# Helpers
# ================================================================

_TOKEN_USAGE = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
_LEDGER = {
    "total": 1,
    "succeeded": 1,
    "retried_ok": 0,
    "failed": [],
    "uncovered_segment_ids": [],
}


def _configured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.DEEPSEEK,
        api_key="sk-test",
        model="deepseek-test",
        temperature=0.3,
        timeout=120,
    )


def _main_seg(seg_id: str, start: float, text: str) -> Segment:
    return Segment(
        id=seg_id,
        type=SegmentType.SUBTITLE,
        start=start,
        end=start + 1.0,
        text=text,
    )


def _track_seg(track_id: str, start: float, text: str) -> Segment:
    # Namespaced id per the SubtitleTrack contract (never collides with
    # main-track ids).
    return Segment(
        id=f"track_{track_id}_seg_{start:.3f}",
        type=SegmentType.SUBTITLE,
        start=start,
        end=start + 1.0,
        text=text,
    )


def _confirmed_delete(seg_id: str) -> EditDecision:
    return EditDecision(
        id=f"edit-{seg_id}",
        start=0.0,
        end=1.0,
        action="delete",
        source="manual",
        status=EditStatus.CONFIRMED,
        target_type="segment",
        target_id=seg_id,
    )


def _correction_pipeline(captured: list[dict] | None = None):
    """Mock analyze_subtitle_correction echoing every input id back."""

    def fake(segments, **kwargs):
        if captured is not None:
            captured.append({"segments": segments, "kwargs": kwargs})
        return {
            "success": True,
            "data": {
                "corrections": [
                    {
                        "segment_id": s["id"],
                        "corrected_text": s.get("text", "") + "!",
                        "changes": ["punctuation"],
                        "category": "punctuation",
                        "confidence": 0.9,
                    }
                    for s in segments
                ],
                "token_usage": dict(_TOKEN_USAGE),
                "ledger": dict(_LEDGER),
            },
        }

    return fake


# ================================================================
# Fixtures / harness
# ================================================================


class _Api:
    """MiloCutApi shell: real ProjectService + captured events."""

    def __init__(self, monkeypatch, tmp_path):
        monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "core.project_service.get_projects_dir", lambda: tmp_path / "projects"
        )
        # Isolate prompt resolution: hardcoded default layer, no overrides.
        monkeypatch.setattr("core.config.load_settings", lambda: {"llm_prompts": {}})

        self.service = ProjectService()
        self.service.create_project("t", "/fake/media.mp4", {"duration": 10.0})

        self.events: list[tuple] = []
        self.instance = MiloCutApi.__new__(MiloCutApi)
        self.instance._project = self.service
        self.instance._emit = lambda event, data=None: self.events.append(
            (event, data)
        )

    def install(
        self,
        *,
        segments: list[Segment],
        tracks: list[SubtitleTrack] | None = None,
        bindings: list[TrackBinding] | None = None,
        edits: list[EditDecision] | None = None,
    ) -> None:
        """Replace the active timeline's transcript layers / edits in one write."""
        tl = self.service.active_timeline
        self.service._current = self.service._current.model_copy(
            update={
                "timelines": [
                    tl.model_copy(
                        update={
                            "transcript": tl.transcript.model_copy(
                                update={
                                    "segments": segments,
                                    "tracks": tracks or [],
                                    "bindings": bindings or [],
                                }
                            ),
                            "edits": edits or [],
                        }
                    )
                ]
            }
        )


@pytest.fixture
def api(monkeypatch, tmp_path):
    return _Api(monkeypatch, tmp_path)


@pytest.fixture
def llm_configured(monkeypatch):
    monkeypatch.setattr(
        "core.llm_service.get_llm_config", lambda: _configured_llm()
    )


def _run_correction(api: _Api, payload: dict) -> TaskManager:
    """Seed + synchronously dispatch one llm_subtitle_correction task."""
    tm = TaskManager(lambda *a: None)
    api.instance._task_manager = tm
    api.instance._register_task_handlers()

    task_id = "task-corr-1"
    tm._tasks[task_id] = MiloTask(
        id=task_id, type=TaskType.LLM_SUBTITLE_CORRECTION, payload=payload
    )
    tm._execute_task(task_id, tm._tasks[task_id])
    return tm


def _bound_track(
    track_id: str,
    ext_segments: list[Segment],
    main_ids: list[str | None],
) -> tuple[SubtitleTrack, list[TrackBinding]]:
    """Build a track + bindings; ``None`` main id = leave that segment unbound."""
    track = SubtitleTrack(
        id=track_id, role="extension", name="Ext", language="en",
        segments=ext_segments,
    )
    bindings = [
        TrackBinding(
            id=f"bind-{i}",
            track_id=track_id,
            main_segment_id=main_id,
            extension_segment_id=seg.id,
        )
        for i, (seg, main_id) in enumerate(
            zip(ext_segments, main_ids, strict=True)
        )
        if main_id is not None
    ]
    return track, bindings


# ================================================================
# Track-path segment source (SPEC M2-1 ①②③)
# ================================================================


class TestTrackSegmentSource:
    def test_bound_to_deleted_main_skipped_others_kept(
        self, api, llm_configured, monkeypatch
    ):
        """1 deleted main seg: its BOUND track seg is skipped; the seg bound
        to a surviving main seg and the unbound seg both stay."""
        main = [_main_seg("seg_a", 1.0, "甲"), _main_seg("seg_b", 2.0, "乙")]
        ext = [
            _track_seg("trk_ext", 1.0, "A"),  # bound to deleted seg_a
            _track_seg("trk_ext", 2.0, "B"),  # bound to surviving seg_b
            _track_seg("trk_ext", 3.0, "C"),  # unbound
        ]
        track, bindings = _bound_track(
            "trk_ext", ext, main_ids=["seg_a", "seg_b", None]
        )
        api.install(
            segments=main,
            tracks=[track],
            bindings=bindings,
            edits=[_confirmed_delete("seg_a")],
        )

        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(captured),
        )
        tm = _run_correction(
            api, {"timeline_id": "default", "track_id": "trk_ext"}
        )

        assert tm._tasks["task-corr-1"].status.value == "completed"
        (call,) = captured
        received = [s["id"] for s in call["segments"]]
        # The deleted main seg's bound track segment never reaches the LLM.
        assert received == [ext[1].id, ext[2].id]

    def test_unbound_segments_survive_main_deletion(
        self, api, llm_configured, monkeypatch
    ):
        """A main-track deletion only propagates through bindings: with no
        binding pointing at the track segments, ALL of them stay in the
        source even though a main seg is confirmed-deleted."""
        main = [_main_seg("seg_a", 1.0, "甲"), _main_seg("seg_b", 2.0, "乙")]
        ext = [
            _track_seg("trk_ext", 1.0, "A"),
            _track_seg("trk_ext", 2.0, "B"),
        ]
        track, bindings = _bound_track("trk_ext", ext, main_ids=[None, None])
        api.install(
            segments=main,
            tracks=[track],
            bindings=bindings,
            edits=[_confirmed_delete("seg_a")],
        )

        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(captured),
        )
        _run_correction(api, {"timeline_id": "default", "track_id": "trk_ext"})

        (call,) = captured
        assert [s["id"] for s in call["segments"]] == [ext[0].id, ext[1].id]

    def test_partial_hints_not_collected_on_track_path(
        self, api, llm_configured, monkeypatch
    ):
        """④: hints are a main-track EditDecision concept -- a partial_delete
        analysis result must NOT surface as edit_hint on track segments."""
        from core.models import AnalysisResult

        main = [_main_seg("seg_a", 1.0, "甲")]
        ext = [_track_seg("trk_ext", 1.0, "A")]
        track, bindings = _bound_track("trk_ext", ext, main_ids=["seg_a"])
        api.install(
            segments=main, tracks=[track], bindings=bindings, edits=[]
        )
        # A partial_delete result targeting the MAIN segment (v2.2.0 hint).
        tl = api.service.active_timeline
        api.service._current = api.service._current.model_copy(
            update={
                "timelines": [
                    tl.model_copy(
                        update={
                            "analysis": tl.analysis.model_copy(
                                update={
                                    "results": [
                                        AnalysisResult(
                                            id="ar-pd",
                                            type="llm_smart_delete",
                                            segment_ids=["seg_a"],
                                            category="partial_delete",
                                            detail="句内含口误/重复，建议修正",
                                        )
                                    ]
                                }
                            )
                        }
                    )
                ]
            }
        )

        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(captured),
        )
        _run_correction(api, {"timeline_id": "default", "track_id": "trk_ext"})

        (call,) = captured
        assert len(call["segments"]) == 1
        assert "edit_hint" not in call["segments"][0]


# ================================================================
# Missing track -> task failed (SPEC M2-1 ① failure path)
# ================================================================


class TestTrackNotFound:
    def test_missing_track_fails_task(self, api, llm_configured, monkeypatch):
        called: list[dict] = []

        def must_not_run(segments, **kwargs):
            called.append({"segments": segments})
            return {"success": True, "data": {"corrections": [], "token_usage": {}}}

        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction", must_not_run
        )
        tm = _run_correction(
            api, {"timeline_id": "default", "track_id": "trk_missing"}
        )

        task = tm._tasks["task-corr-1"]
        assert task.status.value == "failed"
        assert "Track not found" in task.error
        assert "trk_missing" in task.error
        # The pipeline never runs for an unresolvable source.
        assert called == []


# ================================================================
# Default main-track regression (v3.0.3 equivalence, snapshot)
# ================================================================


class TestDefaultMainTrackSource:
    def test_default_payload_uses_main_subtitle_segments(
        self, api, llm_configured, monkeypatch
    ):
        """No track_id key: source = main subtitle segments minus
        confirmed-deleted ones (silence segs filtered, v3.0.3 snapshot)."""
        main = [
            _main_seg("seg_a", 1.0, "甲"),  # confirmed-deleted -> excluded
            _main_seg("seg_b", 2.0, "乙"),  # survives
            Segment(
                id="seg_sil", type=SegmentType.SILENCE,
                start=3.0, end=4.0, text="",
            ),  # silence -> excluded
        ]
        api.install(segments=main, edits=[_confirmed_delete("seg_a")])

        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(captured),
        )
        tm = _run_correction(api, {"timeline_id": "default"})

        assert tm._tasks["task-corr-1"].status.value == "completed"
        (call,) = captured
        assert [s["id"] for s in call["segments"]] == ["seg_b"]


# ================================================================
# Option B: store track_id detail key (P2-2 choice)
# ================================================================


class TestStoreTrackIdKey:
    def test_main_path_store_records_empty_track_id(
        self, api, llm_configured, monkeypatch
    ):
        """Option B: the main path threads track_id="" into store; the
        detail JSON carries the scope marker ("" = main track)."""
        main = [_main_seg("seg_a", 1.0, "甲")]
        api.install(segments=main, edits=[])

        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(),
        )
        tm = _run_correction(api, {"timeline_id": "default"})

        assert tm._tasks["task-corr-1"].status.value == "completed"
        results = [
            r
            for r in api.service.active_timeline.analysis.results
            if r.type == "llm_subtitle_correction"
        ]
        assert len(results) == 1
        detail = json.loads(results[0].detail)
        assert detail["track_id"] == ""
