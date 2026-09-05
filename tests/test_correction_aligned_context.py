"""v3.0.4 P2-6 M2-5 (R2.5): aligned main-track context on the track path.

Locks (SPEC M2-5 / PLAN P2-6):
- ``_build_structured_user_message`` forwards an optional per-segment
  ``aligned_main_text`` row (self-describing field; the edit_hint channel
  is NOT reused -- its semantics stay anchored to intra-sentence slips,
  architect pre-ruling 1).
- On the track correction path, a BOUND track segment whose main partner
  is alive receives ``aligned_main_text`` = the main partner's text
  (confirmed-deleted partners never reach here -- their bound segments
  are skipped upstream, P2-2).
- Unbound track segments degrade automatically: no ``aligned_main_text``,
  still in the source, task completes normally.
- The main-track path NEVER injects ``aligned_main_text`` (even when the
  timeline carries tracks + bindings).

Mock style follows tests/test_correction_track_source.py (P2-2):
MiloCutApi.__new__ + real ProjectService + synchronous
``TaskManager._execute_task`` driving + captured ``analyze_subtitle_correction``.
"""

from __future__ import annotations

import json

import pytest

from core.llm_service import _build_structured_user_message
from core.models import (
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
    ) -> None:
        """Replace the active timeline's transcript layers in one write."""
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
                            )
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
# 1. Builder unit: aligned_main_text forwarding (SPEC M2-5)
# ================================================================


class TestBuilderForwardsAlignedMainText:
    def test_forwarded_when_present_absent_when_missing(self):
        """One payload, one bound-style segment and one plain segment: the
        aligned row is forwarded verbatim for the former and never appears
        for the latter (2 assertions, self-describing field name)."""
        message = _build_structured_user_message(
            [
                {
                    "id": "seg_a",
                    "text": "A",
                    "start": 0.0,
                    "end": 1.0,
                    "aligned_main_text": "主轨甲",
                },
                {"id": "seg_b", "text": "B", "start": 1.0, "end": 2.0},
            ]
        )
        by_id = {s["id"]: s for s in json.loads(message)["segments"]}
        assert by_id["seg_a"]["aligned_main_text"] == "主轨甲"
        assert "aligned_main_text" not in by_id["seg_b"]


# ================================================================
# 2. Track path: bound segment carries the main partner's text
# ================================================================


class TestTrackPathAlignedContext:
    def test_bound_segment_carries_main_text(
        self, api, llm_configured, monkeypatch
    ):
        """A track segment bound to a surviving main segment reaches the
        correction pipeline with aligned_main_text = that main segment's
        exact text."""
        main = [
            _main_seg("seg_a", 1.0, "主轨甲的完整文本"),
            _main_seg("seg_b", 2.0, "主轨乙的完整文本"),
        ]
        ext = [
            _track_seg("trk_ext", 1.0, "A"),  # bound to seg_a
            _track_seg("trk_ext", 2.0, "B"),  # bound to seg_b
        ]
        track, bindings = _bound_track(
            "trk_ext", ext, main_ids=["seg_a", "seg_b"]
        )
        api.install(segments=main, tracks=[track], bindings=bindings)

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
        by_id = {s["id"]: s for s in call["segments"]}
        assert by_id[ext[0].id]["aligned_main_text"] == "主轨甲的完整文本"
        assert by_id[ext[1].id]["aligned_main_text"] == "主轨乙的完整文本"


# ================================================================
# 3. Track path: unbound segment degrades (no context, still sourced)
# ================================================================


class TestUnboundSegmentDegradation:
    def test_unbound_segment_no_context_still_sourced(
        self, api, llm_configured, monkeypatch
    ):
        """No binding -> no aligned_main_text; the segment still enters the
        pipeline source and the task completes with results (SPEC M2-5
        acceptance: unbound segments return results normally)."""
        main = [_main_seg("seg_a", 1.0, "主轨甲")]
        ext = [_track_seg("trk_ext", 1.0, "A")]  # unbound
        track, bindings = _bound_track("trk_ext", ext, main_ids=[None])
        api.install(segments=main, tracks=[track], bindings=bindings)

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
        assert [s["id"] for s in call["segments"]] == [ext[0].id]
        assert "aligned_main_text" not in call["segments"][0]


# ================================================================
# 4. Main-track regression: aligned_main_text never injected
# ================================================================


class TestMainPathRegression:
    def test_main_path_segments_never_carry_aligned_main_text(
        self, api, llm_configured, monkeypatch
    ):
        """Default (no track_id) path: the main-track segment list never
        contains aligned_main_text, even though the timeline carries an
        extension track + bindings that could have leaked in."""
        main = [_main_seg("seg_a", 1.0, "甲"), _main_seg("seg_b", 2.0, "乙")]
        ext = [_track_seg("trk_ext", 1.0, "A")]
        track, bindings = _bound_track("trk_ext", ext, main_ids=["seg_a"])
        api.install(segments=main, tracks=[track], bindings=bindings)

        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_correction",
            _correction_pipeline(captured),
        )
        tm = _run_correction(api, {"timeline_id": "default"})

        assert tm._tasks["task-corr-1"].status.value == "completed"
        (call,) = captured
        assert [s["id"] for s in call["segments"]] == ["seg_a", "seg_b"]
        assert all("aligned_main_text" not in s for s in call["segments"])
