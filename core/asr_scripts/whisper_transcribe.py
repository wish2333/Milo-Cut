"""faster-whisper subprocess inference script.

Runs inside an isolated plugin venv. Communicates with the parent process
via stdout JSON events (progress, result, error).

Usage (launched by PluginManager.run_in_plugin):
    python whisper_transcribe.py --result-path /path/to/result.json \
        --media-path /path/to/media.mp3 \
        --model-path /path/to/model \
        --language zh \
        --device cpu \
        --compute-type int8 \
        --word-timestamps true \
        --vad-filter true
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Import common utilities for subprocess IPC
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.asr_scripts.common import (
    parse_args,
    report,
    start_stdin_watchdog,
    write_result,
)


def parse_whisper_args() -> argparse.Namespace:
    """Parse whisper-specific arguments."""
    base = parse_args()
    parser = argparse.ArgumentParser(parents=[base._parser if hasattr(base, '_parser') else argparse.ArgumentParser()])
    parser.add_argument("--media-path", required=True, help="Path to media file")
    parser.add_argument("--model-path", required=True, help="Path to downloaded model")
    parser.add_argument("--language", default="zh", help="Language code")
    parser.add_argument("--device", default="cpu", help="Device: cpu, cuda, auto")
    parser.add_argument("--compute-type", default="int8", help="Compute type: int8, float16, float32")
    parser.add_argument("--word-timestamps", default="true", help="Enable word-level timestamps")
    parser.add_argument("--vad-filter", default="true", help="Enable Silero VAD filtering")
    # Re-parse to get all args
    return parser.parse_args()


def main() -> None:
    args = parse_whisper_args()

    # Start orphan process defense
    start_stdin_watchdog()

    report("progress", percent=5.0, message="Loading faster-whisper model...")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        report("error", message="faster-whisper is not installed in this environment")
        sys.exit(1)

    model_path = args.model_path
    device = args.device
    compute_type = args.compute_type

    # If model_path is a HuggingFace repo_id, the model will be downloaded
    # If it's a local path, it will be loaded from disk
    try:
        model = WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
        )
    except Exception as exc:
        report("error", message=f"Failed to load model: {exc}")
        sys.exit(1)

    report("progress", percent=15.0, message="Model loaded. Starting transcription...")

    word_timestamps = args.word_timestamps.lower() == "true"
    vad_filter = args.vad_filter.lower() == "true"
    language = args.language if args.language else None

    # Run transcription
    report("progress", percent=20.0, message="Transcribing audio...")

    try:
        segments_iter, info = model.transcribe(
            args.media_path,
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
        )
    except Exception as exc:
        report("error", message=f"Transcription failed: {exc}")
        sys.exit(1)

    report("progress", percent=30.0, message=f"Detected language: {info.language} (prob: {info.language_probability:.2f})")

    # Collect segments with progress reporting
    segments: list[dict] = []
    total_duration = info.duration if info.duration > 0 else 1.0

    for seg in segments_iter:
        seg_data = {
            "id": f"seg_{seg.start:.3f}",
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": [],
        }

        if word_timestamps and seg.words:
            seg_data["words"] = [
                {
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "confidence": round(w.probability, 3),
                }
                for w in seg.words
            ]

        segments.append(seg_data)

        # Report progress based on position in audio
        pct = 20.0 + (seg.end / total_duration) * 70.0
        report("progress", percent=min(pct, 90.0), message=f"Transcribed {seg.end:.1f}s / {total_duration:.1f}s")

    report("progress", percent=95.0, message="Saving results...")

    # Build result
    result = {
        "engine": "faster-whisper",
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 3),
        "segments": segments,
        "segment_count": len(segments),
        "word_count": sum(len(s["words"]) for s in segments),
    }

    # Write result to file (not stdout) to avoid pipe overflow
    write_result(args.result_path, result)

    report("progress", percent=100.0, message=f"Transcription complete: {len(segments)} segments")


if __name__ == "__main__":
    main()
