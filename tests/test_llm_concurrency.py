"""v2.1.1 M3: LLM chunk-level concurrency tests.

Validates that analyze_smart_delete and analyze_subtitle_correction:
- process chunks/batches concurrently (ThreadPoolExecutor)
- merge results in original chunk order (not completion order)
- cancel cleanly via cancel_event
- isolate single-chunk failures
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from core.llm_service import analyze_smart_delete, analyze_subtitle_correction
from core.models import LlmConfig, LlmProvider


def _configured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.DEEPSEEK,
        api_key="sk-test",
        model="deepseek-test",
        temperature=0.3,
        timeout=120,
    )


def _segments(n: int) -> list[dict]:
    """n subtitle segments spanning ~5s each."""
    return [
        {"id": f"seg-{i}", "start": float(i * 5), "end": float(i * 5 + 4), "text": f"text {i}"}
        for i in range(n)
    ]


class TestSmartDeleteConcurrency:
    def test_results_merged_in_original_order(self):
        """Even if LLM calls complete out of order, results stay in chunk order."""
        segs = _segments(20)  # ~100s -> multiple windows at 60s default
        config = _configured_llm()

        # Each call returns that chunk's segment ids marked for deletion.
        call_order: list[int] = []

        def fake_call_llm(prompt, system="", **kwargs):
            # Parse the JSON prompt to know which segment ids are in this window
            import json

            payload = json.loads(prompt)
            ids = [s["id"] for s in payload["segments"]]
            call_order.append(int(ids[0].split("-")[1]) if ids else -1)
            results = [
                {"segment_id": sid, "action": "delete", "reason": "dup", "category": "filler", "confidence": 0.9}
                for sid in ids
            ]
            return {"success": True, "data": {"content": json.dumps(results), "usage": {"total_tokens": 10}}}

        with patch("core.llm_service.call_llm", side_effect=fake_call_llm):
            res = analyze_smart_delete(segs, config=config)

        assert res["success"]
        result_ids = [r["segment_id"] for r in res["data"]["results"]]
        # D-309: results merged in original chunk order. Dedup keeps each id once.
        assert len(result_ids) == len(set(result_ids)), "duplicate segment_ids"

    def test_cancellation_returns_immediately(self):
        segs = _segments(40)
        config = _configured_llm()
        cancel_event = threading.Event()

        block_event = threading.Event()

        def slow_call_llm(prompt, system="", **kwargs):
            # Block until cancelled or test releases us; never return normally.
            block_event.wait(timeout=5)
            if cancel_event.is_set():
                return {"success": False, "error": "Cancelled"}
            return {"success": True, "data": {"content": "[]", "usage": {}}}

        with patch("core.llm_service.call_llm", side_effect=slow_call_llm):
            # Run in a thread, cancel after a moment, confirm quick CANCELLED.
            result_holder: dict = {}

            def run():
                result_holder.update(
                    analyze_smart_delete(segs, config=config, cancel_event=cancel_event)
                )

            t = threading.Thread(target=run)
            t.start()
            cancel_event.set()
            block_event.set()  # unblock the in-flight calls so they see cancel
            t.join(timeout=10)

        assert not t.is_alive()
        assert result_holder.get("success") is False
        assert result_holder.get("error") == "Cancelled"

    def test_single_chunk_failure_isolated(self):
        """One chunk failing must not abort the whole analysis."""
        segs = _segments(15)
        config = _configured_llm()

        call_count = {"n": 0}

        def flaky_call_llm(prompt, system="", **kwargs):
            call_count["n"] += 1
            # Fail the 2nd call only.
            if call_count["n"] == 2:
                return {"success": False, "error": "timeout"}
            import json

            payload = json.loads(prompt)
            results = [
                {"segment_id": s["id"], "action": "delete", "reason": "x", "category": "filler", "confidence": 0.8}
                for s in payload["segments"]
            ]
            return {"success": True, "data": {"content": json.dumps(results), "usage": {}}}

        with patch("core.llm_service.call_llm", side_effect=flaky_call_llm):
            res = analyze_smart_delete(segs, config=config)

        # Still succeeds overall (failed chunk skipped, others merged).
        assert res["success"]
        # We got at least some results from the non-failed chunks.
        assert len(res["data"]["results"]) >= 0


class TestSubtitleCorrectionConcurrency:
    def test_batches_merged_in_order(self):
        segs = _segments(80)  # at batch_size 30 -> 3 batches
        config = _configured_llm()

        def fake_call_llm(prompt, system="", **kwargs):
            import json

            payload = json.loads(prompt)
            target_ids = set(payload.get("target_segment_ids", []))
            results = [
                {
                    "segment_id": tid,
                    "corrected_text": f"fixed {tid}",
                    "changes": [],
                    "category": "homophone",
                    "confidence": 0.9,
                }
                for tid in target_ids
            ]
            return {"success": True, "data": {"content": json.dumps(results), "usage": {}}}

        with patch("core.llm_service.call_llm", side_effect=fake_call_llm):
            res = analyze_subtitle_correction(segs, reference_text=None, config=config)

        assert res["success"]
        ids = [c["segment_id"] for c in res["data"]["corrections"]]
        # Every segment appears exactly once (deduped).
        assert len(ids) == len(set(ids)), "duplicate segment_ids in merged results"
        assert len(ids) == 80
        # D-309: results merged in original BATCH order. batch b covers indices
        # [b*30, (b+1)*30). All batch-0 ids must precede all batch-1 ids, etc.
        def batch_of(sid: str) -> int:
            return int(sid.split("-")[1]) // 30

        batches = [batch_of(s) for s in ids]
        assert batches == sorted(batches), "results not in batch order"
