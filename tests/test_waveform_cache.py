"""v3.0.0 P4-3 M11-3: waveform peaks sidecar cache.

Contract:
- Sidecar ``<媒体名>.peaks.json`` = {version, media_signature:{size, mtime_ms}, peaks}.
- Signature hit -> load_waveform_cache returns the sidecar path (handler skips
  ffmpeg); size OR mtime change -> miss -> regenerate.
- Any corruption / unknown version / empty peaks -> miss (cache is a pure
  optimization, never a correctness gate).
- Media directory not writable -> write_waveform_cache returns None and the
  legacy project-dir waveform stays the source.
"""

from __future__ import annotations

import json
import os

import pytest

from core.ffmpeg_service import (
    load_waveform_cache,
    media_signature,
    peaks_sidecar_path,
    read_peaks_file,
    write_waveform_cache,
)
from core.project_service import ProjectService

PEAKS = [{"min": -0.5, "max": 0.5}, {"min": -0.2, "max": 0.9}]


@pytest.fixture
def media_file(tmp_path):
    p = tmp_path / "media.mp4"
    p.write_bytes(b"\x00" * 1024)
    return p


def _write_sidecar_raw(media_path, payload) -> None:
    with open(peaks_sidecar_path(str(media_path)), "w", encoding="utf-8") as f:
        json.dump(payload, f)


class TestMediaSignature:
    def test_signature_shape(self, media_file):
        sig = media_signature(str(media_file))
        assert sig["size"] == 1024
        assert isinstance(sig["mtime_ms"], int)

    def test_signature_changes_on_content_change(self, media_file):
        before = media_signature(str(media_file))
        media_file.write_bytes(b"\x01" * 2048)
        after = media_signature(str(media_file))
        assert before != after
        assert after["size"] == 2048


