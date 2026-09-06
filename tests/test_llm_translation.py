"""v3.0.4 M1-2 (P1-3): analyze_subtitle_translation batch pipeline tests.

Validates the translation pipeline against SPEC M1-2:
- batch windows (llm_correction_batch_size) shrunk by llm_max_batch_chars
- reverse coverage validation (full-output conservation): missing /
  unknown / duplicated output ids fail the batch, and the whole task
  fails after the single retry (zero persistence upstream)
- happy path: translations merged in original segment order
- sustained 429 -> serial fallback (correction semantics)
- 4-layer JSON parsing for non-json_mode providers (bad JSON / fence /
  prefix-suffix noise)
- cancellation mid-run: completed batches produce no merged output
- opaque ids (t1..tN) never leak real ids; reverse-mapped on return
- context = SOURCE text +/- llm_correction_context_window in each payload

Mock style follows tests/test_llm_phase4b.py + tests/test_llm_concurrency.py.
"""

from __future__ import annotations

import json
import threading

from core import llm_service
from core.llm_service import analyze_subtitle_translation
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


def _unconfigured_llm() -> LlmConfig:
    return LlmConfig(
        provider=LlmProvider.CUSTOM,
        base_url="",
        api_key="",
        model="",
    )


def _segments(n: int, text_template: str = "text {i}") -> list[dict]:
    """n source segments in the handler shape (SPEC M1-2)."""
    return [
        {
            "segment_id": f"seg-{i:03d}",
            "start": float(i * 5),
            "end": float(i * 5 + 4),
            "text": text_template.format(i=i),
        }
        for i in range(n)
    ]


def _parse_payload(prompt: str) -> dict:
    return json.loads(prompt)


def _target_texts(payload: dict) -> list[str]:
    """Source texts of the batch's target segments, in target-list order."""
    by_id = {s["id"]: s["text"] for s in payload["segments"]}
    return [by_id[t] for t in payload["target_segment_ids"] if t in by_id]


def _perfect_translator(captured: list[str] | None = None):
    """Mock LLM echoing every target id back with a translation."""

    def fake_call_llm(prompt, system="", **kwargs):
        if captured is not None:
            captured.append(prompt)
        payload = _parse_payload(prompt)
        results = [
            {"segment_id": t, "translated_text": f"EN[{t}]"}
            for t in payload["target_segment_ids"]
        ]
        return {
            "success": True,
            "data": {
                "content": json.dumps(results),
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            },
        }

    return fake_call_llm


class _WarningLog:
    """Capture loguru WARNING+ messages emitted by the service logger."""

    def __enter__(self) -> list[str]:
        self.messages: list[str] = []
        self.handler_id = llm_service.logger.add(
            lambda m: self.messages.append(str(m)), level="WARNING"
        )
        return self.messages

    def __exit__(self, *exc_info) -> None:
        llm_service.logger.remove(self.handler_id)


# ================================================================
# Guard clauses
# ================================================================


class TestTranslationGuards:
    def test_not_configured(self):
        result = analyze_subtitle_translation(
            _segments(1), "English", config=_unconfigured_llm()
        )
        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    def test_empty_segments(self):
        result = analyze_subtitle_translation([], "English", config=_configured_llm())
        assert result["success"] is False
        assert result["error"] == "No segments to translate"

    def test_empty_target_language(self):
        result = analyze_subtitle_translation(
            _segments(1), "  ", config=_configured_llm()
        )
        assert result["success"] is False
        assert result["error"] == "Empty target language"


# ================================================================
# Batch window construction (batch size + char budget)
# ================================================================


class TestTranslationBatchWindows:
    def test_batch_size_partitions_windows(self, monkeypatch):
        """Default batch size 30 partitions 70 segments into 30/30/10."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        captured: list[str] = []
        monkeypatch.setattr(
            "core.llm_service.call_llm", _perfect_translator(captured)
        )

        result = analyze_subtitle_translation(
            _segments(70), "English", config=_configured_llm()
        )

        assert result["success"] is True
        assert len(captured) == 3
        sizes = sorted(len(_parse_payload(p)["target_segment_ids"]) for p in captured)
        assert sizes == [10, 30, 30]
        assert result["data"]["ledger"]["total"] == 3

    def test_char_budget_shrinks_batches(self, monkeypatch):
        """Large texts exceed llm_max_batch_chars -> windows shrink below 30."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {"llm_max_batch_chars": 60},
        )
        captured: list[str] = []
        monkeypatch.setattr(
            "core.llm_service.call_llm", _perfect_translator(captured)
        )

        # 10 segments x 10 chars, budget 60 -> 6 + 4 (first segment always
        # included even when it alone saturates the budget).
        result = analyze_subtitle_translation(
            _segments(10, text_template="0123456789"), "English",
            config=_configured_llm(),
        )

        assert result["success"] is True
        assert len(captured) == 2
        sizes = sorted(len(_parse_payload(p)["target_segment_ids"]) for p in captured)
        assert sizes == [4, 6]


