"""v3.0.4 P1-5 M1-1/M1-5: start_translation expose + _handle_translation wiring.

Locks (SPEC M1-1 validation order, M1-5 five-step flow / failure table):
- start_translation validation branches: LLM not configured / no project /
  invalid language / empty main track / duplicate same-language translation
  track (guidance copy) / happy path creating the llm_translation task.
- Handler registration + synchronous TaskManager dispatch (mock LLM): the
  bound track lands via create_translation_track and the task completes
  with a project dump in the result.
- Completion-time timeline pinning: timeline switched during the run ->
  task FAILED with the return-to-original-timeline guidance and ZERO
  writes (M0-3 constraint 4 boundary case).
- Partial mid-run deletion: surviving items persist, uncovered_ids ride
  the llm:translation_completed payload (never silent).
- {{target_language}} final replacement injects the English display name
  and leaves no {{ behind; a system_override carrying some OTHER
  {{placeholder}} fails fast (zero writes, pipeline never called).

Mock style follows tests/test_analysis_handlers.py (MiloCutApi.__new__ +
real ProjectService) and tests/test_task_cancel.py (synchronous
``TaskManager._execute_task`` driving).
"""

from __future__ import annotations

import pytest

from core.events import LLM_TRANSLATION_COMPLETED, TASK_COMPLETED, TASK_FAILED
from core.models import (
    AnalysisData,
    LlmConfig,
    LlmProvider,
    MiloTask,
    Segment,
    SegmentType,
    SubtitleTrack,
    TaskType,
    Timeline,
    TranscriptData,
)
from core.project_service import ProjectService
from core.task_manager import TaskManager
from main import _TRANSLATION_LANGUAGES, MiloCutApi

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


def _unconfigured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.CUSTOM,
        base_url="",
        api_key="",
        model="",
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


def _install_translation_track(svc: ProjectService, language: str) -> None:
    """Simulate an existing same-language translation track (expose branch 5)."""
    tl = svc.active_timeline
    track = SubtitleTrack(
        id="trk_existing",
        role="translation",
        name="English",
        language=language,
        segments=[],
    )
    svc._current = svc._current.model_copy(
        update={
            "timelines": [
                tl.model_copy(
                    update={
                        "transcript": tl.transcript.model_copy(
                            update={"tracks": [*tl.transcript.tracks, track]}
                        )
                    }
                )
            ]
        }
    )


def _install_prompt_override(svc: ProjectService, prompts: dict) -> None:
    """Install timeline-level llm_prompts (system_override path)."""
    tl = svc.active_timeline
    svc._current = svc._current.model_copy(
        update={
            "timelines": [tl.model_copy(update={"llm_prompts": prompts})]
        }
    )


def _perfect_pipeline(captured: list[dict] | None = None):
    """Mock analyze_subtitle_translation echoing every input id back."""

    def fake(segments, target_language, *, config=None, cancel_event=None,
             progress_cb=None, system_prompt=None):
        if captured is not None:
            captured.append(
                {
                    "segments": segments,
                    "target_language": target_language,
                    "system_prompt": system_prompt,
                }
            )
        return {
            "success": True,
            "data": {
                "translations": [
                    {"segment_id": s["id"], "translated_text": f"EN[{s['id']}]"}
                    for s in segments
                ],
                "token_usage": dict(_TOKEN_USAGE),
                "ledger": dict(_LEDGER),
            },
        }

    return fake


def _seed_translation_task(tm: TaskManager, payload: dict) -> str:
    """Pre-populate _tasks the way the queue dispatcher would (sync drive)."""
    task_id = "task-tr-1"
    tm._tasks[task_id] = MiloTask(
        id=task_id, type=TaskType.LLM_TRANSLATION, payload=payload
    )
    return task_id


def _translation_event(events: list[tuple]) -> tuple | None:
    for item in events:
        if item[0] == LLM_TRANSLATION_COMPLETED:
            return item
    return None


