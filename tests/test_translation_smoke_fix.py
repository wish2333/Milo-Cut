"""v3.0.4 smoke-fix regression tests (P4-4 smoke findings).

Covers the three smoke defects reported on the dev-3.0.4 real-device pass:

1a. get_llm_config exposes provider-resolved base_url/model so the frontend
    "configured" judgment matches backend is_configured() (empty fields =
    provider defaults, not "unconfigured").
1c. analyze_subtitle_translation cancels PROMPTLY even while every in-flight
    batch is blocked on a slow LLM response: the executor polls the cancel
    event on a bounded interval and never waits out running HTTP calls on
    shutdown (cancel latency ~= poll interval, not "next batch completion").

(Defect 1b -- the panel progress bar never listened to task:progress -- and
defect 2 -- the manual-range group had no delete affordance -- are frontend
fixes covered by frontend tests.)
"""

from __future__ import annotations

import json
import threading
import time

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


def _segments(n: int) -> list[dict]:
    return [
        {
            "segment_id": f"seg-{i:03d}",
            "start": float(i * 5),
            "end": float(i * 5 + 4),
            "text": f"text {i}",
        }
        for i in range(n)
    ]


def _echo_translator(block: threading.Event | None = None):
    """Mock LLM: echoes targets; optionally blocks until released."""

    def fake_call_llm(prompt, system="", **kwargs):
        if block is not None:
            block.wait(timeout=60)
        payload = json.loads(prompt)
        results = [
            {"segment_id": t, "translated_text": f"EN[{t}]"}
            for t in payload["target_segment_ids"]
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
# 1a: resolved provider defaults in get_llm_config payload
# ================================================================


class TestResolvedLlmConfig:
    def test_resolved_fields_present_with_defaults(self, monkeypatch):
        """Empty base_url/model resolve to provider defaults -- the backend
        judgment stays configured, and the expose carries the resolved
        values for the frontend."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {
                "llm_provider": "deepseek",
                "llm_base_url": "",
                "llm_api_key": "sk-live-key",
                "llm_model": "",
            },
        )
        config = llm_service.get_llm_config()
        # backend semantics: defaults count as configured
        assert config.is_configured() is True
        assert config.resolved_base_url()
        assert config.resolved_model()
        # the expose adds the resolved values (main.py get_llm_config)
        from main import MiloCutApi

        api = MiloCutApi.__new__(MiloCutApi)
        data = api.get_llm_config()["data"]
        assert data["resolved_base_url"] == config.resolved_base_url()
        assert data["resolved_model"] == config.resolved_model()
        assert data["api_key_masked"]

    def test_raw_fields_stay_raw_for_settings_editor(self, monkeypatch):
        """The raw model/base_url keys remain the user's (possibly empty)
        values -- the settings editor must not see resolved defaults and
        write them back as explicit overrides."""
        monkeypatch.setattr(
            llm_service,
            "load_settings",
            lambda: {
                "llm_provider": "deepseek",
                "llm_base_url": "",
                "llm_api_key": "sk-live-key",
                "llm_model": "",
            },
        )
        from main import MiloCutApi

        api = MiloCutApi.__new__(MiloCutApi)
        data = api.get_llm_config()["data"]
        assert data["base_url"] == ""
        assert data["model"] == ""


# ================================================================
# 1c: prompt cancellation under blocked in-flight batches
# ================================================================


class TestCancelLatency:
    def test_cancel_observed_while_batches_blocked(self, monkeypatch):
        """Every in-flight batch blocks on a 60s barrier; cancel fires at
        t=0.3s. The pipeline must return Cancelled within ~2s (poll
        interval 1s + scheduling margin) instead of waiting for the
        barrier. Pre-fix, as_completed + the with-block shutdown(wait=True)
        held the caller until the barrier released."""
        block = threading.Event()
        monkeypatch.setattr("core.llm_service.call_llm", _echo_translator(block))
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})

        cancel_event = threading.Event()
        outcome: dict = {}

        def run():
            outcome["result"] = analyze_subtitle_translation(
                _segments(6),
                "English",
                config=_configured_llm(),
                cancel_event=cancel_event,
            )

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        time.sleep(0.3)
        cancel_event.set()
        worker.join(timeout=5.0)

        assert not worker.is_alive(), "pipeline did not observe cancel promptly"
        result = outcome["result"]
        assert result["success"] is False
        assert result["error"] == "Cancelled"
        # in-flight HTTP calls are abandoned, not waited out
        block.set()
        worker.join(timeout=2.0)

    def test_no_cancel_completes_normally(self, monkeypatch):
        """The polling restructure preserves the happy path (full
        conservation, ordered translations)."""
        monkeypatch.setattr("core.llm_service.call_llm", _echo_translator())
        monkeypatch.setattr(llm_service, "load_settings", lambda: {})
        result = analyze_subtitle_translation(
            _segments(6),
            "English",
            config=_configured_llm(),
        )
        assert result["success"] is True
        translations = result["data"]["translations"]
        assert [t["segment_id"] for t in translations] == [
            f"seg-{i:03d}" for i in range(6)
        ]
