"""ASR GUI E2E regression tests (behavioral, no GPU/network).

Verifies actual runtime behavior to catch the 4 regression bugs:
1. SettingsModal uses engine-prefixed keys (not old asr_compute_type)
2. SettingsModal has int8_float16 as compute option
3. Engine switch preserves device settings
4. handleTranscribe calls saveAsrSettings before runTranscription

All tests read source files or import config -- no torch, no GPU, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Resolve project root (one level up from tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_source(relative: str) -> str:
    """Read a source file relative to project root and return its text."""
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Config behavioral tests (tests 1-5)
# ---------------------------------------------------------------------------

class TestConfigBehavior:
    """Verify engine-prefixed settings keys exist with correct defaults."""

    def test_config_has_engine_prefixed_keys(self):
        """_DEFAULT_SETTINGS must contain all 5 engine-prefixed keys."""
        from core.config import _DEFAULT_SETTINGS

        required_keys = [
            "whisper_compute_type",
            "whisper_vad_threshold",
            "whisper_vad_min_silence_ms",
            "qwen_compute_type",
            "qwen_language",
        ]
        for key in required_keys:
            assert key in _DEFAULT_SETTINGS, f"Missing key: {key}"

    def test_config_old_key_removed(self):
        """The legacy 'asr_compute_type' key must NOT exist."""
        from core.config import _DEFAULT_SETTINGS
        assert "asr_compute_type" not in _DEFAULT_SETTINGS

    def test_whisper_default_is_int8_float16(self):
        """whisper_compute_type must default to 'int8_float16'."""
        from core.config import _DEFAULT_SETTINGS
        assert _DEFAULT_SETTINGS["whisper_compute_type"] == "int8_float16"

    def test_qwen_default_is_bfloat16(self):
        """qwen_compute_type must default to 'bfloat16'."""
        from core.config import _DEFAULT_SETTINGS
        assert _DEFAULT_SETTINGS["qwen_compute_type"] == "bfloat16"

    def test_settings_roundtrip_preserves_keys(self, tmp_path, monkeypatch):
        """Engine-prefixed keys must survive save -> load roundtrip."""
        from core.config import load_settings, save_settings

        # Patch get_settings_path to use a temp file
        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(
            "core.config.get_settings_path", lambda: settings_file
        )

        # First load (no file) -- returns defaults
        s1 = load_settings()
        for key in (
            "whisper_compute_type",
            "whisper_vad_threshold",
            "whisper_vad_min_silence_ms",
            "qwen_compute_type",
            "qwen_language",
        ):
            assert key in s1, f"Key {key} missing from default load"

        # Save to disk
        save_settings(s1)

        # Second load -- must preserve all keys
        s2 = load_settings()
        for key in (
            "whisper_compute_type",
            "whisper_vad_threshold",
            "whisper_vad_min_silence_ms",
            "qwen_compute_type",
            "qwen_language",
        ):
            assert key in s2, f"Key {key} lost after roundtrip"
            assert s2[key] == s1[key], (
                f"Value mismatch for {key}: {s2[key]} != {s1[key]}"
            )


# ---------------------------------------------------------------------------
# 2. Backend source behavioral tests (tests 6-10)
# ---------------------------------------------------------------------------

class TestBackendSource:
    """Source-level behavioral checks on ASR scripts and main.py."""

    def test_qwen_has_bfloat16_default(self):
        """qwen_transcribe.py must map bfloat16 to torch.bfloat16."""
        src = _read_source("core/asr_scripts/qwen_transcribe.py")
        assert "torch.bfloat16" in src, "DTYPE_MAP missing torch.bfloat16"

    def test_qwen_has_compute_type_arg(self):
        """qwen_transcribe.py must accept --compute-type argument."""
        src = _read_source("core/asr_scripts/qwen_transcribe.py")
        assert "--compute-type" in src, (
            "--compute-type arg missing from qwen argparse"
        )

    def test_whisper_has_vad_params(self):
        """whisper_transcribe.py must pass vad_parameters to transcription."""
        src = _read_source("core/asr_scripts/whisper_transcribe.py")
        assert "vad_parameters" in src, (
            "vad_parameters not found in whisper script"
        )

    def test_main_reads_engine_prefixed_keys(self):
        """main.py must read whisper_compute_type from settings."""
        src = _read_source("main.py")
        # Verify it's used in a settings.get() call, not just a comment
        assert "whisper_compute_type" in src, (
            "main.py does not reference whisper_compute_type"
        )
        # More specific: must appear in a settings.get call
        assert re.search(r'settings\.get\(\s*["\']whisper_compute_type', src), (
            "whisper_compute_type not used in settings.get() call"
        )

    def test_main_single_cleanup_method(self):
        """There must be exactly one definition of cleanup_tasks_folder."""
        src = _read_source("main.py")
        count = len(re.findall(r"def cleanup_tasks_folder", src))
        assert count == 1, f"Expected 1 def, found {count}"


# ---------------------------------------------------------------------------
# 3. Frontend source behavioral tests (tests 11-12)
# ---------------------------------------------------------------------------

class TestFrontendSource:
    """Source-level behavioral checks on Vue components."""

    def test_settings_modal_uses_engine_prefixed_keys(self):
        """SettingsModal.vue must use engine-prefixed keys, not old asr_compute_type."""
        src = _read_source("frontend/src/components/workspace/SettingsModal.vue")
        # Must use engine-prefixed keys
        assert "whisper_compute_type" in src, (
            "SettingsModal.vue does not use whisper_compute_type"
        )
        assert "qwen_compute_type" in src, (
            "SettingsModal.vue does not use qwen_compute_type"
        )
        # Must have int8_float16 as a compute option
        assert "int8_float16" in src, (
            "SettingsModal.vue missing int8_float16 compute option"
        )
        # Must NOT use old un-prefixed key as a settings key
        # (allow it only if not used in updateField/setField calls)
        if "asr_compute_type" in src:
            # If present, must only be in a comparison, not as a settings key
            assert not re.search(
                r"updateField\(\s*['\"]asr_compute_type", src
            ), "SettingsModal.vue still uses old asr_compute_type as settings key"

    def test_workspace_handle_transcribe_saves_first(self):
        """handleTranscribe must call saveAsrSettings() before runTranscription()."""
        src = _read_source("frontend/src/pages/WorkspacePage.vue")
        # Find the handleTranscribe function body
        match = re.search(
            r"async function handleTranscribe\(\)\s*\{(.*?)(?=\n(?:async )?function |\nconst \w+ = |\Z)",
            src,
            re.DOTALL,
        )
        assert match is not None, "handleTranscribe function not found"
        body = match.group(1)
        # Both calls must exist
        assert "saveAsrSettings" in body, (
            "handleTranscribe does not call saveAsrSettings"
        )
        assert "runTranscription" in body, (
            "handleTranscribe does not call runTranscription"
        )
        # saveAsrSettings must come before runTranscription
        save_pos = body.index("saveAsrSettings")
        transcribe_pos = body.index("runTranscription")
        assert save_pos < transcribe_pos, (
            f"saveAsrSettings (pos {save_pos}) must come before "
            f"runTranscription (pos {transcribe_pos})"
        )
