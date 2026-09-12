"""v3.0.5 R5.5 (M5.5, controlled point (a)): correction-side cancel polling.

The subtitle-correction pipeline's ``with ThreadPoolExecutor + as_completed``
cancel mechanism was restructured to a bounded 1s poll loop with a
non-blocking finally-shutdown -- the pattern proven on the translation side
by v3.0.4 smoke-fix 1c. Cancel latency drops from "next batch completion"
(tens of seconds on big blocked batches) to the poll interval.

Covered matrix (SPEC M5.5 focus-3 state table, >=4 tests):
- cancel while every in-flight batch is blocked (1s latency assertion)
- happy-path aggregation equivalence (corrections content + token_usage
  + ledger set, list order NOT locked)
- SG-2 (i): serial fallback x cancel -> serial head returns, pending
  batches' mock call count stays zero
- SG-2 (ii): 429 downgrade inside the poll loop -> serial loop takes over,
  both loops exit without hanging
- MF2-1 lock face: serial x parse-failure still records failed under the
  frozen not-corrections ledger criterion (poll restructure must NOT change
  the v3.0.4 bookkeeping asymmetry; translation-side error judging is NOT
  copied over).
"""

from __future__ import annotations

import json
import threading
import time

from core import llm_service
from core.llm_service import analyze_subtitle_correction
from core.models import LlmConfig, LlmProvider

# ================================================================
# Helpers
# ================================================================


def _configured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.DEEPSEEK,
        api_key="sk-test",
        model="deepseek-test",
        temperature=0.3,
        timeout=120,
    )


def _segments(n: int) -> list[dict]:
    return [
        {
            "id": f"seg-{i:03d}",
            "start": float(i * 5),
            "end": float(i * 5 + 4),
            "text": f"text {i}",
        }
        for i in range(n)
    ]


