"""v3.0.0 M1-1: transcription keeps ASR words (no SRT round-trip).

The auto-saved SRT is an archive deliverable only; ``_handle_transcription``
must not import it back into the project, so words/speaker survive and
segment ids keep the ASR ``seg_{start:.3f}`` format.
"""

from __future__ import annotations

import json

import pytest

from core.models import Project
from main import MiloCutApi

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _asr_result() -> dict:
    """Mock ASR output shaped like core.asr_service responses (whisper链路)."""
    return {
        "success": True,
        "data": {
            "language": "zh",
            "word_count": 6,
            "segments": [
                {
                    "id": "seg_1.000",
                    "type": "subtitle",
                    "start": 1.0,
                    "end": 3.0,
                    "text": "大家好今天讲一下",
                    "speaker": "SPEAKER_00",
                    "words": [
                        {"word": "大家", "start": 1.0, "end": 1.4},
                        {"word": "好", "start": 1.4, "end": 1.6},
                        {"word": "今天", "start": 1.7, "end": 2.2},
                        {"word": "讲", "start": 2.3, "end": 2.6},
                        {"word": "一下", "start": 2.6, "end": 3.0},
                    ],
                },
                {
                    "id": "seg_3.500",
                    "type": "subtitle",
                    "start": 3.5,
                    "end": 6.0,
                    "text": "然后我们看下一部分",
                    "speaker": "SPEAKER_00",
                    "words": [
                        {"word": "然后", "start": 3.5, "end": 3.9},
                        {"word": "我们", "start": 4.0, "end": 4.3},
                        {"word": "看", "start": 4.4, "end": 4.6},
                        {"word": "下一部分", "start": 4.7, "end": 6.0},
                    ],
                },
            ],
        },
    }


@pytest.fixture
def api(monkeypatch, tmp_path):
    """MiloCutApi with a real ProjectService backed by tmp dirs."""
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    from core.project_service import ProjectService

    api = MiloCutApi.__new__(MiloCutApi)
    api._project = ProjectService()
    import queue

    api._event_queue = queue.Queue()
    api._plugin_manager = object()  # mocked ASR never touches it
    api._project.create_project(
        "t", "/fake/media.mp4", {"duration": 10.0, "format": "mp4"}
    )

    # Mock the whisper chain (imported lazily inside the handler).
    monkeypatch.setattr(
        "core.asr_service.transcribe_with_whisper",
        lambda **kwargs: _asr_result(),
    )
    # Auto SRT export resolves ffmpeg via _find_ffmpeg; stub it out.
    monkeypatch.setattr("core.ffmpeg_service._find_ffmpeg", lambda: "ffmpeg")
    return api


def _make_task(payload: dict):
    from core.models import MiloTask, TaskType

    return MiloTask(id="task-t", type=TaskType.TRANSCRIPTION, payload=payload)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranscriptionKeepsWords:
    def test_transcription_keeps_words(self, api, tmp_path):
        """转写落库后 words 非空、id 保持 ASR 格式、engine/language 正确。"""
        result = api._handle_transcription(_make_task({"engine": "faster-whisper"}), None, lambda *a, **k: None)

        assert result["segment_count"] == 2
        assert result["srt_path"]  # archive SRT still exported
        assert (tmp_path / "transcripts").exists()

        project = api._project.current
        segs = project.timelines[0].transcript.segments
        assert len(segs) == 2
        first = segs[0]
        # words survive
        assert len(first.words) == 5
        assert first.words[0].word == "大家"
        # speaker survives
        assert first.speaker == "SPEAKER_00"
        # ASR-format ids are kept (no seg-0001 renumbering)
        assert segs[0].id == "seg_1.000"
        assert segs[1].id == "seg_3.500"
        # transcript-level metadata recorded
        assert project.timelines[0].transcript.engine == "faster-whisper"
        assert project.timelines[0].transcript.language == "zh"

    def test_transcribed_project_json_has_words(self, api, tmp_path):
        """落盘的 project.json 中 words 同样保留（持久化层面验证）。"""
        api._handle_transcription(_make_task({}), None, lambda *a, **k: None)
        api._project.save_project()  # normally triggered by PROJECT_DIRTY via UI
        path = tmp_path / "projects" / "t" / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        segs = data["timelines"][0]["transcript"]["segments"]
        assert segs[0]["words"], "words must be persisted in project.json"
        assert all("start" in w and "end" in w for w in segs[0]["words"])


class TestManualSrtImportUnchanged:
    def test_manual_srt_import_unchanged(self, api):
        """手动 import_srt 路径行为不变（id 顺序号语义保留）。"""
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "1\n00:00:01,000 --> 00:00:03,000\n手动导入的一行\n\n"
                "2\n00:00:03,500 --> 00:00:06,000\n第二行内容\n"
            )
            srt = f.name

        res = api.import_srt(srt)
        assert res["success"]
        segs = api._project.current.timelines[0].transcript.segments
        assert [s.id for s in segs] == ["seg-0001", "seg-0002"]
        assert segs[0].text == "手动导入的一行"
        assert segs[0].words == []


class TestUpdateTranscriptMeta:
    def test_meta_update_keeps_segments(self, api):
        """update_transcript_meta 只改元数据，segments 原样保留。"""
        res = api._handle_transcription(_make_task({}), None, lambda *a, **k: None)
        before = Project.model_validate(res["project"])
        segs_before = before.timelines[0].transcript.segments

        res2 = api._project.update_transcript_meta(engine="qwen3-asr")
        assert res2["success"]
        after = api._project.current
        assert after.timelines[0].transcript.engine == "qwen3-asr"
        assert after.timelines[0].transcript.segments == segs_before
