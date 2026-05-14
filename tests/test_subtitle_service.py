"""Tests for core.subtitle_service."""

from core.subtitle_service import parse_srt, validate_srt


class TestParseSrt:
    def test_basic_parse(self, srt_file):
        result = parse_srt(srt_file)
        assert result["success"] is True
        assert len(result["data"]) == 3
        assert result["data"][0]["text"] == "Hello world"
        assert result["data"][0]["start"] == 1.0
        assert result["data"][0]["end"] == 5.0

    def test_file_not_found(self):
        result = parse_srt("/nonexistent/file.srt")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_wrong_extension(self, tmp_dir):
        path = tmp_dir / "test.txt"
        path.write_text("content", encoding="utf-8")
        result = parse_srt(str(path))
        assert result["success"] is False
        assert "unsupported" in result["error"].lower()

    def test_chinese_content(self, tmp_dir):
        content = """1
00:00:01,000 --> 00:00:05,000
你好世界

2
00:00:05,500 --> 00:00:10,000
这是一个测试
"""
        path = tmp_dir / "cn.srt"
        path.write_text(content, encoding="utf-8")
        result = parse_srt(str(path))
        assert result["success"] is True
        assert result["data"][0]["text"] == "你好世界"

    def test_utf8_bom(self, tmp_dir):
        content = "1\n00:00:01,000 --> 00:00:05,000\nBOM test\n"
        path = tmp_dir / "bom.srt"
        path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        result = parse_srt(str(path))
        assert result["success"] is True

    def test_multiline_text(self, tmp_dir):
        content = """1
00:00:01,000 --> 00:00:05,000
Line 1
Line 2
Line 3
"""
        path = tmp_dir / "multi.srt"
        path.write_text(content, encoding="utf-8")
        result = parse_srt(str(path))
        assert result["success"] is True
        assert "Line 1\nLine 2\nLine 3" == result["data"][0]["text"]

    def test_segment_ids(self, srt_file):
        result = parse_srt(srt_file)
        assert result["data"][0]["id"] == "seg-0001"
        assert result["data"][1]["id"] == "seg-0002"


class TestValidateSrt:
    def test_valid_file(self, srt_file):
        result = validate_srt(srt_file)
        assert result["success"] is True
        assert result["data"]["error_count"] == 0

    def test_file_not_found(self):
        result = validate_srt("/nonexistent/file.srt")
        assert result["success"] is False

    def test_index_gap(self, tmp_dir):
        content = """1
00:00:01,000 --> 00:00:05,000
First

3
00:00:05,500 --> 00:00:10,000
Third (gap)
"""
        path = tmp_dir / "gap.srt"
        path.write_text(content, encoding="utf-8")
        result = validate_srt(str(path))
        assert result["success"] is True
        assert result["data"]["warning_count"] > 0

    def test_overlap_detection(self, tmp_dir):
        content = """1
00:00:01,000 --> 00:00:10,000
First

2
00:00:05,000 --> 00:00:15,000
Overlapping
"""
        path = tmp_dir / "overlap.srt"
        path.write_text(content, encoding="utf-8")
        result = validate_srt(str(path))
        assert result["success"] is True
        assert result["data"]["warning_count"] > 0
        assert any("overlap" in i["message"].lower() for i in result["data"]["issues"])

    def test_start_after_end(self, tmp_dir):
        content = """1
00:00:10,000 --> 00:00:05,000
Bad timestamps
"""
        path = tmp_dir / "bad_ts.srt"
        path.write_text(content, encoding="utf-8")
        result = validate_srt(str(path))
        assert result["success"] is True
        assert result["data"]["error_count"] > 0

    def test_duration_mismatch(self, srt_file):
        # SRT ends at 15s, video claims 60s -> >10% mismatch
        result = validate_srt(srt_file, video_duration=60.0)
        assert result["success"] is True
        assert result["data"]["warning_count"] > 0
        assert any("duration" in i["message"].lower() for i in result["data"]["issues"])

    def test_duration_within_tolerance(self, srt_file):
        # SRT ends at 15s, video is 16s -> within 10%
        result = validate_srt(srt_file, video_duration=16.0)
        duration_warnings = [
            i for i in result["data"]["issues"]
            if "duration" in i["message"].lower()
        ]
        assert len(duration_warnings) == 0

    def test_gb18030_encoding(self, tmp_dir):
        content = "1\n00:00:01,000 --> 00:00:05,000\n测试中文\n"
        path = tmp_dir / "gb.srt"
        path.write_bytes(content.encode("gb18030"))
        result = validate_srt(str(path))
        assert result["success"] is True