def _echo_corrector(block: threading.Event | None = None):
    """Mock LLM echoing the prompt's opaque target ids as corrections;
    optionally blocks until released (60s barrier)."""

    def fake_call_llm(prompt, system="", **kwargs):
        if block is not None:
            block.wait(timeout=60)
        payload = json.loads(prompt)
        results = [
            {
                "segment_id": tid,
                "corrected_text": f"fixed {tid}",
                "changes": [],
                "category": "homophone",
                "confidence": 0.9,
            }
            for tid in payload.get("target_segment_ids", [])
        ]
        return {
            "success": True,
            "data": {
                "content": json.dumps(results),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        }

    return fake_call_llm


# ================================================================
# Cancel latency (1s poll assertion, barrier method)
# ================================================================


class TestCancelLatency:
    def test_cancel_observed_while_batches_blocked(self, monkeypatch):
        """Every in-flight batch blocks on a 60s barrier; cancel fires at
        t=0.3s. The pipeline must return Cancelled within ~2s (poll interval
        1s + scheduling margin) instead of waiting for the barrier.
        Pre-R5.5, as_completed + the with-block shutdown(wait=True) held the
        caller until the barrier released."""
        block = threading.Event()
        monkeypatch.setattr("core.llm_service.call_llm", _echo_corrector(block))
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})

        cancel_event = threading.Event()
        outcome: dict = {}

        def run():
            outcome["result"] = analyze_subtitle_correction(
                _segments(6),
                reference_text=None,
                config=_configured_llm(),
                cancel_event=cancel_event,
            )

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        time.sleep(0.3)
        t_cancel = time.monotonic()
        cancel_event.set()
        worker.join(timeout=5.0)

        assert not worker.is_alive(), "pipeline did not observe cancel promptly"
        assert time.monotonic() - t_cancel < 4.0, "cancel latency exceeded poll budget"
        result = outcome["result"]
        assert result["success"] is False
        assert result["error"] == "Cancelled"
        # bare envelope: R5.5 ruling 5 keeps the correction-side cancel
        # without the token_usage data payload (no key-level additions here)
        assert "data" not in result
        # in-flight HTTP calls are abandoned, not waited out
        block.set()
        worker.join(timeout=2.0)

    def test_no_cancel_completes_normally_with_aggregation_equivalence(self, monkeypatch):
        """The polling restructure preserves the happy path: corrections
        content, token_usage totals and the ledger set are locked (list
        order is not -- wait() completion order differs from as_completed)."""
        monkeypatch.setattr("core.llm_service.call_llm", _echo_corrector())
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})

        result = analyze_subtitle_correction(
            _segments(80),  # batch_size 30 -> 3 batches
            reference_text=None,
            config=_configured_llm(),
        )

        assert result["success"] is True
        data = result["data"]
        # corrections content: every target corrected exactly once, merged
        # in original batch order (batch b covers [b*30, (b+1)*30))
        ids = [c["segment_id"] for c in data["corrections"]]
        assert sorted(ids) == [f"seg-{i:03d}" for i in range(80)]
        batches = [int(sid.split("-")[1]) // 30 for sid in ids]
        assert batches == sorted(batches), "results not in batch order"
        # token_usage totals: 3 successful calls x per-call usage
        assert data["token_usage"] == {
            "prompt_tokens": 3,
            "completion_tokens": 3,
            "total_tokens": 6,
        }
        # ledger set
        assert data["ledger"]["total"] == 3
        assert data["ledger"]["succeeded"] == 3
        assert data["ledger"]["retried_ok"] == 0
        assert data["ledger"]["failed"] == []
        assert data["ledger"]["uncovered_segment_ids"] == []


# ================================================================
# SG-2: serial fallback x cancel / 429 downgrade interweaving
# (concurrency 1 keeps the pool deterministic: batches 0-2 exhaust the
# 429 budget before queued futures 3-4 ever start)
# ================================================================


def _rate_limit_then(mode: str, cancel_event: threading.Event | None = None):
    """Calls 1-6 (batches 0-2, each with its automatic retry) return a
    sustained 429 error; calls >= 7 (the serial-fallback batches) switch to
    ``mode``: "echo" -> valid corrections, "unparseable" -> success with
    content the layer parser rejects. Optionally sets the cancel event on
    the 6th call (right before the serial loop starts)."""
    calls = {"n": 0}

    def fake_call_llm(prompt, system="", **kwargs):
        calls["n"] += 1
        if calls["n"] <= 6:
            if cancel_event is not None and calls["n"] == 6:
                cancel_event.set()
            return {"success": False, "error": "Rate limited (429)"}
        if mode == "unparseable":
            return {"success": True, "data": {"content": "<<<<>>>>", "usage": {}}}
        payload = json.loads(prompt)
        results = [
            {
                "segment_id": tid,
                "corrected_text": f"fixed {tid}",
                "changes": [],
                "category": "homophone",
                "confidence": 0.9,
            }
            for tid in payload.get("target_segment_ids", [])
        ]
        return {
            "success": True,
            "data": {"content": json.dumps(results), "usage": {}},
        }

    return fake_call_llm, calls


class TestSerialFallbackInterweaving:
    def _settings(self):
        return lambda: {"llm_concurrency": 1}

    def test_cancel_after_downgrade_pending_batches_never_executed(self, monkeypatch):
        """SG-2 (i): 429 downgrade lands with pending batches 3-4; cancel is
        set on the last pool call. The serial loop's head check returns
        Cancelled immediately and the pending batches' mock call count stays
        at the 6 pool-phase calls (zero serial executions)."""
        cancel_event = threading.Event()
        fake, calls = _rate_limit_then("echo", cancel_event=cancel_event)
        monkeypatch.setattr("core.llm_service.call_llm", fake)
        monkeypatch.setattr(llm_service, "load_settings", self._settings())

        result = analyze_subtitle_correction(
            _segments(150),  # 5 batches
            reference_text=None,
            config=_configured_llm(),
            cancel_event=cancel_event,
        )

        assert result["success"] is False
        assert result["error"] == "Cancelled"
        assert calls["n"] == 6, "serial loop executed pending batches after cancel"

    def test_429_downgrade_enters_serial_both_loops_exit(self, monkeypatch):
        """SG-2 (ii): three consecutive rate-limited digests inside the poll
        loop set the downgrade flag and break BOTH loops; the serial loop
        takes over the pending batches and the task finishes cleanly (no
        hang, no CancelledError surfacing from the cancelled pool futures)."""
        fake, calls = _rate_limit_then("echo")
        monkeypatch.setattr("core.llm_service.call_llm", fake)
        monkeypatch.setattr(llm_service, "load_settings", self._settings())

        result = analyze_subtitle_correction(
            _segments(150),
            reference_text=None,
            config=_configured_llm(),
        )

        assert result["success"] is True
        data = result["data"]
        # batches 0-2 failed even after retry; 3-4 landed serially. The
        # serial loop's frozen not-corrections criterion (MF2-1) has no
        # plain-success bucket: a serial batch that succeeds on its first
        # attempt increments nothing (succeeded stays 0).
        assert data["ledger"]["failed"] == [0, 1, 2]
        assert data["ledger"]["succeeded"] == 0
        assert data["ledger"]["retried_ok"] == 0
        # corrections cover exactly the serial batches' targets
        ids = sorted(c["segment_id"] for c in data["corrections"])
        assert ids == [f"seg-{i:03d}" for i in range(90, 150)]
        assert data["ledger"]["uncovered_segment_ids"] == [
            f"seg-{i:03d}" for i in range(90)
        ]

    def test_serial_parse_failure_still_records_failed_mf2_1(self, monkeypatch):
        """MF2-1 lock face: in the serial loop a batch whose _call_batch
        returns error=None with empty corrections (parse returned None)
        must still be recorded failed under the frozen not-corrections
        criterion. Copying the translation-side error judgment over would
        mis-record these as retried_ok/succeeded and change the ledger set."""
        fake, _calls = _rate_limit_then("unparseable")
        monkeypatch.setattr("core.llm_service.call_llm", fake)
        monkeypatch.setattr(llm_service, "load_settings", self._settings())

        result = analyze_subtitle_correction(
            _segments(150),
            reference_text=None,
            config=_configured_llm(),
        )

        assert result["success"] is True
        data = result["data"]
        # not-corrections criterion: parse-None serial batches are failed
        assert data["ledger"]["failed"] == [0, 1, 2, 3, 4]
        assert data["ledger"]["succeeded"] == 0
        assert data["ledger"]["retried_ok"] == 0
        assert data["corrections"] == []
        assert data["ledger"]["uncovered_segment_ids"] == [
            f"seg-{i:03d}" for i in range(150)
        ]