# ================================================================
# Reverse coverage validation (full-output conservation)
# ================================================================


class TestTranslationReverseCoverage:
    def test_missing_id_batch_fails_after_retry(self, monkeypatch):
        """Output missing a target id (untranslated) -> retry -> task fails."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        calls = {"n": 0}

        def dropper(prompt, system="", **kwargs):
            calls["n"] += 1
            payload = _parse_payload(prompt)
            tids = payload["target_segment_ids"]
            results = [
                {"segment_id": t, "translated_text": f"EN[{t}]"} for t in tids[:-1]
            ]
            return {
                "success": True,
                "data": {"content": json.dumps(results), "usage": {}},
            }

        monkeypatch.setattr("core.llm_service.call_llm", dropper)

        with _WarningLog() as warnings:
            result = analyze_subtitle_translation(
                _segments(3), "English", config=_configured_llm()
            )

        assert result["success"] is False
        assert "uncovered" in result["error"]
        # exactly one retry, still violated
        assert calls["n"] == 2
        assert any("missing ids" in w for w in warnings)
        ledger = result["data"]["ledger"]
        assert ledger["failed"] == [0]
        # failed batch contributes ALL its target ids as uncovered
        assert ledger["uncovered_segment_ids"] == ["seg-000", "seg-001", "seg-002"]

    def test_unknown_id_batch_fails(self, monkeypatch):
        """Output containing an id outside the target set -> task fails."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        calls = {"n": 0}

        def inventor(prompt, system="", **kwargs):
            calls["n"] += 1
            payload = _parse_payload(prompt)
            results = [
                {"segment_id": t, "translated_text": f"EN[{t}]"}
                for t in payload["target_segment_ids"]
            ]
            results.append({"segment_id": "t99", "translated_text": "hallucinated"})
            return {
                "success": True,
                "data": {"content": json.dumps(results), "usage": {}},
            }

        monkeypatch.setattr("core.llm_service.call_llm", inventor)

        with _WarningLog() as warnings:
            result = analyze_subtitle_translation(
                _segments(2), "English", config=_configured_llm()
            )

        assert result["success"] is False
        assert calls["n"] == 2  # initial + retry
        assert any("unknown ids" in w for w in warnings)
        assert result["data"]["ledger"]["failed"] == [0]

    def test_duplicate_id_batch_fails(self, monkeypatch):
        """Output repeating a target id (merge/split) -> task fails."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        calls = {"n": 0}

        def duplicator(prompt, system="", **kwargs):
            calls["n"] += 1
            payload = _parse_payload(prompt)
            tids = payload["target_segment_ids"]
            results = [
                {"segment_id": t, "translated_text": f"EN[{t}]"} for t in tids
            ]
            results.append({"segment_id": tids[0], "translated_text": "EN[again]"})
            return {
                "success": True,
                "data": {"content": json.dumps(results), "usage": {}},
            }

        monkeypatch.setattr("core.llm_service.call_llm", duplicator)

        with _WarningLog() as warnings:
            result = analyze_subtitle_translation(
                _segments(2), "English", config=_configured_llm()
            )

        assert result["success"] is False
        assert calls["n"] == 2
        assert any("duplicate ids" in w for w in warnings)
        assert result["data"]["ledger"]["failed"] == [0]

    def test_retry_recovers_coverage_violation(self, monkeypatch):
        """First attempt violates conservation, retry completes -> success."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        calls = {"n": 0}

        def flaky(prompt, system="", **kwargs):
            calls["n"] += 1
            payload = _parse_payload(prompt)
            tids = payload["target_segment_ids"]
            if calls["n"] == 1:
                tids = tids[:-1]  # drop last on the first attempt only
            results = [
                {"segment_id": t, "translated_text": f"EN[{t}]"} for t in tids
            ]
            return {
                "success": True,
                "data": {"content": json.dumps(results), "usage": {}},
            }

        monkeypatch.setattr("core.llm_service.call_llm", flaky)

        result = analyze_subtitle_translation(
            _segments(3), "English", config=_configured_llm()
        )

        assert result["success"] is True
        assert calls["n"] == 2
        ledger = result["data"]["ledger"]
        assert ledger["retried_ok"] == 1
        assert ledger["succeeded"] == 0
        assert ledger["failed"] == []
        assert [t["segment_id"] for t in result["data"]["translations"]] == [
            "seg-000",
            "seg-001",
            "seg-002",
        ]