def _all_tracks(svc: ProjectService) -> list[SubtitleTrack]:
    return [
        t
        for tl in svc.current.timelines
        for t in tl.transcript.tracks
    ]


# ================================================================
# Fixtures
# ================================================================


class _Api:
    """MiloCutApi shell: real ProjectService + captured events."""

    def __init__(self, monkeypatch, tmp_path):
        monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
        # Redirect the bound import inside project_service too, so
        # create_project writes into the tmp sandbox.
        monkeypatch.setattr(
            "core.project_service.get_projects_dir", lambda: tmp_path / "projects"
        )
        # Isolate prompt resolution: hardcoded default layer, no overrides.
        monkeypatch.setattr("core.config.load_settings", lambda: {"llm_prompts": {}})

        self.service = ProjectService()
        self.service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
        _install_main_segments(self.service, _main_segments(3))

        self.events: list[tuple] = []
        self.instance = MiloCutApi.__new__(MiloCutApi)
        self.instance._project = self.service
        self.instance._emit = lambda event, data=None: self.events.append(
            (event, data)
        )


@pytest.fixture
def api(monkeypatch, tmp_path):
    return _Api(monkeypatch, tmp_path)


@pytest.fixture
def llm_configured(monkeypatch):
    monkeypatch.setattr(
        "core.llm_service.get_llm_config", lambda: _configured_llm()
    )


@pytest.fixture
def llm_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "core.llm_service.get_llm_config", lambda: _unconfigured_llm()
    )


@pytest.fixture
def no_worker(monkeypatch):
    """Keep create_task from auto-dispatching a worker thread (expose tests)."""
    monkeypatch.setattr(
        "core.task_manager.TaskManager._ensure_worker", lambda self: None
    )


# ================================================================
# start_translation validation branches (SPEC M1-1 order)
# ================================================================


class TestStartTranslationValidation:
    def test_llm_not_configured(self, api, llm_unconfigured, no_worker):
        api.instance._task_manager = TaskManager(lambda *a: None)
        result = api.instance.start_translation(target_language="en")
        assert result == {"success": False, "error": "LLM not configured"}

    def test_no_project_open(self, api, llm_configured):
        api.service._current = None
        result = api.instance.start_translation(target_language="en")
        assert result == {"success": False, "error": "No project open"}

    def test_invalid_language_rejected(self, api, llm_configured, no_worker):
        api.instance._task_manager = TaskManager(lambda *a: None)
        for bad in ("", "xx", "EN"):
            result = api.instance.start_translation(target_language=bad)
            assert result["success"] is False
            assert "Unsupported target language" in result["error"]

    def test_empty_main_track_rejected(self, api, llm_configured, no_worker):
        _install_main_segments(api.service, [])
        api.instance._task_manager = TaskManager(lambda *a: None)
        result = api.instance.start_translation(target_language="en")
        assert result["success"] is False
        assert result["error"] == "No subtitle segments to translate"

    def test_duplicate_language_rejected_with_guidance(
        self, api, llm_configured, no_worker
    ):
        _install_translation_track(api.service, "en")
        api.instance._task_manager = TaskManager(lambda *a: None)
        result = api.instance.start_translation(target_language="en")
        assert result["success"] is False
        assert "可清空或删除该轨后重试" in result["error"]

    def test_happy_path_creates_task_with_payload(
        self, api, llm_configured, no_worker, monkeypatch
    ):
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation", _perfect_pipeline()
        )
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm

        result = api.instance.start_translation(
            target_language="en", track_name="My English"
        )

        assert result["success"] is True
        task_id = result["data"]["id"]
        assert tm._tasks[task_id].type == TaskType.LLM_TRANSLATION
        assert tm._tasks[task_id].payload == {
            "timeline_id": "default",
            "target_language": "en",
            "track_name": "My English",
        }


# ================================================================
# Handler registration + synchronous dispatch (mock LLM)
# ================================================================


