"""Tests for export_service: VTT export and format helpers."""

from __future__ import annotations

import os

import pytest

from core.export_service import (
    _format_srt_time,
    _format_vtt_time,
    export_srt,
    export_vtt,
)


class TestFormatSrtTime:
    """Tests for _format_srt_time helper."""

    def test_zero(self):
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_seconds_only(self):
        assert _format_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _format_srt_time(65.25) == "00:01:05,250"

    def test_hours(self):
        assert _format_srt_time(3661.1) == "01:01:01,100"

    def test_negative_clamped(self):
        assert _format_srt_time(-1.0) == "00:00:00,000"

    def test_millis_rounding(self):
        # millis round to 1000 wraps to 0 via % 1000, seconds not carried
        assert _format_srt_time(1.9999) == "00:00:01,000"


class TestFormatVttTime:
    """Tests for _format_vtt_time helper."""

    def test_zero(self):
        assert _format_vtt_time(0.0) == "00:00:00.000"

    def test_seconds_only(self):
        assert _format_vtt_time(5.5) == "00:00:05.500"

    def test_minutes(self):
        assert _format_vtt_time(65.25) == "00:01:05.250"

    def test_hours(self):
        assert _format_vtt_time(3661.1) == "01:01:01.100"

    def test_negative_clamped(self):
        assert _format_vtt_time(-1.0) == "00:00:00.000"

    def test_uses_period_not_comma(self):
        result = _format_vtt_time(1.5)
        assert "." in result
        assert "," not in result


class TestExportSrt:
    """Tests for export_srt function."""

    def test_basic_export(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "Hello"},
            {"id": "s2", "type": "subtitle", "start": 4.0, "end": 6.0, "text": "World"},
            {"id": "s3", "type": "silence", "start": 3.0, "end": 4.0, "text": ""},
        ]
        output = str(tmp_path / "test.srt")
        result = export_srt(segments, [], output, media_duration=10.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert "1\n00:00:01,000 --> 00:00:03,000\nHello\n" in content
        assert "2\n00:00:04,000 --> 00:00:06,000\nWorld\n" in content

    def test_with_deletions(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "Keep"},
            {"id": "s2", "type": "subtitle", "start": 7.0, "end": 9.0, "text": "Also keep"},
        ]
        edits = [
            {"id": "e1", "start": 3.0, "end": 7.0, "action": "delete", "status": "confirmed"},
        ]
        output = str(tmp_path / "test.srt")
        result = export_srt(segments, edits, output, media_duration=10.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        # After deleting 3-7s, second subtitle should be remapped
        assert "Keep" in content
        assert "Also keep" in content

    def test_empty_segments(self, tmp_path):
        output = str(tmp_path / "empty.srt")
        result = export_srt([], [], output, media_duration=5.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert content == ""


class TestExportVtt:
    """Tests for export_vtt function."""

    def test_basic_export(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "Hello"},
            {"id": "s2", "type": "subtitle", "start": 4.0, "end": 6.0, "text": "World"},
            {"id": "s3", "type": "silence", "start": 3.0, "end": 4.0, "text": ""},
        ]
        output = str(tmp_path / "test.vtt")
        result = export_vtt(segments, [], output, media_duration=10.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert content.startswith("WEBVTT\n")
        assert "00:00:01.000 --> 00:00:03.000" in content
        assert "00:00:04.000 --> 00:00:06.000" in content
        assert "Hello" in content
        assert "World" in content

    def test_uses_period_separator(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.5, "end": 3.5, "text": "Test"},
        ]
        output = str(tmp_path / "test.vtt")
        result = export_vtt(segments, [], output, media_duration=5.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert "00:00:01.500 --> 00:00:03.500" in content
        assert "," not in content.split("WEBVTT\n\n")[1]

    def test_with_deletions(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "Keep me"},
            {"id": "s2", "type": "subtitle", "start": 7.0, "end": 9.0, "text": "Keep me too"},
        ]
        edits = [
            {"id": "e1", "start": 3.0, "end": 7.0, "action": "delete", "status": "confirmed"},
        ]
        output = str(tmp_path / "test.vtt")
        result = export_vtt(segments, edits, output, media_duration=10.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert content.startswith("WEBVTT\n")
        assert "Keep me" in content
        assert "Keep me too" in content

    def test_empty_segments(self, tmp_path):
        output = str(tmp_path / "empty.vtt")
        result = export_vtt([], [], output, media_duration=5.0)
        assert result["success"]
        content = open(output, encoding="utf-8").read()
        assert content.startswith("WEBVTT\n")
        # Only header, no cues
        assert content.strip() == "WEBVTT"

    def test_segment_count_in_result(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "A"},
            {"id": "s2", "type": "subtitle", "start": 4.0, "end": 6.0, "text": "B"},
        ]
        output = str(tmp_path / "test.vtt")
        result = export_vtt(segments, [], output, media_duration=10.0)
        assert result["success"]
        assert result["data"]["segment_count"] == 2

    def test_subtitle_lost_by_deletion(self, tmp_path):
        segments = [
            {"id": "s1", "type": "subtitle", "start": 1.0, "end": 3.0, "text": "Keep"},
            {"id": "s2", "type": "subtitle", "start": 4.0, "end": 6.0, "text": "Deleted"},
        ]
        edits = [
            {"id": "e1", "start": 3.5, "end": 6.5, "action": "delete", "status": "confirmed"},
        ]
        output = str(tmp_path / "test.vtt")
        result = export_vtt(segments, edits, output, media_duration=10.0)
        assert result["success"]
        assert result["data"]["segment_count"] == 1
        content = open(output, encoding="utf-8").read()
        assert "Keep" in content
        assert "Deleted" not in content
