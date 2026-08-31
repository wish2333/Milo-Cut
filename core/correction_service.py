"""Subtitle correction domain (v3.0.0 M10, moved verbatim from ProjectService).

Single-direction dependency: CorrectionService -> ProjectService (holds the
project service instance; never the other way). All bridge envelopes and
method names are unchanged -- main.py's @expose methods delegate here.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.project_service import ProjectService

from core.models import AnalysisResult, Segment
from core.timeline_utils import reattach_words

logger = logging.getLogger(__name__)


class CorrectionService:
    """LLM subtitle correction storage / review / apply workflows."""

    def __init__(self, project_service: ProjectService) -> None:
        self._project = project_service

    def store_subtitle_corrections(
        self, corrections: list[dict], timeline_id: str
    ) -> dict:
        """Persist LLM subtitle corrections as AnalysisResult records (D-54).

        Instead of immediately mutating segment text (the old behavior), each
        correction is stored as an AnalysisResult with type=
        llm_subtitle_correction and its structured payload JSON-encoded in
        ``detail``. The frontend reviews them and calls accept/reject per item.

        Existing unreviewed corrections of the same type are cleared first so
        re-running P1 replaces the pending review set.

        Args:
            corrections: LLM output list (segment_id, corrected_text, changes,
                category, confidence).
            timeline_id: Target timeline.

        Returns:
            {"success": True, "data": {"stored_count": int}}
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        from uuid import uuid4

        tl = self._project._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        seg_map = {s.id: s for s in tl.transcript.segments}

        # Clear previously-pending corrections (avoid duplicates on re-run).
        kept_results = [
            r for r in tl.analysis.results
            if r.type != "llm_subtitle_correction"
        ]

        stored: list[AnalysisResult] = []
        for corr in corrections:
            seg_id = corr.get("segment_id")
            if not seg_id or seg_id not in seg_map:
                continue
            original_text = seg_map[seg_id].text
            corrected_text = str(corr.get("corrected_text", original_text))
            # Skip no-op corrections (LLM says "no change").
            if corrected_text.strip() == original_text.strip():
                continue
            result = AnalysisResult(
                id=f"corr-{seg_id}-{uuid4().hex[:8]}",
                type="llm_subtitle_correction",
                segment_ids=[seg_id],
                confidence=float(corr.get("confidence", 0.8)),
                detail=json.dumps(
                    {
                        "original_text": original_text,
                        "corrected_text": corrected_text,
                        "changes": corr.get("changes", []),
                        "category": corr.get("category", "none"),
                    },
                    ensure_ascii=False,
                ),
            )
            stored.append(result)

        new_results = kept_results + stored
        self._project._update_timeline_by_id(
            timeline_id,
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info(
            "Stored {} subtitle corrections for review (timeline {})",
            len(stored), timeline_id,
        )
        return {"success": True, "data": {"stored_count": len(stored)}}

    def get_subtitle_corrections(self, timeline_id: str) -> dict:
        """Read pending P1 corrections for a timeline (parsed detail JSON).

        Returns:
            {"success": True, "data": [correction_dict, ...]} where each dict
            has id, segment_id, confidence, original_text, corrected_text,
            changes, category, start, end (for time-link rendering).
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}


        tl = self._project._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        seg_map = {s.id: s for s in tl.transcript.segments}
        out: list[dict] = []
        for r in tl.analysis.results:
            if r.type != "llm_subtitle_correction":
                continue
            try:
                payload = json.loads(r.detail) if r.detail else {}
            except (ValueError, TypeError):
                payload = {}
            seg_id = r.segment_ids[0] if r.segment_ids else ""
            seg = seg_map.get(seg_id)
            out.append({
                "id": r.id,
                "segment_id": seg_id,
                "confidence": r.confidence,
                "original_text": payload.get("original_text", seg.text if seg else ""),
                "corrected_text": payload.get("corrected_text", ""),
                "changes": payload.get("changes", []),
                "category": payload.get("category", "none"),
                "start": seg.start if seg else 0.0,
                "end": seg.end if seg else 0.0,
            })
        return {"success": True, "data": out}

    def _parse_correction_result(self, result: AnalysisResult) -> dict | None:
        """Decode the detail JSON of a correction AnalysisResult."""
        if not result.detail:
            return None
        try:
            return json.loads(result.detail)
        except (ValueError, TypeError):
            return None

    def accept_subtitle_correction(self, result_id: str) -> dict:
        """Accept one correction: apply to segment.text + remove AnalysisResult.

        Args:
            result_id: The AnalysisResult id (``corr-<seg>-<hex>``).

        Returns:
            {"success": True, "data": {"segment_id": str}}
            {"success": False, "error": str} if not found.
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        from core.llm_service import (
            TimestampCorruptionError,
            _assert_timestamps_unchanged,
            _check_correction_confidence,
        )

        tl = self._project.active_timeline
        target = next(
            (r for r in tl.analysis.results if r.id == result_id), None
        )
        if target is None or target.type != "llm_subtitle_correction":
            return {"success": False, "error": f"Correction {result_id} not found"}

        payload = self._parse_correction_result(target)
        if payload is None:
            return {"success": False, "error": "Malformed correction detail"}

        seg_id = target.segment_ids[0] if target.segment_ids else ""
        seg = next((s for s in tl.transcript.segments if s.id == seg_id), None)
        if seg is None:
            return {"success": False, "error": f"Segment {seg_id} not found"}

        corrected_text = str(payload.get("corrected_text", seg.text))
        conf = _check_correction_confidence(seg.text, corrected_text)
        new_flags = {**seg.dirty_flags, "llm_corrected": True}
        if conf["low_confidence"]:
            new_flags["llm_low_confidence"] = True

        # v3.0.0 P4-1: re-align word-level timestamps against the corrected
        # text (keep unchanged regions, clear words when unreliable).
        new_words = reattach_words(
            seg.words, corrected_text, seg_start=seg.start, seg_end=seg.end
        )
        corrected_seg = seg.model_copy(
            update={"text": corrected_text, "dirty_flags": new_flags, "words": new_words}
        )

        # Timestamp assertion (defensive -- LLM should never alter timestamps).
        try:
            _assert_timestamps_unchanged(
                seg.start, seg.end, corrected_seg.start, corrected_seg.end,
                segment_id=seg.id,
            )
            new_segments = [
                corrected_seg if s.id == seg_id else s
                for s in tl.transcript.segments
            ]
        except TimestampCorruptionError:
            logger.warning("Timestamp corruption on accept, rollback segment %s", seg_id)
            new_segments = list(tl.transcript.segments)

        # Remove the accepted correction from analysis results.
        new_results = [r for r in tl.analysis.results if r.id != result_id]

        self._project._update_active_timeline(
            transcript=tl.transcript.model_copy(update={"segments": new_segments}),
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Accepted subtitle correction {} (seg {})", result_id, seg_id)
        return {"success": True, "data": {"segment_id": seg_id}}

    def reject_subtitle_correction(self, result_id: str) -> dict:
        """Reject one correction: remove AnalysisResult without touching text.

        Args:
            result_id: The AnalysisResult id.

        Returns:
            {"success": True, "data": {"segment_id": str}}
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self._project.active_timeline
        target = next(
            (r for r in tl.analysis.results if r.id == result_id), None
        )
        if target is None or target.type != "llm_subtitle_correction":
            return {"success": False, "error": f"Correction {result_id} not found"}

        seg_id = target.segment_ids[0] if target.segment_ids else ""
        new_results = [r for r in tl.analysis.results if r.id != result_id]
        self._project._update_active_timeline(
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Rejected subtitle correction {} (seg {})", result_id, seg_id)
        return {"success": True, "data": {"segment_id": seg_id}}

    def accept_high_confidence_corrections(
        self, timeline_id: str, threshold: float = 0.8
    ) -> dict:
        """Batch-accept all corrections with confidence >= threshold (D-52).

        Iterates the pending corrections, applying each qualifying one to
        segment.text and removing it from the analysis results. Corrections
        below the threshold remain pending for manual review.

        Args:
            timeline_id: Target timeline.
            threshold: Minimum confidence to auto-accept (default 0.8, D-68).

        Returns:
            {"success": True, "data": {"accepted_count": int, "remaining_count": int}}
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self._project._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        # Gather qualifying ids, then reuse the single-accept path so the
        # apply logic (confidence flag, timestamp assertion) stays unified.
        qualifying = [
            r.id for r in tl.analysis.results
            if r.type == "llm_subtitle_correction" and r.confidence >= threshold
        ]

        # Ensure the target timeline is active so accept_subtitle_correction
        # (which operates on active_timeline) hits the right timeline.
        if self._project._current.active_timeline_id != timeline_id:
            self._project._current = self._project._current.model_copy(
                update={"active_timeline_id": timeline_id}
            )

        accepted = 0
        for rid in qualifying:
            res = self.accept_subtitle_correction(rid)
            if res.get("success"):
                accepted += 1

        # Count remaining (active timeline may have changed during accepts).
        tl_after = self._project._current.get_timeline(timeline_id)
        remaining = sum(
            1 for r in tl_after.analysis.results
            if r.type == "llm_subtitle_correction"
        ) if tl_after else 0
        logger.info(
            "Batch-accepted {} high-confidence corrections (threshold {}, {})",
            accepted, threshold, "remaining" if remaining else "clean",
        )
        return {
            "success": True,
            "data": {"accepted_count": accepted, "remaining_count": remaining},
        }

    def clear_subtitle_corrections(self, timeline_id: str) -> dict:
        """Clear all pending P1 corrections for a timeline (D-50).

        Used when the user dismisses the review without per-item action.

        Returns:
            {"success": True, "data": {"cleared_count": int}}
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self._project._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        cleared = sum(1 for r in tl.analysis.results if r.type == "llm_subtitle_correction")
        if cleared == 0:
            return {"success": True, "data": {"cleared_count": 0}}

        new_results = [
            r for r in tl.analysis.results
            if r.type != "llm_subtitle_correction"
        ]
        self._project._update_timeline_by_id(
            timeline_id,
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Cleared {} subtitle corrections (timeline {})", cleared, timeline_id)
        return {"success": True, "data": {"cleared_count": cleared}}

    def apply_subtitle_corrections(self, corrections: list[dict]) -> dict:
        """Apply LLM subtitle corrections to the active timeline.

        Uses layered fault tolerance: does not fail entirely on partial
        mismatches. Matches by segment_id, applies what matches, and marks
        uncovered segments with dirty_flags.llm_uncovered.

        Args:
            corrections: List of dicts with segment_id, corrected_text,
                changes, category, confidence.

        Returns:
            {"success": True, "data": {corrected_count, uncovered_count,
             uncovered_ids, orphaned_count, partial}}
            {"success": False, "error": str} on complete mismatch.
        """
        if self._project._current is None:
            return {"success": False, "error": "No project is open"}

        from core.llm_service import (
            TimestampCorruptionError,
            _assert_timestamps_unchanged,
            _check_correction_confidence,
        )

        timeline = self._project.active_timeline
        seg_map = {s.id: s for s in timeline.transcript.segments}
        total = len(timeline.transcript.segments)

        # Match corrections to segments
        matched: list[tuple[Segment, dict]] = []
        uncovered_ids: list[str] = []

        for seg in timeline.transcript.segments:
            corr = next((c for c in corrections if c["segment_id"] == seg.id), None)
            if corr:
                matched.append((seg, corr))
            else:
                uncovered_ids.append(seg.id)

        extra_corrections = [c for c in corrections if c["segment_id"] not in seg_map]

        # Complete mismatch
        if len(matched) == 0 and total > 0:
            return {
                "success": False,
                "error": "No segment_id matched (LLM output completely mismatched)",
            }

        if len(matched) < total:
            logger.warning(
                f"Partial correction coverage: {len(matched)}/{total} segments matched, "
                f"{len(uncovered_ids)} uncovered, {len(extra_corrections)} orphaned"
            )

        # Apply corrections
        corr_map = {seg_id: corr for seg, corr in matched for seg_id in [seg.id]}
        new_segments: list[Segment] = []
        rolled_back_count = 0

        for seg in timeline.transcript.segments:
            corr = corr_map.get(seg.id)
            if corr:
                corrected_text = str(corr.get("corrected_text", seg.text))
                # Confidence check
                conf = _check_correction_confidence(seg.text, corrected_text)
                new_flags = {**seg.dirty_flags, "llm_corrected": True}
                if conf["low_confidence"]:
                    new_flags["llm_low_confidence"] = True

                # v3.0.0 P4-1: word reattachment (same semantics as the
                # single-accept path).
                new_words = reattach_words(
                    seg.words, corrected_text, seg_start=seg.start, seg_end=seg.end
                )
                corrected = seg.model_copy(
                    update={
                        "text": corrected_text,
                        "dirty_flags": new_flags,
                        "words": new_words,
                    }
                )

                # Timestamp assertion
                try:
                    _assert_timestamps_unchanged(
                        seg.start, seg.end, corrected.start, corrected.end,
                        segment_id=seg.id,
                    )
                    new_segments.append(corrected)
                except TimestampCorruptionError:
                    # Rollback this segment, keep original
                    rolled_back_count += 1
                    new_segments.append(seg)
            else:
                # Uncovered: keep original, mark for UI
                uncovered = seg.model_copy(
                    update={
                        "dirty_flags": {**seg.dirty_flags, "llm_uncovered": True}
                    }
                )
                new_segments.append(uncovered)

        # Update timeline: new segments + invalidate analysis
        self._project._update_active_timeline(
            transcript=timeline.transcript.model_copy(update={"segments": new_segments}),
            analysis=timeline.analysis.model_copy(update={"last_run": None}),
        )

        logger.info(
            f"Applied subtitle corrections: {len(matched)} matched, "
            f"{len(uncovered_ids)} uncovered, {rolled_back_count} rolled back"
        )

        return {
            "success": True,
            "data": {
                "corrected_count": len(matched) - rolled_back_count,
                "uncovered_count": len(uncovered_ids),
                "uncovered_ids": uncovered_ids,
                "orphaned_count": len(extra_corrections),
                "rolled_back_count": rolled_back_count,
                "partial": len(matched) < total,
            },
        }
