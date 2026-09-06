"""v3.0.0 M1-3: SRT encoding fallback (utf-8-sig -> gb18030 -> latin-1).

parse_srt previously hard-coded utf-8-sig, so GB18030 Chinese SRT files
crashed on import even though validate_srt handled them.
"""

from __future__ import annotations

from core.subtitle_service import parse_srt, validate_srt

GB_SRT_TEXT = (
    "1\n"
    "00:00:01,000 --> 00:00:03,000\n"
    "大家好，今天讲一下\n\n"
    "2\n"
    "00:00:03,500 --> 00:00:06,000\n"
    "然后我们看下一部分\n"
)


def _write(path, encoding: str) -> str:
    path.write_text(GB_SRT_TEXT, encoding=encoding)
    return str(path)


class TestGb18030Fallback:
    def test_parse_srt_gb18030_no_mojo(self, tmp_path):
        srt = _write(tmp_path / "gb.srt", "gb18030")
        res = parse_srt(srt)
        assert res["success"]
        segs = res["data"]
        assert len(segs) == 2
        assert segs[0]["text"] == "大家好，今天讲一下"
        assert segs[1]["text"] == "然后我们看下一部分"

    def test_validate_srt_gb18030_still_works(self, tmp_path):
        srt = _write(tmp_path / "gb.srt", "gb18030")
        res = validate_srt(srt, video_duration=6.0)
        assert res["success"]
        assert res["data"]["error_count"] == 0

    def test_parse_srt_utf8_unchanged(self, tmp_path):
        srt = _write(tmp_path / "u8.srt", "utf-8-sig")
        res = parse_srt(srt)
        assert res["success"]
        assert res["data"][0]["id"] == "seg-0001"
        assert res["data"][0]["start"] == 1.0
