"""v3.0.0 M3: LLM reliability protocol tests (ledger / sanitize / SSRF / opaque ids)."""

from __future__ import annotations

import pytest

from core import llm_service
from core.llm_service import (
    BatchLedger,
    _build_opaque_id_mapping,
    _build_structured_user_message,
    _parse_json_response_layers,
    _sanitize_response,
    chunk_transcript_by_count,
    validate_base_url_security,
)
from core.models import LlmConfig, LlmProvider

# ---------------------------------------------------------------------------
# M3-1: BatchLedger
# ---------------------------------------------------------------------------

class TestBatchLedger:
    def test_ledger_defaults_and_serialization(self):
        ledger = BatchLedger(total=4)
        assert ledger.succeeded == 0
        assert ledger.failed == []
        assert ledger.uncovered_segment_ids == []
        d = ledger.to_dict()
        assert d["total"] == 4
        assert d["uncovered_segment_ids"] == []

    def test_uncovered_are_target_ids_of_failed_batches(self, monkeypatch):
        """One batch fails even after retry -> its targets are uncovered."""
        state = {"calls": 0}

        def fake_call_llm(prompt, system="", *, json_mode=False, config=None,
                          cancel_event=None, progress_cb=None):
            state["calls"] += 1
            if state["calls"] == 1:
                return {
                    "success": True,
                    "data": {
                        "content": '[{"segment_id": "t1", "action": "keep"}]',
                        "usage": {"total_tokens": 1},
                    },
                }
            return {"success": False, "error": "boom"}

        monkeypatch.setattr(llm_service, "call_llm", fake_call_llm)
        monkeypatch.setattr(llm_service, "load_settings", lambda: {
            "llm_smart_batch_size": 5, "llm_smart_overlap_size": 0,
            "llm_concurrency": 1, "llm_allow_local_urls": True,
        })
        config = LlmConfig(provider=LlmProvider.CUSTOM, base_url="https://x.example",
                           api_key="k", model="m")
        segs = [{"id": f"s{i}", "text": f"文本{i}", "start": float(i), "end": i + 1.0}
                for i in range(10)]
        res = llm_service.analyze_smart_delete(segs, config=config)
        assert res["success"]
        ledger = res["data"]["ledger"]
        assert ledger["total"] == 2
        assert len(ledger["failed"]) == 1
        # retried exactly once: 1 call for batch ok + 2 calls for failed batch
        assert state["calls"] == 3
        # uncovered = target ids of the failed batch (5 ids)
        assert len(ledger["uncovered_segment_ids"]) == 5
        assert ledger["succeeded"] + ledger["retried_ok"] + len(ledger["failed"]) == 2

    def test_retry_success_counts_retried_ok(self, monkeypatch):
        """First attempt fails, retry succeeds -> retried_ok == 1, no uncovered."""
        state = {"first": True}

        def fake_call_llm(prompt, system="", *, json_mode=False, config=None,
                          cancel_event=None, progress_cb=None):
            if state["first"]:
                state["first"] = False
                return {"success": False, "error": "transient"}
            return {
                "success": True,
                "data": {"content": "[]", "usage": {}},
            }

        monkeypatch.setattr(llm_service, "call_llm", fake_call_llm)
        monkeypatch.setattr(llm_service, "load_settings", lambda: {
            "llm_smart_batch_size": 10, "llm_smart_overlap_size": 0,
            "llm_concurrency": 1, "llm_allow_local_urls": True,
        })
        config = LlmConfig(provider=LlmProvider.CUSTOM, base_url="https://x.example",
                           api_key="k", model="m")
        segs = [{"id": "s0", "text": "a", "start": 0.0, "end": 1.0}]
        res = llm_service.analyze_smart_delete(segs, config=config)
        assert res["success"]
        assert res["data"]["ledger"]["retried_ok"] == 1
        assert res["data"]["ledger"]["uncovered_segment_ids"] == []


# ---------------------------------------------------------------------------
# M3-3: response sanitization
# ---------------------------------------------------------------------------

class TestSanitize:
    def test_strips_think_blocks(self):
        raw = "<think>让我想想...</think>\n[{\"segment_id\": \"s1\"}]"
        assert _sanitize_response(raw) == '[{"segment_id": "s1"}]'

    def test_strips_fences_and_prefix_noise(self):
        raw = "好的，结果如下：\n```json\n[{\"a\": 1}]\n```\n希望有帮助"
        assert _sanitize_response(raw) == '[{"a": 1}]'

    def test_layer5_integrated_into_parse(self):
        raw = "<think>deepseek-r1 reasoning...</think>```json\n[{\"segment_id\": \"s9\", \"action\": \"delete\"}]\n```"
        parsed = _parse_json_response_layers(raw)
        assert parsed == [{"segment_id": "s9", "action": "delete"}]

    def test_sanitize_is_subtractive_only(self):
        raw = "{\"k\": \"</think> inside\"}"
        # content between first { and last } is preserved verbatim
        assert _sanitize_response(raw) == "{\"k\": \"</think> inside\"}"