class TestHandlerDispatch:
    def test_handler_registered_for_task_type(self, api):
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm
        api.instance._register_task_handlers()
        assert tm._handlers[TaskType.LLM_TRANSLATION] == api.instance._handle_translation

    def test_dispatch_completes_and_writes_track(self, api, llm_configured, monkeypatch):
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation", _perfect_pipeline()
        )
        tm = TaskManager(lambda event, data=None: api.events.append((event, data)))
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "en", "track_name": ""}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        task = tm._tasks[task_id]
        assert task.status.value == "completed"
        # create_translation_track was called: a bound translation track
        # with 1:1 zero-offset bindings now lives in the project.
        (track,) = _all_tracks(api.service)
        assert track.role == "translation"
        assert track.language == "en"
        assert track.name == "English"  # default track_name = display name
        assert len(track.segments) == 3
        bindings = api.service.active_timeline.transcript.bindings
        assert len(bindings) == 3
        assert all(b.start_offset == 0.0 and b.end_offset == 0.0 for b in bindings)
        # Completion event carries the write report + ledger.
        event = _translation_event(api.events)
        assert event is not None
        payload = event[1]
        assert payload["track_id"] == track.id
        assert payload["track_name"] == "English"
        assert payload["language"] == "en"
        assert payload["written_count"] == 3
        assert payload["target_count"] == 3
        assert payload["uncovered_ids"] == []
        assert payload["ledger"] == _LEDGER
        # Token usage follows the correction emit convention.
        assert ("llm:token_usage", _TOKEN_USAGE) in api.events
        # task:completed envelope: result keeps the project dump...
        assert "project" in task.result
        assert task.result["written_count"] == 3
        # ...while the event carries only result_meta (stripped upstream).
        completed = [e for e in api.events if e[0] == TASK_COMPLETED]
        assert completed and "project" not in completed[0][1]["result"]

    def test_pipeline_failure_fails_task_zero_writes(
        self, api, llm_configured, monkeypatch
    ):
        def failing(segments, target_language, **kwargs):
            return {"success": False, "error": "Translation incomplete: boom"}

        monkeypatch.setattr("core.llm_service.analyze_subtitle_translation", failing)
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "en"}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        task = tm._tasks[task_id]
        assert task.status.value == "failed"
        assert "boom" in task.error
        assert _all_tracks(api.service) == []  # zero writes
        assert _translation_event(api.events) is None


# ================================================================
# Failure semantics: mid-run deletion / timeline switch (SPEC M1-5 table)
# ================================================================


class TestMidRunChanges:
    def test_uncovered_ids_ride_completion_event(self, api, llm_configured, monkeypatch):
        deleted_id = _main_segments(3)[0].id

        def deleting_pipeline(segments, target_language, **kwargs):
            # Simulate the user deleting a main-track segment while the
            # 1-3 minute task ran: the handler's snapshot is unaffected,
            # the CURRENT main track is what create_translation_track
            # reconciles against.
            svc = api.service
            tl = svc.active_timeline
            remaining = [s for s in tl.transcript.segments if s.id != deleted_id]
            svc._current = svc._current.model_copy(
                update={
                    "timelines": [
                        tl.model_copy(
                            update={
                                "transcript": tl.transcript.model_copy(
                                    update={"segments": remaining}
                                )
                            }
                        )
                    ]
                }
            )
            return {
                "success": True,
                "data": {
                    "translations": [
                        {"segment_id": s["id"], "translated_text": f"EN[{s['id']}]"}
                        for s in segments
                    ],
                    "token_usage": dict(_TOKEN_USAGE),
                    "ledger": dict(_LEDGER),
                },
            }

        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation", deleting_pipeline
        )
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "en"}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        # Surviving pairs persist; the vanished id is reported, not silent.
        assert tm._tasks[task_id].status.value == "completed"
        (track,) = _all_tracks(api.service)
        assert len(track.segments) == 2
        payload = _translation_event(api.events)[1]
        assert payload["written_count"] == 2
        assert payload["target_count"] == 3
        assert payload["uncovered_ids"] == [deleted_id]

    def test_timeline_switch_fails_zero_writes(self, api, llm_configured, monkeypatch):
        def switching_pipeline(segments, target_language, **kwargs):
            # Simulate the user switching to another timeline mid-run.
            svc = api.service
            second = Timeline(
                id="tl-2",
                label="Second",
                source="manual",
                transcript=TranscriptData(),
                analysis=AnalysisData(),
                edits=[],
            )
            svc._current = svc._current.model_copy(
                update={
                    "timelines": [*svc._current.timelines, second],
                    "active_timeline_id": "tl-2",
                }
            )
            return {
                "success": True,
                "data": {
                    "translations": [
                        {"segment_id": s["id"], "translated_text": f"EN[{s['id']}]"}
                        for s in segments
                    ],
                    "token_usage": dict(_TOKEN_USAGE),
                    "ledger": dict(_LEDGER),
                },
            }

        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation", switching_pipeline
        )
        tm = TaskManager(lambda event, data=None: api.events.append((event, data)))
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "en"}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        task = tm._tasks[task_id]
        assert task.status.value == "failed"
        assert "回到原时间轴" in task.error
        assert "翻译期间已切换时间轴" in task.error
        # Zero writes: no translation track on either timeline.
        assert _all_tracks(api.service) == []
        assert api.service.active_timeline.transcript.bindings == []
        # No completion event for a discarded result.
        assert _translation_event(api.events) is None
        failed = [e for e in api.events if e[0] == TASK_FAILED]
        assert failed and "回到原时间轴" in failed[0][1]["error"]


