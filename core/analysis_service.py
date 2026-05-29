"""Rule-based analysis service for filler word, error trigger, and duplicate detection."""

from __future__ import annotations

import math
import uuid
from collections import Counter

from core.models import AnalysisResult, Segment


def _get_ngrams(text: str, language: str, n: int = 3) -> list[str]:
    """Extract n-grams from text based on language.

    For Chinese (zh-*): character-level n-grams.
    For English/Western: word-level 2-grams (split by space).
    For other/unknown: character-level n-grams (default).
    """
    if not text:
        return []

    # Chinese: character-level n-grams
    if language and language.startswith("zh"):
        return [text[i:i + n] for i in range(len(text) - n + 1)]

    # English/Western: word-level 2-grams
    if language and language.startswith(("en", "de", "fr", "es", "it", "pt", "ru")):
        words = text.split()
        if len(words) < 2:
            return words
        return [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]

    # Default: character-level n-grams
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _cosine_similarity(vec1: Counter, vec2: Counter) -> float:
    """Calculate cosine similarity between two frequency vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Get all unique keys
    all_keys = set(vec1.keys()) | set(vec2.keys())

    # Calculate dot product and magnitudes
    dot_product = sum(vec1.get(k, 0) * vec2.get(k, 0) for k in all_keys)
    magnitude1 = math.sqrt(sum(v * v for v in vec1.values()))
    magnitude2 = math.sqrt(sum(v * v for v in vec2.values()))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def _compute_similarity(text1: str, text2: str, language: str) -> float:
    """Compute similarity between two texts using n-gram cosine similarity."""
    ngrams1 = _get_ngrams(text1, language)
    ngrams2 = _get_ngrams(text2, language)

    if not ngrams1 or not ngrams2:
        return 0.0

    vec1 = Counter(ngrams1)
    vec2 = Counter(ngrams2)

    return _cosine_similarity(vec1, vec2)


def detect_duplicates(
    segments: list[Segment],
    language: str = "zh",
    threshold: float = 0.85,
    min_length: int = 5,
    window_size: int = 50,
    time_window_sec: float = 300.0,
) -> list[AnalysisResult]:
    """Detect duplicate/repeated segments using n-gram cosine similarity.

    Uses sliding window optimization:
    - Each segment is only compared with the next `window_size` segments
    - Only compares segments within `time_window_sec` seconds
    - Complexity: O(n * window_size) instead of O(n^2)

    Args:
        segments: List of Segment objects to analyze.
        language: Language code for n-gram extraction (e.g., "zh", "en").
        threshold: Similarity threshold to consider as duplicate (0.0-1.0).
        min_length: Minimum text length to consider for duplicate detection.
        window_size: Maximum number of subsequent segments to compare.
        time_window_sec: Maximum time window in seconds for comparison.

    Returns:
        List of AnalysisResult entries with type="duplicate".
    """
    # Filter to subtitle segments with sufficient text length
    subtitle_segs = [
        s for s in segments
        if s.type == "subtitle" and s.text and len(s.text) >= min_length
    ]

    if len(subtitle_segs) < 2:
        return []

    results: list[AnalysisResult] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, seg1 in enumerate(subtitle_segs):
        # Compare with next window_size segments within time window
        for j in range(i + 1, min(i + 1 + window_size, len(subtitle_segs))):
            seg2 = subtitle_segs[j]

            # Check time window constraint
            if seg2.start - seg1.start > time_window_sec:
                break

            # Avoid duplicate pairs
            pair_key = (min(seg1.id, seg2.id), max(seg1.id, seg2.id))
            if pair_key in seen_pairs:
                continue

            # Compute similarity
            similarity = _compute_similarity(seg1.text, seg2.text, language)

            if similarity >= threshold:
                seen_pairs.add(pair_key)
                results.append(AnalysisResult(
                    id=f"dup-{uuid.uuid4().hex[:8]}",
                    type="duplicate",
                    segment_ids=[seg1.id, seg2.id],
                    confidence=round(similarity, 3),
                    detail=f"Duplicate detected: '{seg1.text[:30]}...' ~ '{seg2.text[:30]}...' (similarity: {similarity:.2%})",
                ))

    return results


def detect_fillers(
    segments: list[Segment],
    filler_words: list[str],
) -> list[AnalysisResult]:
    """Detect filler words in subtitle segments.

    Uses longest-first matching with simple string containment for Chinese text.
    Returns AnalysisResult entries with type="filler" and confidence=0.90.
    """
    sorted_fillers = sorted(filler_words, key=len, reverse=True)
    results: list[AnalysisResult] = []

    for seg in segments:
        if seg.type != "subtitle" or not seg.text:
            continue
        matched: list[str] = []
        for word in sorted_fillers:
            if word in seg.text:
                matched.append(word)
        if matched:
            results.append(AnalysisResult(
                id=f"filler-{uuid.uuid4().hex[:8]}",
                type="filler",
                segment_ids=[seg.id],
                confidence=0.90,
                detail=f"Filler words found: {', '.join(matched)}",
            ))

    return results


def detect_errors(
    segments: list[Segment],
    trigger_words: list[str],
    lookahead: int = 3,
) -> list[AnalysisResult]:
    """Detect error triggers in subtitle segments and mark the error region.

    When a trigger word is found, the next N subtitle segments are included
    in the error region (the speaker is re-stating). Returns AnalysisResult
    entries with type="error" and confidence=0.85.
    """
    sorted_triggers = sorted(trigger_words, key=len, reverse=True)
    subtitle_segs = [s for s in segments if s.type == "subtitle"]
    results: list[AnalysisResult] = []

    for i, seg in enumerate(subtitle_segs):
        if not seg.text:
            continue
        matched_trigger: str | None = None
        for word in sorted_triggers:
            if word in seg.text:
                matched_trigger = word
                break
        if matched_trigger is None:
            continue

        region_ids: list[str] = [seg.id]
        for j in range(i + 1, min(i + 1 + lookahead, len(subtitle_segs))):
            region_ids.append(subtitle_segs[j].id)

        results.append(AnalysisResult(
            id=f"error-{uuid.uuid4().hex[:8]}",
            type="error",
            segment_ids=region_ids,
            confidence=0.85,
            detail=f"Error trigger: '{matched_trigger}' at segment {seg.id}",
        ))

    return results


def detect_punctuation(
    segments: list[Segment],
    punctuation_marks: list[str] | None = None,
) -> list[AnalysisResult]:
    """Detect segments containing punctuation marks for quick deletion.

    Useful for cleaning up ASR output that may contain unwanted punctuation
    or for identifying segments that need punctuation removal.

    Args:
        segments: List of Segment objects to analyze.
        punctuation_marks: List of punctuation marks to detect.
            Defaults to common Chinese and English punctuation.

    Returns:
        List of AnalysisResult entries with type="punctuation".
    """
    if punctuation_marks is None:
        # Default: common Chinese and English punctuation
        punctuation_marks = [
            # Chinese punctuation
            "。", "！", "？", "，", "、", "；", "：",
            """, """, "'", "'", "（", "）", "【", "】",
            "《", "》", "…", "——",
            # English punctuation
            ".", "!", "?", ",", ";", ":",
            "(", ")", "[", "]", "{", "}",
            "'", "'", "\"", "\"",
        ]

    results: list[AnalysisResult] = []

    for seg in segments:
        if seg.type != "subtitle" or not seg.text:
            continue

        # Find all punctuation marks in the segment
        found_punctuation = []
        for mark in punctuation_marks:
            if mark in seg.text:
                found_punctuation.append(mark)

        if found_punctuation:
            # Calculate confidence based on punctuation density
            text_len = len(seg.text)
            punct_count = sum(seg.text.count(p) for p in found_punctuation)
            density = punct_count / max(text_len, 1)
            confidence = min(0.95, 0.7 + density * 2)  # Higher density = higher confidence

            results.append(AnalysisResult(
                id=f"punct-{uuid.uuid4().hex[:8]}",
                type="punctuation",
                segment_ids=[seg.id],
                confidence=round(confidence, 3),
                detail=f"Punctuation found: {''.join(found_punctuation[:5])}{'...' if len(found_punctuation) > 5 else ''}",
            ))

    return results


def run_full_analysis(
    segments: list[Segment],
    settings: dict,
) -> list[AnalysisResult]:
    """Run filler, error, duplicate, and punctuation detection, returning combined results."""
    filler_words = settings.get("filler_words", [])
    trigger_words = settings.get("error_trigger_words", [])
    language = settings.get("asr_language", "zh")
    duplicate_threshold = settings.get("duplicate_threshold", 0.85)
    duplicate_min_length = settings.get("duplicate_min_length", 5)
    detect_punct = settings.get("detect_punctuation", True)

    fillers = detect_fillers(segments, filler_words)
    errors = detect_errors(segments, trigger_words)
    duplicates = detect_duplicates(
        segments,
        language=language,
        threshold=duplicate_threshold,
        min_length=duplicate_min_length,
    )

    result = fillers + errors + duplicates

    if detect_punct:
        punctuations = detect_punctuation(segments)
        result.extend(punctuations)

    return result
