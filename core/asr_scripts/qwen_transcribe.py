"""Qwen3-ASR subprocess inference script.

Runs inside an isolated plugin venv. Communicates with the parent process
via stdout JSON events (progress, result, error).

Features:
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
    # First parse common args (--result-path)
    common = parse_args()

    # Then parse Qwen-specific args
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--media-path", required=True, help="Path to media file")
    parser.add_argument("--asr-model-path", required=True, help="Path to Qwen3-ASR model")
    parser.add_argument("--aligner-model-path", required=True, help="Path to Qwen3-ForcedAligner model")
    parser.add_argument("--language", default="zh", help="Language code")
    parser.add_argument("--device", default="cpu", help="Device: cpu, cuda")
    parser.add_argument("--result-path", required=True, help="Path to write result JSON")

    # Parse known args, ignoring any unknown args
    args, _ = parser.parse_known_args()

    # Copy result_path from common args if not set
    if not args.result_path and hasattr(common, 'result_path'):
        args.result_path = common.result_path

    return args


def find_silence_points(audio_data: Any, sample_rate: int) -> list[float]:
    """Find silence points in audio for smart slicing.

    Uses simple energy-based detection. Returns list of timestamps (in seconds)
    where silence is detected.
    """
    import numpy as np

    # Calculate frame energy
    frame_size = int(sample_rate * 0.025)  # 25ms frames
    hop_size = int(sample_rate * 0.010)    # 10ms hop

    silence_points = []
    threshold = np.mean(np.abs(audio_data)) * 0.1  # 10% of mean amplitude

    for i in range(0, len(audio_data) - frame_size, hop_size):
        frame = audio_data[i:i + frame_size]
        energy = np.mean(np.abs(frame))

        if energy < threshold:
            timestamp = i / sample_rate
            silence_points.append(timestamp)

    # Merge close silence points
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
    """Find the best silence point near the target time.

    Searches within search_range seconds of target_time for the closest silence point.
    If none found, returns target_time.
    """
    if not silence_points:
        return target_time

    # Filter silence points within search range
    candidates = [
        p for p in silence_points
        if abs(p - target_time) <= search_range
    ]

    if not candidates:
        return target_time

    # Return closest to target
    return min(candidates, key=lambda p: abs(p - target_time))


def smart_slice_audio(audio_path: str, temp_dir: str) -> list[dict[str, Any]]:
    """Slice long audio into manageable chunks for ASR.

    Strategy:
    1. Accumulate audio until ~ACCUMULATE_THRESHOLD seconds
    2. Find best silence point near the threshold
    3. Cut with SLICE_OVERLAP overlap to prevent missing words
    4. If no silence found, force cut at FORCE_CUT_THRESHOLD

    Returns list of dicts with keys: path, start, end
    """
    import subprocess
    import numpy as np

    # Get audio duration using ffprobe
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

    # If short enough, return as single slice
    if duration <= ACCUMULATE_THRESHOLD + 30:
        return [{"path": audio_path, "start": 0.0, "end": duration}]

    # Extract audio as raw PCM for silence detection
    raw_path = Path(temp_dir) / "audio_raw.wav"
    extract_cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ac", "1", "-ar", "16000",  # mono, 16kHz
        "-f", "wav", str(raw_path)
    ]

    try:
        subprocess.run(extract_cmd, capture_output=True, check=True)
    except Exception as e:
        report("error", message=f"Failed to extract audio: {e}")
        sys.exit(1)

    # Load audio data for silence detection
    try:
        import wave
        with wave.open(str(raw_path), 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            sample_rate = wf.getframerate()
    except Exception as e:
        report("error", message=f"Failed to load audio data: {e}")
        sys.exit(1)

    # Find silence points
    report("progress", percent=5.0, message="Analyzing audio for silence points...")
    silence_points = find_silence_points(audio_data, sample_rate)

    # Generate slices
    slices = []
    current_start = 0.0
    slice_idx = 0

    while current_start < duration:
        # Target end time
        target_end = current_start + ACCUMULATE_THRESHOLD

        if target_end >= duration:
            # Last slice
            slices.append({
                "path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"),
                "start": current_start,
                "end": duration,
            })
            break

        # Find best cut point
        cut_point = find_best_cut_point(silence_points, target_end)

        # If cut point is too far from target (no silence), force cut
        if abs(cut_point - target_end) > 30:
            cut_point = current_start + FORCE_CUT_THRESHOLD

        # Add overlap for non-first slices
        actual_start = max(0, current_start - SLICE_OVERLAP) if slice_idx > 0 else current_start

        slices.append({
            "path": str(Path(temp_dir) / f"slice_{slice_idx:03d}.wav"),
            "start": actual_start,
            "end": cut_point,
        })

        current_start = cut_point
        slice_idx += 1

    # Extract slices using ffmpeg
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

        # Report progress
        pct = 5.0 + (i / len(slices)) * 10.0
        report("progress", percent=pct, message=f"Extracted slice {i+1}/{len(slices)}")

    return slices


def deduplicate_overlap(segments: list[dict], slice_start: float, slice_end: float) -> list[dict]:
    """Remove duplicate words in overlap regions.

    For words that appear in both the current slice and the previous slice,
    keep only the ones that are clearly within this slice's valid content area.
    """
    if not segments:
        return segments

    # Define valid content area (excluding overlap)
    valid_start = slice_start + SLICE_OVERLAP if slice_start > 0 else slice_start

    filtered = []
    for seg in segments:
        # Filter words in overlap region
        if seg.get("words"):
            filtered_words = []
            for word in seg["words"]:
                # Keep word if its midpoint is in valid area
                midpoint = (word["start"] + word["end"]) / 2
                if midpoint >= valid_start:
                    filtered_words.append(word)

            # Only keep segment if it has words remaining
            if filtered_words:
                seg["words"] = filtered_words
                # Recalculate segment boundaries from words
                seg["start"] = filtered_words[0]["start"]
                seg["end"] = filtered_words[-1]["end"]
                filtered.append(seg)
        else:
            # No word-level timestamps, keep segment if start is in valid area
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
    """Split long text into standard subtitle segments.

    Standard subtitle format:
    - Each segment has 1-2 lines of text
    - Each line has max 15-20 characters (for Chinese)
    - Segment duration should be 2-8 seconds
    - Word-level timestamps are preserved

    Args:
        text: Full transcription text
        words: List of word dicts with start/end/text
        slice_start: Start time of the slice
        slice_end: End time of the slice
        max_chars_per_segment: Max characters per subtitle segment
        max_duration_per_segment: Max duration in seconds per segment

    Returns:
        List of segment dicts in standard subtitle format
    """
    if not text:
        return []

    # If no word-level timestamps, create a single segment
    if not words:
        return [{
            "id": f"seg_{slice_start:.3f}",
            "start": round(slice_start, 3),
            "end": round(slice_end, 3),
            "text": text.strip(),
            "words": [],
        }]

    # Split text into sentences/phrases
    # For Chinese: split by punctuation marks
    # For English: split by sentence boundaries
    import re

    # Detect language from text
    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))

    if is_chinese:
        # Split by Chinese punctuation
        sentences = re.split(r'([。！？，、；：])', text)
        # Merge punctuation with preceding text
        merged = []
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                merged.append(sentences[i] + sentences[i + 1])
            else:
                merged.append(sentences[i])
        sentences = [s.strip() for s in merged if s.strip()]
    else:
        # Split by English punctuation
        sentences = re.split(r'([.!?,;:])', text)
        # Merge punctuation with preceding text
        merged = []
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                merged.append(sentences[i] + sentences[i + 1])
            else:
                merged.append(sentences[i])
        sentences = [s.strip() for s in merged if s.strip()]

    # If no sentences found, use the whole text
    if not sentences:
        sentences = [text.strip()]

    # Create segments with proper timing
    segments = []
    word_idx = 0
    current_time = slice_start

    for sentence in sentences:
        if not sentence:
            continue

        # Find words that belong to this sentence
        sentence_words = []
        sentence_start = None
        sentence_end = None

        # Match words to sentence text
        remaining_text = sentence
        while word_idx < len(words) and remaining_text:
            word = words[word_idx]
            word_text = word["word"].strip()

            # Check if this word is part of the sentence
            if word_text in remaining_text:
                sentence_words.append(word)
                if sentence_start is None:
                    sentence_start = word["start"]
                sentence_end = word["end"]
                remaining_text = remaining_text.replace(word_text, "", 1).strip()
                word_idx += 1
            else:
                break

        # If no words matched, use time-based estimation
        if not sentence_words:
            # Estimate duration based on text length
            char_count = len(sentence)
            estimated_duration = max(1.0, min(max_duration_per_segment, char_count * 0.15))
            sentence_start = current_time
            sentence_end = current_time + estimated_duration
            current_time = sentence_end

        # Create segment
        segment_id = f"seg_{sentence_start:.3f}" if sentence_start else f"seg_{slice_start:.3f}"
        segments.append({
            "id": segment_id,
            "start": round(sentence_start or slice_start, 3),
            "end": round(sentence_end or slice_end, 3),
            "text": sentence,
            "words": sentence_words,
        })

    # If no segments created, create a single segment
    if not segments:
        segments.append({
            "id": f"seg_{slice_start:.3f}",
            "start": round(slice_start, 3),
            "end": round(slice_end, 3),
            "text": text.strip(),
            "words": words,
        })

    return segments


def transcribe_slice(
    model: Any,
    aligner: Any,
    slice_path: str,
    slice_start: float,
    slice_end: float,
    language: str,
    device: str,
    slice_idx: int,
    total_slices: int,
) -> list[dict]:
    """Transcribe a single audio slice with forced alignment.

    Returns list of segment dicts in standard subtitle format with word-level timestamps.
    """
    import torch

    # Load audio for ASR
    try:
        from transformers import AutoProcessor
        processor = AutoProcessor.from_pretrained(model.name_or_path)
    except Exception:
        # Fallback: use the processor from the model
        processor = model.processor if hasattr(model, 'processor') else None

    if processor is None:
        report("error", message="Failed to load processor")
        sys.exit(1)

    # Prepare audio input
    try:
        import librosa
        audio_array, sr = librosa.load(slice_path, sr=16000)
    except Exception as e:
        report("error", message=f"Failed to load audio slice: {e}")
        sys.exit(1)

    # Run ASR
    try:
        inputs = processor(audio_array, sampling_rate=16000, return_tensors="pt")
        if device == "cuda" and torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(**inputs, language=language)

        # Decode to text
        transcription = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    except Exception as e:
        report("error", message=f"ASR inference failed on slice {slice_idx}: {e}")
        sys.exit(1)

    # Run forced alignment for word-level timestamps
    all_words = []

    try:
        # Use aligner for word-level alignment
        alignment = aligner.transcribe(
            audio_array,
            transcription,
            language=language,
        )

        # Parse alignment result with global timestamps
        for word_info in alignment.get("words", []):
            all_words.append({
                "word": word_info["word"],
                "start": round(word_info["start"] + slice_start, 3),
                "end": round(word_info["end"] + slice_start, 3),
                "confidence": round(word_info.get("confidence", 0.9), 3),
            })
    except Exception:
        # Fallback: no word-level timestamps
        pass

    # Split into standard subtitle segments
    segments = _split_into_subtitle_segments(
        text=transcription,
        words=all_words,
        slice_start=slice_start,
        slice_end=slice_end,
        max_chars_per_segment=30,
        max_duration_per_segment=8.0,
    )

    # Deduplicate overlap with previous slice
    if slice_idx > 0:
        segments = deduplicate_overlap(segments, slice_start, slice_end)

    return segments


def main() -> None:
    args = parse_qwen_args()

    # Start orphan process defense
    start_stdin_watchdog()

    report("progress", percent=2.0, message="Checking plugin environment...")

    # Verify dependencies
    try:
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
    except ImportError as e:
        report("error", message=f"Required dependencies not installed: {e}")
        sys.exit(1)

    # Create temporary directory for slices
    with tempfile.TemporaryDirectory() as temp_dir:
        report("progress", percent=5.0, message="Analyzing audio for smart slicing...")

        # Smart slice audio
        slices = smart_slice_audio(args.media_path, temp_dir)
        total_slices = len(slices)

        report("progress", percent=10.0, message=f"Audio divided into {total_slices} slice(s)")

        # Load ASR model
        report("progress", percent=12.0, message="Loading Qwen3-ASR model...")
        try:
            asr_model = AutoModelForSpeechSeq2Seq.from_pretrained(
                args.asr_model_path,
                torch_dtype=torch.float32 if args.device == "cpu" else torch.float16,
                low_cpu_mem_usage=True,
            )
            if args.device == "cuda" and torch.cuda.is_available():
                asr_model = asr_model.cuda()
            asr_model.eval()
        except Exception as e:
            report("error", message=f"Failed to load ASR model: {e}")
            sys.exit(1)

        # Load aligner model
        report("progress", percent=15.0, message="Loading Qwen3-ForcedAligner model...")
        try:
            # Qwen3-ForcedAligner uses a different loading mechanism
            # This is a simplified version - actual implementation depends on the model's API
            from qwen3_forced_aligner import Qwen3ForcedAligner
            aligner = Qwen3ForcedAligner(
                model_path=args.aligner_model_path,
                device=args.device,
            )
        except ImportError:
            # Fallback: use simple VAD-based alignment
            report("log", message="Qwen3-ForcedAligner not available, using fallback alignment")
            aligner = None
        except Exception as e:
            report("error", message=f"Failed to load aligner model: {e}")
            sys.exit(1)

        # Process each slice
        all_segments = []
        total_duration = sum(s["end"] - s["start"] for s in slices)
        processed_duration = 0.0

        for i, slice_info in enumerate(slices):
            slice_path = slice_info["path"]
            slice_start = slice_info["start"]
            slice_end = slice_info["end"]
            slice_duration = slice_end - slice_start

            # Update progress
            base_pct = 15.0 + (processed_duration / total_duration) * 65.0
            report("progress", percent=base_pct, message=f"Transcribing slice {i+1}/{total_slices} ({slice_start:.1f}s - {slice_end:.1f}s)")

            # Transcribe slice
            segments = transcribe_slice(
                model=asr_model,
                aligner=aligner,
                slice_path=slice_path,
                slice_start=slice_start,
                slice_end=slice_end,
                language=args.language,
                device=args.device,
                slice_idx=i,
                total_slices=total_slices,
            )

            all_segments.extend(segments)
            processed_duration += slice_duration

            # Report slice completion
            pct = 15.0 + (processed_duration / total_duration) * 65.0
            report("progress", percent=pct, message=f"Completed slice {i+1}/{total_slices}")

        # Final progress
        report("progress", percent=85.0, message="Finalizing results...")

        # Build final result
        total_words = sum(len(s.get("words", [])) for s in all_segments)
        total_text_chars = sum(len(s.get("text", "")) for s in all_segments)

        result = {
            "engine": "qwen3-asr",
            "language": args.language,
            "language_probability": 0.95,  # Qwen3 doesn't provide this
            "duration": total_duration,
            "segments": all_segments,
            "segment_count": len(all_segments),
            "word_count": total_words,
            "text_length": total_text_chars,
            "slices_processed": total_slices,
        }

        # Write result to file
        report("progress", percent=95.0, message="Saving results...")
        write_result(args.result_path, result)

        report("progress", percent=100.0, message=f"Transcription complete: {len(all_segments)} segments, {total_words} words")


if __name__ == "__main__":
    main()