# ---------------------------------------------------------------------------
# M3-4: SSRF guard
# ---------------------------------------------------------------------------

@pytest.fixture
def allow_flag_off(monkeypatch):
    monkeypatch.setattr(llm_service, "load_settings", lambda: {"llm_allow_local_urls": False})


class TestSsrf:
    def test_private_ipv4_rejected(self, allow_flag_off):
        cfg = LlmConfig(provider=LlmProvider.CUSTOM, base_url="http://192.168.1.10:8000/v1",
                        api_key="k", model="m")
        err = validate_base_url_security(cfg)
        assert err and "SSRF" in err

    def test_loopback_rejected(self, allow_flag_off):
        cfg = LlmConfig(provider=LlmProvider.CUSTOM, base_url="http://127.0.0.1:11434/v1",
                        api_key="k", model="m")
        assert validate_base_url_security(cfg) is not None

    def test_public_host_allowed(self, allow_flag_off):
        cfg = LlmConfig(provider=LlmProvider.DEEPSEEK, base_url="",
                        api_key="k", model="m")
        assert validate_base_url_security(cfg) is None

    def test_allow_local_urls_flag_bypasses(self, monkeypatch):
        monkeypatch.setattr(llm_service, "load_settings", lambda: {"llm_allow_local_urls": True})
        cfg = LlmConfig(provider=LlmProvider.CUSTOM, base_url="http://localhost:11434/v1",
                        api_key="k", model="m")
        assert validate_base_url_security(cfg) is None

    def test_call_llm_rejects_private_endpoint(self, monkeypatch, allow_flag_off):
        cfg = LlmConfig(provider=LlmProvider.CUSTOM, base_url="http://10.0.0.5/v1",
                        api_key="k", model="m")
        res = llm_service.call_llm("hi", config=cfg)
        assert not res["success"]
        assert "SSRF" in res["error"]


# ---------------------------------------------------------------------------
# M3-5: opaque ids + temperature
# ---------------------------------------------------------------------------

class TestOpaqueIds:
    def test_mapping_shape(self):
        segs = [{"id": "seg_1.000", "text": "a"}, {"id": "seg_2.000", "text": "b"}]
        mapping = _build_opaque_id_mapping(segs)
        assert mapping == {"seg_1.000": "t1", "seg_2.000": "t2"}

    def test_message_hides_real_ids_and_timestamps(self):
        segs = [{"id": "seg_1.000", "text": "机密段落", "start": 12.345, "end": 15.678}]
        mapping = _build_opaque_id_mapping(segs)
        msg = _build_structured_user_message(segs, opaque_ids=mapping)
        payload = __import__("json").loads(msg)
        assert payload["segments"][0]["id"] == "t1"
        assert "start" not in payload["segments"][0]
        assert "end" not in payload["segments"][0]
        assert "seg_1.000" not in msg

    def test_message_without_opaque_keeps_fields(self):
        segs = [{"id": "seg_1.000", "text": "t", "start": 1.0, "end": 2.0}]
        msg = _build_structured_user_message(segs)
        assert '"start"' in msg and "seg_1.000" in msg

    def test_effective_temperature_override(self):
        cfg = LlmConfig(provider=LlmProvider.CUSTOM, base_url="http://x.example",
                        api_key="k", model="m", temperature=0.1)
        assert cfg.effective_temperature() == 0.1
        hot = cfg.model_copy(update={"temperature_override": 0.0})
        assert hot.effective_temperature() == 0.0


class TestMaxBatchChars:
    def test_char_budget_splits_batches(self):
        segs = [
            {"id": f"s{i}", "text": "字" * 300, "start": float(i), "end": i + 1.0}
            for i in range(10)
        ]
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=0, max_chars=1000)
        # 3000 chars total / 1000 per batch -> at least 3 batches
        assert len(batches) >= 3
        all_targets = [sid for _, targets in batches for sid in targets]
        assert sorted(all_targets) == sorted(s["id"] for s in segs)

    def test_oversized_single_segment_never_dropped(self):
        segs = [{"id": "big", "text": "字" * 5000, "start": 0.0, "end": 1.0},
                {"id": "s1", "text": "小", "start": 1.0, "end": 2.0}]
        batches = chunk_transcript_by_count(segs, batch_size=10, overlap=0, max_chars=1000)
        all_targets = [sid for _, targets in batches for sid in targets]
        assert "big" in all_targets and "s1" in all_targets

    def test_no_budget_keeps_count_semantics(self):
        segs = [{"id": f"s{i}", "text": "x", "start": float(i), "end": i + 1.0}
                for i in range(45)]
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 3
