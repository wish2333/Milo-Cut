"""Qwen3-ASR subprocess inference script.

Runs inside an isolated plugin venv. Communicates with the parent process
via stdout JSON events (progress, result, error).

Features:
- Uses qwen-asr package (Qwen3ASRModel) for transcription
- Long audio smart slicing (accumulate ~280s, cut at best silence point)
- Forced alignment with Qwen3-ForcedAligner for word-level timestamps
- Overlap region deduplication to prevent missing words at slice boundaries

Usage (launched by PluginManager.run_in_plugin):
    python qwen_transcribe.py --result-path /path/to/result.json \
        --media-path /path/to/media.mp3 \
        --asr-model-path /path/to/asr-model \
        --aligner-model-path /path/to/aligner-model \
        --language zh \
        --device cpu
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Import common utilities for subprocess IPC
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.asr_scripts.common import (
    parse_args,
    report,
    start_stdin_watchdog,
    write_result,
)

# Constants for smart slicing
ACCUMULATE_THRESHOLD = 280.0  # seconds - target slice length
FORCE_CUT_THRESHOLD = 240.0   # seconds - force cut if no silence found
SLICE_OVERLAP = 0.5           # seconds - overlap between slices
MIN_SILENCE_DURATION = 0.3    # seconds - minimum silence to consider as cut point


def parse_qwen_args() -> argparse.Namespace:
    """Parse Qwen3-ASR specific arguments."""
    common = parse_args()

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--media-path", required=True, help="Path to media file")
    parser.add_argument("--asr-model-path", required=True, help="Path to Qwen3-ASR model")
    parser.add_argument("--aligner-model-path", default="", help="Path to Qwen3-ForcedAligner model (optional)")
    parser.add_argument("--language", default="zh", help="Language code")
    parser.add_argument("--device", default="cpu", help="Device: cpu, cuda")
    parser.add_argument("--compute-type", default="bfloat16", help="Compute type: bfloat16, float16, float32")
    parser.add_argument("--result-path", required=True, help="Path to write result JSON")

    args, _ = parser.parse_known_args()

    if not args.result_path and hasattr(common, "result_path"):
        args.result_path = common.result_path

    return args


def find_silence_points(audio_data: Any, sample_rate: int) -> list[float]:
    """Find silence points in audio for smart slicing."""
    import numpy as np

    frame_size = int(sample_rate * 0.025)
    hop_size = int(sample_rate * 0.010)

    silence_points = []
    threshold = np.mean(np.abs(audio_data)) * 0.1

    for i in range(0, len(audio_data) - frame_size, hop_size):
        frame = audio_data[i:i + frame_size]
        energy = np.mean(np.abs(frame))
        if energy < threshold:
            timestamp = i / sample_rate
            silence_points.append(timestamp)

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
    """Find the best silence point near the target time."""
    if not silence_points:
        return target_time
    candidates = [p for p in silence_points if abs(p - target_time) <= search_range]
    if not candidates:
        return target_time
    return min(candidates, key=lambda p: abs(p - target_time))


def smart_slice_audio(audio_path: str, temp_dir: str) -> list[dict[str, Any]]:
    """Slice long audio into manageable chunks for ASR."""
    import subprocess
    import numpy as np

    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json", audio_path
    ]

    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except Exception as e:
        report("error", message=f"Failed to get audio duration: {e}")
        sys.exit(1)

    if duration <= ACCUMULATE_THRESHOLD + 30:
        return [{"path": audio_path, "start": 0.0, "end": duration}]

    raw_path = Path(temp_dir) / "audio_raw.wav"
    extract_cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ac", "1", "-ar", "16000",
        "-f", "wav", str(raw_path)
    ]

    try:
        subprocess.run(extract_cmd, capture_output=True, check=True)
    except Exception as e:
        report("error", message=f"Failed to extract audio: {e}")
        sys.exit(1)

    try:
        import wave
        with wave.open(str(raw_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            sample_rate = wf.getframerate()
    except Exception as e:
        report("error", message=f"Failed to load audio data: {e}")
        sys.exit(1)

    report("progress", percent=5.0, message="Analyzing audio for silence points...")
    silence_points = find_silence_points(audio_data, sample_rate)

    slices = []
    current_start = 0.0
    slice_idx = 0

    while current_start < duration:
        target_end = current_start + ACCUMULATE_THRESHOLD

        if target_end >= duration:
            slices.append({
                "path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"),
                "start": current_start,
                "end": duration,
            })
            break

        cut_point = find_best_cut_point(silence_points, target_end)
        if abs(cut_point - target_end) > 30:
            cut_point = current_start + FORCE_CUT_THRESHOLD

        actual_start = max(0, current_start - SLICE_OVERLAP) if slice_idx > 0 else current_start

        slices.append({
            "path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"),
            "start": actual_start,
            "end": cut_point,
        })

        current_start = cut_point
        slice_idx += 1

    for i, slice_info in enumerate(slices):
        start = slice_info["start"]
        duration_slice = slice_info["end"] - start

        extract_cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", str(start),
            "-t", str(duration_slice),
            "-ac", "1", "-ar", "16000",
            slice_info["path"]
        ]

        try:
            subprocess.run(extract_cmd, capture_output=True, check=True)
        except Exception as e:
            report("error", message=f"Failed to extract slice {i}: {e}")
            sys.exit(1)

        pct = 5.0 + (i / len(slices)) * 10.0
        report("progress", percent=pct, message=f"Extracted slice {i+1}/{len(slices)}")

    return slices


def deduplicate_overlap(segments: list[dict], slice_start: float, slice_end: float) -> list[dict]:
    """Remove duplicate words in overlap regions."""
    if not segments:
        return segments

    valid_start = slice_start + SLICE_OVERLAP if slice_start > 0 else slice_start

    filtered = []
    for seg in segments:
        if seg.get("words"):
            filtered_words = []
            for word in seg["words"]:
                midpoint = (word["start"] + word["end"]) / 2
                if midpoint >= valid_start:
                    filtered_words.append(word)
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
    """Split long text into standard subtitle segments."""
    if not text:
        return []

    if not words:
        return [{
            "id": f"seg_{slice_start:.3f}",
            "start": round(slice_start, 3),
            "end": round(slice_end, 3),
            "text": text.strip(),
            "words": [],
        }]

    import re

    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))

    if is_chinese:
        sentences = re.split(r"([。！？，、；：])", text)
        merged = []
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                merged.append(sentences[i] + sentences[i + 1])
            else:
                merged.append(sentences[i])
        sentences = [s.strip() for s in merged if s.strip()]
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
            current_time = sentence_end

        segment_id = f"seg_{sentence_start:.3f}" if sentence_start else f"seg_{slice_start:.3f}"
        segments.append({
            "id": segment_id,
            "start": round(sentence_start or slice_start, 3),
            "end": round(sentence_end or slice_end, 3),
            "text": sentence,
            "words": sentence_words,
        })

    if not segments:
        segments.append({
            "id": f"seg_{slice_start:.3f}",
            "start": round(slice_start, 3),
            "end": round(slice_end, 3),
            "text": text.strip(),
            "words": words,
        })

    return segments


def main() -> None:
    args = parse_qwen_args()

    report("progress", percent=2.0, message="Checking plugin environment...")

    # Verify dependencies
    try:
        import torch
    except ImportError as e:
        report("error", message=f"torch not installed: {e}")
        sys.exit(1)

    try:
        from qwen_asr import Qwen3ASRModel
    except ImportError as e:
        report("error", message=f"qwen-asr not installed: {e}")
        sys.exit(1)

    # Suppress CUDA init when running on CPU only.
    # Only set CUDA_VISIBLE_DEVICES for CPU mode -- setting it to ""
    # when the var is not natively set would hide GPUs on Windows.
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    # Create temporary directory for slices
    with tempfile.TemporaryDirectory() as temp_dir:
        report("progress", percent=5.0, message="Analyzing audio for smart slicing...")

        slices = smart_slice_audio(args.media_path, temp_dir)
        total_slices = len(slices)

        report("progress", percent=10.0, message=f"Audio divided into {total_slices} slice(s)")

        # Load ASR model with forced aligner
        report("progress", percent=12.0, message="Loading Qwen3-ASR model...")

        dev = args.device
        DTYPE_MAP = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}
        dtype = DTYPE_MAP.get(args.compute_type, torch.bfloat16)
        if dev == "cpu":
            dtype = torch.float32
        device_map = "cpu" if dev == "cpu" else "auto"

        aligner_kwargs = {}
        if args.aligner_model_path:
            report("progress", percent=12.5, message="Loading Qwen3-ForcedAligner...")
            aligner_kwargs = {
                "forced_aligner": args.aligner_model_path,
                "forced_aligner_kwargs": {
                    "dtype": dtype,
                    "device_map": device_map,
                },
            }

        try:
            asr_model = Qwen3ASRModel.from_pretrained(
                args.asr_model_path,
                dtype=dtype,
                device_map=device_map,
                max_inference_batch_size=32,
                max_new_tokens=256,
                **aligner_kwargs,
            )
        except Exception as e:
            report("error", message=f"Failed to load ASR model: {e}")
            sys.exit(1)

        report("progress", percent=15.0, message=f"Model loaded on {dev}. Starting transcription...")

        # Start orphan process defense AFTER model loading
        start_stdin_watchdog()

        # Map language codes to Qwen3-ASR language names
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
        # Auto-detect: pass None to model.transcribe() for automatic language detection
        if args.language in ("auto", "", "None", None):
            language = None

        # Process each slice
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
                return_timestamps = bool(args.aligner_model_path)
                results = asr_model.transcribe(
                    audio=slice_path,
                    language=language,
                    return_time_stamps=return_timestamps,
                )

                result = results[0]
                transcription = result.text.strip()

                # Extract word-level timestamps if available
                all_words = []
                if hasattr(result, "time_stamps") and result.time_stamps:
                    for item in result.time_stamps:
                        # Handle both flat list and nested list formats
                        # Flat: [ForcedAlignItem, ...] -> iterate directly
                        # Nested: [[ForcedAlignItem, ...], ...] -> iterate inner list
                        ts_items = item if isinstance(item, list) else [item]
                        for ts in ts_items:
                            # Only add words with valid timestamps (not None and not 0)
                            # ForcedAlignItem has start_time/end_time (in seconds)
                            start = getattr(ts, "start_time", getattr(ts, "start", None))
                            end = getattr(ts, "end_time", getattr(ts, "end", None))
                            if start is not None and end is not None and (start > 0 or end > 0):
                                all_words.append({
                                    "word": ts.text if hasattr(ts, "text") else str(ts),
                                    "start": round(start + slice_start, 3),
                                    "end": round(end + slice_start, 3),
                                    "confidence": round(getattr(ts, "confidence", 0.9), 3),
                                })

                # Split into subtitle segments
                segments = _split_into_subtitle_segments(
                    text=transcription,
                    words=all_words,
                    slice_start=slice_start,
                    slice_end=slice_end,
                    max_chars_per_segment=30,
                    max_duration_per_segment=8.0,
                )

                # Deduplicate overlap
                if i > 0:
                    segments = deduplicate_overlap(segments, slice_start, slice_end)

                all_segments.extend(segments)
                processed_duration += slice_duration

                pct = 15.0 + (processed_duration / total_duration) * 65.0
                report("progress", percent=pct, message=f"Completed slice {i+1}/{total_slices}")

            except Exception as e:
                report("error", message=f"Transcription failed on slice {i}: {e}")
                sys.exit(1)

        # Final progress
        report("progress", percent=85.0, message="Finalizing results...")

        total_words = sum(len(s.get("words", [])) for s in all_segments)
        total_text_chars = sum(len(s.get("text", "")) for s in all_segments)

        result = {
            "engine": "qwen3-asr",
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
        write_result(args.result_path, result)

        report("progress", percent=100.0, message=f"Transcription complete: {len(all_segments)} segments, {total_words} words")


if __name__ == "__main__":
    main()