class TestCacheRoundTrip:
    def test_write_then_load_hit(self, media_file):
        assert write_waveform_cache(str(media_file), PEAKS) == str(
            peaks_sidecar_path(str(media_file))
        )
        assert load_waveform_cache(str(media_file)) == str(
            peaks_sidecar_path(str(media_file))
        )

    def test_miss_when_no_sidecar(self, media_file):
        assert load_waveform_cache(str(media_file)) is None

    def test_miss_on_size_change(self, media_file):
        write_waveform_cache(str(media_file), PEAKS)
        media_file.write_bytes(b"\x00" * 2048)  # same-ish mtime, new size
        assert load_waveform_cache(str(media_file)) is None

    def test_miss_on_mtime_change_same_size(self, media_file):
        write_waveform_cache(str(media_file), PEAKS)
        # Rewrite same byte count, bump mtime explicitly (double-factor guard).
        media_file.write_bytes(b"\x01" * 1024)
        st = media_file.stat()
        os.utime(media_file, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        assert load_waveform_cache(str(media_file)) is None

    def test_media_replacement_then_regenerate_hits_again(self, media_file):
        write_waveform_cache(str(media_file), PEAKS)
        media_file.write_bytes(b"\x02" * 4096)
        assert load_waveform_cache(str(media_file)) is None  # replaced -> miss
        write_waveform_cache(str(media_file), PEAKS)  # regenerate overwrites
        assert load_waveform_cache(str(media_file)) is not None

    def test_miss_on_corrupted_sidecar(self, media_file):
        sidecar = peaks_sidecar_path(str(media_file))
        sidecar.write_text("{not json", encoding="utf-8")
        assert load_waveform_cache(str(media_file)) is None

    def test_miss_on_unknown_version(self, media_file):
        _write_sidecar_raw(
            media_file,
            {"version": 99, "media_signature": media_signature(str(media_file)), "peaks": PEAKS},
        )
        assert load_waveform_cache(str(media_file)) is None

    def test_miss_on_empty_peaks(self, media_file):
        _write_sidecar_raw(
            media_file,
            {"version": 1, "media_signature": media_signature(str(media_file)), "peaks": []},
        )
        assert load_waveform_cache(str(media_file)) is None

    def test_miss_on_signature_mismatch_shape(self, media_file):
        _write_sidecar_raw(media_file, {"version": 1, "media_signature": {"size": 1}, "peaks": PEAKS})
        assert load_waveform_cache(str(media_file)) is None


class TestWriteFallbacks:
    def test_unwritable_media_dir_returns_none(self, media_file, tmp_path):
        # Media path inside a nonexistent directory -> stat/write both fail.
        bogus = tmp_path / "nope" / "media.mp4"
        assert write_waveform_cache(str(bogus), PEAKS) is None

    def test_read_peaks_file_shapes(self, tmp_path):
        f = tmp_path / "waveform.json"
        f.write_text(json.dumps(PEAKS), encoding="utf-8")
        assert read_peaks_file(str(f)) == PEAKS
        f.write_text("[]", encoding="utf-8")
        assert read_peaks_file(str(f)) is None
        f.write_text("{broken", encoding="utf-8")
        assert read_peaks_file(str(f)) is None


# ---------------------------------------------------------------------------
# Handler-level: cache hit skips the ffmpeg extraction (main.MiloCutApi)
# ---------------------------------------------------------------------------


class _StubTaskManager:
    def _update_progress(self, task_id, percent, message=""):
        pass


class _StubTask:
    id = "task-1"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    from core.media_server import MediaServer
    from main import MiloCutApi

    media = tmp_path / "long_video.mp4"
    media.write_bytes(b"\x00" * 4096)

    svc_project = tmp_path / "projects" / "w"
    svc_project.mkdir(parents=True)
    service = ProjectService()
    service.create_project("w", str(media), {"duration": 60.0})

    api_obj = MiloCutApi.__new__(MiloCutApi)
    api_obj._project = service
    api_obj._media_server = MediaServer()
    api_obj._task_manager = _StubTaskManager()
    return api_obj, media


class TestHandlerCacheSkipsFfmpeg:
    def test_second_run_hits_cache_without_ffmpeg(self, api, monkeypatch, tmp_path):
        api_obj, media = api

        calls = {"n": 0}

        def fake_generate(file_path, duration, output_path, buckets_per_second=100):
            calls["n"] += 1
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([{"min": -0.4, "max": 0.4}] * 10, f)
            return {"success": True, "data": {"path": output_path, "buckets": 10}}

        monkeypatch.setattr("main.generate_waveform", fake_generate)

        task = _StubTask()
        first = api_obj._handle_waveform_generation(task, None, None)
        assert calls["n"] == 1
        assert first.get("cached") is None  # miss -> real generation
        sidecar = str(peaks_sidecar_path(str(media)))
        assert api_obj._project.current.media.waveform_path == sidecar
        assert sidecar and os.path.exists(sidecar)

        # Second run: signature hit, ffmpeg extraction skipped entirely.
        second = api_obj._handle_waveform_generation(task, None, None)
        assert calls["n"] == 1
        assert second["cached"] is True
        assert api_obj._project.current.media.waveform_path == sidecar

    def test_media_replacement_regenerates(self, api, monkeypatch):
        api_obj, media = api

        calls = {"n": 0}

        def fake_generate(file_path, duration, output_path, buckets_per_second=100):
            calls["n"] += 1
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([{"min": -0.1, "max": 0.1}] * 5, f)
            return {"success": True, "data": {"path": output_path, "buckets": 5}}

        monkeypatch.setattr("main.generate_waveform", fake_generate)
        task = _StubTask()
        api_obj._handle_waveform_generation(task, None, None)
        assert calls["n"] == 1

        # User replaces the media at the same path -> signature miss.
        media.write_bytes(b"\x09" * 8192)
        api_obj._handle_waveform_generation(task, None, None)
        assert calls["n"] == 2