# ================================================================
# Prompt final replacement (SPEC M1-3, hosted here per PLAN micro-ruling)
# ================================================================


class TestPromptFinalReplacement:
    def test_display_name_injected_no_placeholder_left(
        self, api, llm_configured, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation",
            _perfect_pipeline(captured),
        )
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "ja"}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        assert tm._tasks[task_id].status.value == "completed"
        (call,) = captured
        # English display name injected; nothing left to substitute.
        assert "Japanese" in call["system_prompt"]
        assert "{{target_language}}" not in call["system_prompt"]
        assert "{{" not in call["system_prompt"]
        # The service-level target_language parameter is the raw code
        # (it never enters the prompt -- system_prompt carries the name).
        assert call["target_language"] == "ja"

    def test_residual_placeholder_fails_fast_zero_writes(
        self, api, llm_configured, monkeypatch
    ):
        # A user system_override carrying some OTHER {{placeholder}}: the
        # {{target_language}} replace cannot fix it, so the handler must
        # fail fast instead of silently degrading the prompt.
        _install_prompt_override(
            api.service,
            {"translation": {"system_override": "Translate into {{target_lang}} now."}},
        )
        called: list[dict] = []

        def must_not_run(segments, target_language, **kwargs):
            called.append({"segments": segments})
            return {"success": True, "data": {"translations": [], "token_usage": {}, "ledger": {}}}

        monkeypatch.setattr(
            "core.llm_service.analyze_subtitle_translation", must_not_run
        )
        tm = TaskManager(lambda *a: None)
        api.instance._task_manager = tm
        api.instance._register_task_handlers()

        task_id = _seed_translation_task(
            tm, {"timeline_id": "default", "target_language": "en"}
        )
        tm._execute_task(task_id, tm._tasks[task_id])

        task = tm._tasks[task_id]
        assert task.status.value == "failed"
        assert "placeholder" in task.error
        # Fail-fast happens BEFORE the pipeline and before any write.
        assert called == []
        assert _all_tracks(api.service) == []
        assert _translation_event(api.events) is None


# ================================================================
# Language constant sanity (single source for expose + handler)
# ================================================================


class TestLanguageCatalog:
    def test_catalog_matches_spec_list(self):
        assert set(_TRANSLATION_LANGUAGES) == {
            "en", "ja", "ko", "zh-CN", "zh-TW", "fr", "de", "es", "ru",
        }
        assert _TRANSLATION_LANGUAGES["en"] == "English"
        assert _TRANSLATION_LANGUAGES["zh-CN"] == "Simplified Chinese"
