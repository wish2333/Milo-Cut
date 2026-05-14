"""Rule-based analysis service for filler word and error trigger detection."""

from __future__ import annotations

import uuid

from core.models import AnalysisResult, Segment


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


def run_full_analysis(
    segments: list[Segment],
    settings: dict,
) -> list[AnalysisResult]:
    """Run both filler and error detection, returning combined results."""
    filler_words = settings.get("filler_words", [])
    trigger_words = settings.get("error_trigger_words", [])

    fillers = detect_fillers(segments, filler_words)
    errors = detect_errors(segments, trigger_words)

    return fillers + errors
