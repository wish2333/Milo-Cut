"""MLX Qwen3-ASR subprocess inference script (Apple Silicon).

Runs inside an isolated plugin venv. Communicates with the parent process
via stdout JSON events (progress, result, error).

Uses mlx-qwen3-asr for Metal-accelerated inference on Apple Silicon.
No PyTorch dependency required.

Usage (launched by PluginManager.run_in_plugin):
    python mlx_transcribe.py --result-path /path/to/result.json \
        --media-path /path/to/media.mp3 \
        --asr-model-path /path/to/asr-model \
        --aligner-model-path /path/to/aligner-model \
        --language zh
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Suppress console window in packaged environment
_SUBPROCESS_KWARGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32"
    else {"start_new_session": True}
)

# Import common utilities for subprocess IPC
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.asr_scripts.common import (
    parse_args,
    report,
    start_stdin_watchdog,
    write_result,
)

# Constants for smart slicing
ACCUMULATE_THRESHOLD = 280.0
FORCE_CUT_THRESHOLD = 240.0
SLICE_OVERLAP = 0.5
MIN_SILENCE_DURATION = 0.3


def parse_mlx_args() -> argparse.Namespace:
    common = parse_args()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--media-path", required=True)
    parser.add_argument("--asr-model-path", required=True)
    parser.add_argument("--aligner-model-path", default="")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--result-path", required=True)
    args, _ = parser.parse_known_args()
    if not args.result_path and hasattr(common, "result_path"):
        args.result_path = common.result_path
    return args


# ---- Smart slicing (reused from qwen_transcribe.py) ----

def find_silence_points(audio_data: Any, sample_rate: int) -> list[float]:
    import numpy as np
    frame_size = int(sample_rate * 0.025)
    hop_size = int(sample_rate * 0.010)
    silence_points = []
    threshold = np.mean(np.abs(audio_data)) * 0.1
    for i in range(0, len(audio_data) - frame_size, hop_size):
        frame = audio_data[i:i + frame_size]
        energy = np.mean(np.abs(frame))
        if energy < threshold:
            silence_points.append(i / sample_rate)
    merged = []
    if silence_points:
        current_start = silence_points[0]
        current_end = silence_points[0]
        for point in silence_points[1:]:
            if point - current_end < MIN_SILENCE_DURATION:
                current_end = point
            else:
                merged.append((current_start + current_end) / 2)
                current_start = point
                current_end = point
        merged.append((current_start + current_end) / 2)
    return merged


def find_best_cut_point(silence_points: list[float], target_time: float, search_range: float = 10.0) -> float:
    if not silence_points:
        return target_time
    candidates = [p for p in silence_points if abs(p - target_time) <= search_range]
    if not candidates:
        return target_time
    return min(candidates, key=lambda p: abs(p - target_time))


def smart_slice_audio(audio_path: str, temp_dir: str) -> list[dict[str, Any]]:
    import numpy as np
    probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", audio_path]
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, **_SUBPROCESS_KWARGS)
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except Exception as e:
        report("error", message=f"Failed to get audio duration: {e}")
        sys.exit(1)

    if duration <= ACCUMULATE_THRESHOLD + 30:
        return [{"path": audio_path, "start": 0.0, "end": duration}]

    raw_path = Path(temp_dir) / "audio_raw.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", "-f", "wav", str(raw_path)],
        capture_output=True, check=True, **_SUBPROCESS_KWARGS,
    )

    import wave
    with wave.open(str(raw_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        sample_rate = wf.getframerate()

    report("progress", percent=5.0, message="Analyzing audio for silence points...")
    silence_points = find_silence_points(audio_data, sample_rate)

    slices = []
    current_start = 0.0
    slice_idx = 0
    while current_start < duration:
        target_end = current_start + ACCUMULATE_THRESHOLD
        if target_end >= duration:
            slices.append({"path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"), "start": current_start, "end": duration})
            break
        cut_point = find_best_cut_point(silence_points, target_end)
        if abs(cut_point - target_end) > 30:
            cut_point = current_start + FORCE_CUT_THRESHOLD
        actual_start = max(0, current_start - SLICE_OVERLAP) if slice_idx > 0 else current_start
        slices.append({"path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"), "start": actual_start, "end": cut_point})
        current_start = cut_point
        slice_idx += 1

    for i, s in enumerate(slices):
        dur = s["end"] - s["start"]
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ss", str(s["start"]), "-t", str(dur), "-ac", "1", "-ar", "16000", s["path"]],
            capture_output=True, check=True, **_SUBPROCESS_KWARGS,
        )
        pct = 5.0 + (i / len(slices)) * 10.0
        report("progress", percent=pct, message=f"Extracted slice {i+1}/{len(slices)}")

    return slices


def deduplicate_overlap(segments: list[dict], slice_start: float, slice_end: float) -> list[dict]:
    if not segments:
        return segments
    valid_start = slice_start + SLICE_OVERLAP if slice_start > 0 else slice_start
    filtered = []
    for seg in segments:
        if seg.get("words"):
            filtered_words = [w for w in seg["words"] if (w["start"] + w["end"]) / 2 >= valid_start]
            if filtered_words:
                seg["words"] = filtered_words
                seg["start"] = filtered_words[0]["start"]
                seg["end"] = filtered_words[-1]["end"]
                filtered.append(seg)
        else:
            if seg["start"] >= valid_start:
                filtered.append(seg)
    return filtered


def _split_into_subtitle_segments(
    text: str,
    words: list[dict],
    slice_start: float,
    slice_end: float,
    max_chars_per_segment: int = 30,
    max_duration_per_segment: float = 8.0,
) -> list[dict]:
    if not text:
        return []
    if not words:
        return [{"id": f"seg_{slice_start:.3f}", "start": round(slice_start, 3), "end": round(slice_end, 3), "text": text.strip(), "words": []}]

    is_chinese = bool(re.search(r"[一-鿿]", text))
    if is_chinese:
        sentences = re.split(r"([。！？，、；：])", text)
    else:
        sentences = re.split(r"([.!?,;:])", text)
    merged = []
    for i in range(0, len(sentences), 2):
        if i + 1 < len(sentences):
            merged.append(sentences[i] + sentences[i + 1])
        else:
            merged.append(sentences[i])
    sentences = [s.strip() for s in merged if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    segments = []
    word_idx = 0
    current_time = slice_start

    for sentence in sentences:
        if not sentence:
            continue
        sentence_words = []
        sentence_start = None
        sentence_end = None
        remaining_text = sentence
        while word_idx < len(words) and remaining_text:
            word = words[word_idx]
            word_text = word["word"].strip()
            if word_text in remaining_text:
                sentence_words.append(word)
                if sentence_start is None:
                    sentence_start = word["start"]
                sentence_end = word["end"]
                remaining_text = remaining_text.replace(word_text, "", 1).strip()
                word_idx += 1
            else:
                break
        if not sentence_words:
            char_count = len(sentence)
            estimated_duration = max(1.0, min(max_duration_per_segment, char_count * 0.15))
            sentence_start = current_time
            sentence_end = current_time + estimated_duration
        current_time = sentence_end or slice_end
        segment_id = f"seg_{sentence_start:.3f}" if sentence_start else f"seg_{slice_start:.3f}"
        segments.append({"id": segment_id, "start": round(sentence_start or slice_start, 3), "end": round(sentence_end or slice_end, 3), "text": sentence, "words": sentence_words})

    if not segments:
        segments.append({"id": f"seg_{slice_start:.3f}", "start": round(slice_start, 3), "end": round(slice_end, 3), "text": text.strip(), "words": words})
    return segments


def main() -> None:
    args = parse_mlx_args()

    report("progress", percent=2.0, message="Checking plugin environment...")

    try:
        from mlx_qwen3_asr import Session
    except ImportError as e:
        report("error", message=f"mlx-qwen3-asr not installed: {e}")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as temp_dir:
        report("progress", percent=5.0, message="Analyzing audio for smart slicing...")
        slices = smart_slice_audio(args.media_path, temp_dir)
        total_slices = len(slices)
        report("progress", percent=10.0, message=f"Audio divided into {total_slices} slice(s)")

        # Load ASR model
        report("progress", percent=12.0, message="Loading Qwen3-ASR model (MLX)...")

        try:
            session = Session(model=args.asr_model_path)
        except Exception as e:
            report("error", message=f"Failed to load ASR model: {e}")
            sys.exit(1)

        report("progress", percent=15.0, message="Model loaded (Apple Silicon MLX). Starting transcription...")
        start_stdin_watchdog()

        # Language mapping
        lang_map = {
            "zh": "Chinese", "en": "English", "yue": "Cantonese",
            "ar": "Arabic", "de": "German", "fr": "French",
            "es": "Spanish", "pt": "Portuguese", "id": "Indonesian",
            "it": "Italian", "ko": "Korean", "ru": "Russian",
            "th": "Thai", "vi": "Vietnamese", "ja": "Japanese",
            "tr": "Turkish", "hi": "Hindi", "ms": "Malay",
            "nl": "Dutch", "sv": "Swedish", "da": "Danish",
            "fi": "Finnish", "pl": "Polish", "cs": "Czech",
            "fil": "Filipino", "fa": "Persian", "el": "Greek",
            "ro": "Romanian", "hu": "Hungarian", "mk": "Macedonian",
        }
        language = lang_map.get(args.language, args.language)
        if args.language in ("auto", "", "None", None):
            language = None

        all_segments = []
        total_duration = sum(s["end"] - s["start"] for s in slices)
        processed_duration = 0.0

        for i, slice_info in enumerate(slices):
            slice_path = slice_info["path"]
            slice_start = slice_info["start"]
            slice_end = slice_info["end"]
            slice_duration = slice_end - slice_start

            base_pct = 15.0 + (processed_duration / total_duration) * 65.0
            report("progress", percent=base_pct, message=f"Transcribing slice {i+1}/{total_slices} ({slice_start:.1f}s - {slice_end:.1f}s)")

            try:
                use_timestamps = bool(args.aligner_model_path)
                transcribe_kwargs: dict[str, Any] = {
                    "language": language,
                    "return_timestamps": use_timestamps,
                }
                if use_timestamps and args.aligner_model_path:
                    transcribe_kwargs["forced_aligner"] = args.aligner_model_path
                result = session.transcribe(slice_path, **transcribe_kwargs)

                transcription = result.text.strip()

                # Extract word-level timestamps
                # MLX result.segments is a flat list of word dicts:
                # [{"text": "hello", "start": 0.5, "end": 0.8}, ...]
                all_words = []
                if use_timestamps and result.segments:
                    for entry in result.segments:
                        # entry might be a dict or an object with attributes
                        if isinstance(entry, dict):
                            text = entry.get("text", "")
                            start = entry.get("start", 0)
                            end = entry.get("end", 0)
                        else:
                            text = getattr(entry, "text", "")
                            start = getattr(entry, "start", 0)
                            end = getattr(entry, "end", 0)
                        if start > 0 or end > 0:
                            all_words.append({
                                "word": text,
                                "start": round(start + slice_start, 3),
                                "end": round(end + slice_start, 3),
                                "confidence": round(
                                    entry.get("confidence", 0.9) if isinstance(entry, dict)
                                    else getattr(entry, "confidence", 0.9), 3
                                ),
                            })

                segments = _split_into_subtitle_segments(
                    text=transcription,
                    words=all_words,
                    slice_start=slice_start,
                    slice_end=slice_end,
                )

                if i > 0:
                    segments = deduplicate_overlap(segments, slice_start, slice_end)

                all_segments.extend(segments)
                processed_duration += slice_duration

                pct = 15.0 + (processed_duration / total_duration) * 65.0
                report("progress", percent=pct, message=f"Completed slice {i+1}/{total_slices}")

            except Exception as e:
                report("error", message=f"Transcription failed on slice {i}: {e}")
                sys.exit(1)

        report("progress", percent=85.0, message="Finalizing results...")

        total_words = sum(len(s.get("words", [])) for s in all_segments)
        total_text_chars = sum(len(s.get("text", "")) for s in all_segments)

        result_data = {
            "engine": "qwen3-asr-mlx",
            "language": args.language,
            "language_probability": 0.95,
            "duration": total_duration,
            "segments": all_segments,
            "segment_count": len(all_segments),
            "word_count": total_words,
            "text_length": total_text_chars,
            "slices_processed": total_slices,
        }

        report("progress", percent=95.0, message="Saving results...")
        write_result(args.result_path, result_data)
        report("progress", percent=100.0, message=f"Transcription complete: {len(all_segments)} segments, {total_words} words")


if __name__ == "__main__":
    main()