# ================================================================
# Happy path: conservation + original order + ledger
# ================================================================


class TestTranslationHappyPath:
    def test_full_conservation_original_order(self, monkeypatch):
        """All batches succeed -> every segment translated, input order kept
        even when the LLM answers in reverse within each batch."""
        monkeypatch.setattr(
            llm_service, "load_settings", lambda: {"llm_correction_batch_size": 4}
        )

        def reversed_translator(prompt, system="", **kwargs):
            payload = _parse_payload(prompt)
            results = [
                {"segment_id": t, "translated_text": f"EN[{t}]"}
                for t in reversed(payload["target_segment_ids"])
            ]
            return {
                "success": True,
                "data": {
                    "content": json.dumps(results),
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", reversed_translator)

        result = analyze_subtitle_translation(
            _segments(10), "English", config=_configured_llm()
        )

        assert result["success"] is True
        translations = result["data"]["translations"]
        assert [t["segment_id"] for t in translations] == [
            f"seg-{i:03d}" for i in range(10)
        ]
        assert all(t["translated_text"].startswith("EN[") for t in translations)
        # output entries carry exactly segment_id + translated_text
        assert all(set(t.keys()) == {"segment_id", "translated_text"} for t in translations)
        ledger = result["data"]["ledger"]
        assert ledger == {
            "total": 3,
            "succeeded": 3,
            "retried_ok": 0,
            "failed": [],
            "uncovered_segment_ids": [],
        }
        # token usage accumulated across batches
        assert result["data"]["token_usage"] == {
            "prompt_tokens": 21,
            "completion_tokens": 9,
            "total_tokens": 30,
        }

    def test_ledger_json_serializable_for_event_payload(self, monkeypatch):
        """Ledger must serialize into an event payload (correction habit)."""
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        monkeypatch.setattr("core.llm_service.call_llm", _perfect_translator())

        result = analyze_subtitle_translation(
            _segments(2), "English", config=_configured_llm()
        )

        assert result["success"] is True
        serialized = json.dumps(result["data"]["ledger"])
        assert set(json.loads(serialized).keys()) == {
            "total",
            "succeeded",
            "retried_ok",
            "failed",
            "uncovered_segment_ids",
        }

    def test_progress_cb_batch_granularity(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "load_settings", lambda: {"llm_correction_batch_size": 2}
        )
        monkeypatch.setattr("core.llm_service.call_llm", _perfect_translator())
        events: list[tuple[float, str]] = []

        result = analyze_subtitle_translation(
            _segments(6),
            "English",
            config=_configured_llm(),
            progress_cb=lambda pct, msg: events.append((pct, msg)),
        )

        assert result["success"] is True
        pcts = sorted(pct for pct, _ in events)
        assert pcts[0] == (1 / 3) * 100
        assert pcts[1] == (2 / 3) * 100
        assert pcts[-1] == 100.0
        assert events[-1][1].startswith("Completed: 6 translations")


# ================================================================
# 429 -> serial fallback + concurrency pool
# ================================================================


class TestTranslationRateLimitFallback:
    def test_sustained_429_switches_to_serial(self, monkeypatch):
        """Three consecutive rate-limited batch failures (after their retry)
        switch the remaining batches to serial processing (AR-2 semantics);
        the exhausted batches stay failed -> the whole task fails."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {"llm_correction_batch_size": 2, "llm_concurrency": 1},
        )
        calls = {"n": 0}
        served_after_fallback: list[list[str]] = []

        def rate_limited_then_ok(prompt, system="", **kwargs):
            calls["n"] += 1
            if calls["n"] <= 6:
                # batches 0-2 x (initial + retry) all rate limited
                return {"success": False, "error": "Rate limited (attempt 1)"}
            served_after_fallback.append(_target_texts(_parse_payload(prompt)))
            return _perfect_translator()(prompt, system, **kwargs)

        monkeypatch.setattr("core.llm_service.call_llm", rate_limited_then_ok)

        with _WarningLog() as warnings:
            result = analyze_subtitle_translation(
                _segments(8), "English", config=_configured_llm()
            )

        # degradation path triggered (same log line as the correction skeleton)
        assert any("switching remaining" in w for w in warnings)
        assert "switching remaining 1 batches to serial" in "".join(warnings)
        # batch 3 was processed serially after the switch. Depending on the
        # worker/consumer race it may also have run once inside the pool
        # before the break (its pool result is discarded); the serial pass
        # is always the last call.
        assert calls["n"] in (7, 8)
        assert served_after_fallback
        assert served_after_fallback[-1] == ["text 6", "text 7"]
        # task fails: batches 0-2 exhausted their single retry
        assert result["success"] is False
        ledger = result["data"]["ledger"]
        assert ledger["total"] == 4
        assert ledger["failed"] == [0, 1, 2]
        assert ledger["succeeded"] == 1  # batch 3, serial
        assert ledger["uncovered_segment_ids"] == [f"seg-{i:03d}" for i in range(6)]

    def test_concurrent_pool_runs_batches_in_parallel(self, monkeypatch):
        """The llm_concurrency pool dispatches batches concurrently (a
        serialized pool would trip the barrier timeout)."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {"llm_correction_batch_size": 2, "llm_concurrency": 3},
        )
        barrier = threading.Barrier(3, timeout=10)

        def gated_translator(prompt, system="", **kwargs):
            barrier.wait()
            return _perfect_translator()(prompt, system, **kwargs)

        monkeypatch.setattr("core.llm_service.call_llm", gated_translator)

        result = analyze_subtitle_translation(
            _segments(6), "English", config=_configured_llm()
        )

        assert result["success"] is True
        assert len(result["data"]["translations"]) == 6
        assert result["data"]["ledger"]["succeeded"] == 3


# ================================================================
# Layered JSON parsing (non-json_mode providers)
# ================================================================


class TestTranslationLayeredParsing:
    def _run(self, monkeypatch, content_fn):
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})

        def fake_call_llm(prompt, system="", **kwargs):
            payload = _parse_payload(prompt)
            return {
                "success": True,
                "data": {"content": content_fn(payload), "usage": {}},
            }

        monkeypatch.setattr("core.llm_service.call_llm", fake_call_llm)
        return analyze_subtitle_translation(
            _segments(2), "English", config=_configured_llm()
        )

    def test_bad_json_unsalvageable_fails(self, monkeypatch):
        calls = {"n": 0}

        def garbage(payload):
            calls["n"] += 1
            return "sorry I cannot do that [[["

        result = self._run(monkeypatch, garbage)
        assert result["success"] is False
        assert calls["n"] == 2  # initial + one retry
        assert result["data"]["ledger"]["failed"] == [0]

    def test_fenced_code_block_succeeds(self, monkeypatch):
        def fenced(payload):
            entries = json.dumps(
                [{"segment_id": t, "translated_text": f"EN[{t}]"}
                 for t in payload["target_segment_ids"]]
            )
            return f"```json\n{entries}\n```"

        result = self._run(monkeypatch, fenced)
        assert result["success"] is True
        assert [t["segment_id"] for t in result["data"]["translations"]] == [
            "seg-000",
            "seg-001",
        ]

    def test_prefix_suffix_noise_succeeds(self, monkeypatch):
        def noisy(payload):
            entries = json.dumps(
                [{"segment_id": t, "translated_text": f"EN[{t}]"}
                 for t in payload["target_segment_ids"]]
            )
            return f"Sure, here it is:\n{entries}\nHope this helps!"

        result = self._run(monkeypatch, noisy)
        assert result["success"] is True
        assert len(result["data"]["translations"]) == 2


