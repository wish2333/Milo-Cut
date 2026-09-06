"""Fabricate word-level timestamps for smoke testing (no ASR run needed).

SRT import cannot carry words (format ceiling, PRD D1.4) -- words only come
from ASR. This script injects synthetic per-token words into an existing
project.json so word-dependent features (M1-4 snap-to-word split, M11-1
hover word highlight) can be smoke-tested without a transcription run.

Tokenization: CJK characters become one word each, latin/digit runs stay a
single word; timestamps are distributed proportionally to token length
across the segment duration (the same "宁可近似、绝不越界" spirit -- this
is test data, not ASR ground truth).

Usage:
    uv run python scripts/fabricate_words.py data/projects/<name>/project.json

Run while the app is CLOSED (the backend loads project.json on open);
reopen the project afterwards.
"""
import json
import re
import sys
from pathlib import Path

# CJK char = one token; latin/digit runs = one token; drop whitespace.
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff\u3400-\u4dbf]|[^\sA-Za-z0-9\u4e00-\u9fff\u3400-\u4dbf]")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def fabricate(project_path: str, only_missing: bool = False) -> None:
    path = Path(project_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    seg_count = 0
    word_count = 0
    for timeline in data.get("timelines", []):
        for seg in timeline.get("transcript", {}).get("segments", []):
            if seg.get("type") != "subtitle":
                continue
            if only_missing and seg.get("words"):
                continue
            tokens = tokenize(seg.get("text") or "")
            if not tokens:
                continue
            total_len = sum(len(t) for t in tokens)
            start = float(seg["start"])
            end = float(seg["end"])
            duration = max(end - start, 0.001)
            words = []
            cursor = start
            for token in tokens:
                span = len(token) / total_len * duration
                words.append({
                    "word": token,
                    "start": round(cursor, 3),
                    "end": round(min(cursor + span, end), 3),
                    "confidence": 1.0,
                })
                cursor += span
            seg["words"] = words
            seg_count += 1
            word_count += len(words)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"fabricated words: {seg_count} segments, {word_count} words -> {path}")


def _main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    fabricate(sys.argv[1], only_missing="--only-missing" in sys.argv)


if __name__ == "__main__":
    _main()