# ================================================================
# Cancellation (correction-aligned semantics)
# ================================================================


class TestTranslationCancellation:
    def test_cancel_midway_returns_bare_cancelled(self, monkeypatch):
        """Cancelled mid-run -> bare {"success": False, "error": "Cancelled"}
        with NO merged translations, so already-completed batches cannot
        produce any persistence side effect upstream (M1-5 table)."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {"llm_correction_batch_size": 2, "llm_concurrency": 1},
        )
        first_done = threading.Event()
        gate = threading.Event()
        served: list[str] = []

        def staged_translator(prompt, system="", **kwargs):
            served.append(prompt)
            if first_done.is_set():
                gate.wait(timeout=5)
                return {"success": False, "error": "Cancelled"}
            outcome = _perfect_translator()(prompt, system, **kwargs)
            first_done.set()
            return outcome

        monkeypatch.setattr("core.llm_service.call_llm", staged_translator)

        cancel_event = threading.Event()
        result_holder: dict = {}

        def run():
            result_holder.update(
                analyze_subtitle_translation(
                    _segments(6),
                    "English",
                    config=_configured_llm(),
                    cancel_event=cancel_event,
                )
            )

        t = threading.Thread(target=run)
        t.start()
        assert first_done.wait(timeout=5), "first batch never completed"
        cancel_event.set()
        gate.set()
        t.join(timeout=10)

        assert not t.is_alive()
        # batch 0 fully completed before the cancel; batch 1 either reached
        # the mock (blocked on the gate) or tripped the per-batch cancel
        # check in _call_batch before it -> 1 or 2 mock invocations.
        assert 1 <= len(served) <= 2
        # bare cancel envelope: no merged output of any completed batch
        assert result_holder == {"success": False, "error": "Cancelled"}


# ================================================================
# Opaque ids + source-text context window
# ================================================================


class TestTranslationOpaqueIdsAndContext:
    def test_payload_hides_real_ids_and_reverse_maps_output(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "load_settings", lambda: {"llm_correction_batch_size": 4}
        )
        captured: list[str] = []
        monkeypatch.setattr(
            "core.llm_service.call_llm", _perfect_translator(captured)
        )

        result = analyze_subtitle_translation(
            _segments(10), "English", config=_configured_llm()
        )

        assert result["success"] is True
        assert len(captured) == 3
        for prompt in captured:
            payload = _parse_payload(prompt)
            for item in payload["segments"]:
                # opaque ids only, no timestamps leaked
                assert item["id"].startswith("t") and item["id"][1:].isdigit()
                assert set(item.keys()) == {"id", "text"}
            # real segment ids never appear anywhere in the raw payload
            assert "seg-00" not in prompt
        # ... while the returned translations carry real ids
        assert [t["segment_id"] for t in result["data"]["translations"]] == [
            f"seg-{i:03d}" for i in range(10)
        ]

    def test_context_window_carries_source_text(self, monkeypatch):
        """Each batch payload includes +/- ctx adjacent SOURCE texts as
        context (no finalized translations -- SPEC M1-2 ruling)."""
        monkeypatch.setattr(
            llm_service, "load_settings", lambda: {"llm_correction_batch_size": 4}
        )
        captured: list[str] = []
        monkeypatch.setattr(
            "core.llm_service.call_llm", _perfect_translator(captured)
        )

        result = analyze_subtitle_translation(
            _segments(10), "English", config=_configured_llm()
        )

        assert result["success"] is True
        payloads = [_parse_payload(p) for p in captured]

        def find_batch(first_target_text: str) -> dict:
            for p in payloads:
                if _target_texts(p)[:1] == [first_target_text]:
                    return p
            raise AssertionError(f"batch starting with {first_target_text!r} not found")

        # first batch: window [0,4) + forward ctx 5 -> 9 source segments,
        # 4 targets, context = texts 4..8 (source only)
        first = find_batch("text 0")
        assert len(first["target_segment_ids"]) == 4
        all_texts = {s["text"] for s in first["segments"]}
        target_texts = set(_target_texts(first))
        assert all_texts - target_texts == {f"text {i}" for i in range(4, 9)}

        # middle batch: window [4,8) +/- ctx -> full-range context
        middle = find_batch("text 4")
        middle_target_texts = set(_target_texts(middle))
        middle_all = {s["text"] for s in middle["segments"]}
        assert middle_all - middle_target_texts == {
            "text 0", "text 1", "text 2", "text 3", "text 8", "text 9",
        }
