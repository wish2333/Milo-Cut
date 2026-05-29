"""Standalone test for ASR transcription pipeline.

Diagnoses transcription stall issues by testing each pipeline stage independently:
1. Plugin installation status
2. Model download status
3. Model resolution logic
4. Subprocess launch and progress reporting

Usage:
    uv run pytest tests/test_transcription.py -v
    uv run pytest tests/test_transcription.py -v -s   (with print output)
    uv run python tests/test_transcription.py           (standalone)

Environment:
    Set MILOCUT_TEST_TIMEOUT=300 to override the default 120s timeout.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_VIDEO = PROJECT_ROOT / "test" / "test.mp4"
TRANSCRIPTION_TIMEOUT = int(os.environ.get("MILOCUT_TEST_TIMEOUT", "120"))
STALL_THRESHOLD_SECONDS = 30


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ts() -> str:
    """Return a timestamp string for debug output."""
    return time.strftime("%H:%M:%S")


def _make_progress_cb(label: str):
    """Create a progress callback that prints timestamps and detects stalls.

    Returns (callback, last_progress_time_ref) where last_progress_time_ref
    is a mutable list holding the last callback timestamp.
    """
    last_call: list[float] = [time.monotonic()]
    stall_detected: list[bool] = [False]

    def cb(percent: float, message: str) -> None:
        now = time.monotonic()
        elapsed_since_last = now - last_call[0]
        last_call[0] = now

        if elapsed_since_last > STALL_THRESHOLD_SECONDS:
            stall_detected[0] = True
            print(
                f"  [{_ts()}] STALL DETECTED: {elapsed_since_last:.1f}s gap "
                f"between progress callbacks"
            )

        print(
            f"  [{_ts()}] [{label}] progress={percent:6.1f}%  "
            f"gap={elapsed_since_last:.1f}s  msg={message}"
        )

    return cb, last_call, stall_detected


def _get_plugin_manager():
    """Initialize and return a PluginManager instance."""
    from core.plugin_manager import PluginManager

    pm = PluginManager()
    return pm


def _get_settings():
    """Load application settings."""
    from core.config import load_settings

    return load_settings()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestVideoFile:
    """Verify the test video file is accessible."""

    def test_video_exists(self):
        """Test video file must exist."""
        assert TEST_VIDEO.exists(), f"Test video not found: {TEST_VIDEO}"
        size_mb = TEST_VIDEO.stat().st_size / (1024 * 1024)
        print(f"\n  Test video: {TEST_VIDEO}")
        print(f"  Size: {size_mb:.1f} MB")


class TestPluginStatus:
    """Check which ASR plugins are installed and models downloaded."""

    def test_plugin_registry_loaded(self):
        """PLUGIN_REGISTRY should contain known plugin IDs."""
        from core.plugin_manager import PLUGIN_REGISTRY

        assert "plugin-whisper" in PLUGIN_REGISTRY
        assert "plugin-qwen-cpu" in PLUGIN_REGISTRY
        assert "plugin-qwen-gpu" in PLUGIN_REGISTRY
        print(f"\n  Registered plugins: {list(PLUGIN_REGISTRY.keys())}")

    def test_list_plugins(self):
        """list_plugins() should return all registered plugins with status."""
        pm = _get_plugin_manager()
        plugins = pm.list_plugins()

        print("\n  Plugin status:")
        for p in plugins:
            marker = "[INSTALLED]" if p["status"] == "installed" else "[NOT INSTALLED]"
            print(f"    {marker} {p['plugin_id']} - {p['display_name']}")
            if p["status"] == "installed":
                print(f"             venv: {p['venv_path']}")

        assert len(plugins) >= 3, "Expected at least 3 plugins in registry"

    def test_list_models(self):
        """list_models() should return all registered models with status."""
        pm = _get_plugin_manager()
        models = pm.list_models()

        print("\n  Model status:")
        for m in models:
            marker = "[DOWNLOADED]" if m["status"] == "downloaded" else "[NOT DOWNLOADED]"
            size_gb = m["size_bytes"] / (1024 ** 3)
            print(
                f"    {marker} {m['model_id']}"
                f"  ({size_gb:.1f} GB, plugin={m['plugin_id']})"
            )

        assert len(models) >= 2, "Expected at least 2 models in registry"

    def test_whisper_installed(self):
        """Check if whisper plugin is installed. Skip other whisper tests if not."""
        pm = _get_plugin_manager()
        installed = pm.is_installed("plugin-whisper")
        if not installed:
            pytest.skip(
                "plugin-whisper not installed -- "
                "install from Settings > AI Engine to run whisper tests"
            )
        print("\n  plugin-whisper: INSTALLED")
        python_path = pm.get_plugin_python("plugin-whisper")
        print(f"  Python executable: {python_path}")
        assert python_path.exists(), f"Plugin Python not found: {python_path}"

    def test_qwen_cpu_installed(self):
        """Check if qwen-cpu plugin is installed. Skip other qwen tests if not."""
        pm = _get_plugin_manager()
        installed = pm.is_installed("plugin-qwen-cpu")
        if not installed:
            pytest.skip(
                "plugin-qwen-cpu not installed -- "
                "install from Settings > AI Engine to run qwen tests"
            )
        print("\n  plugin-qwen-cpu: INSTALLED")


class TestModelResolution:
    """Test model ID resolution logic without downloading anything."""

    def test_resolve_whisper_model_known_sizes(self):
        """Known whisper size keys should resolve to full model IDs."""
        from core.asr_service import _resolve_whisper_model

        cases = [
            ("large-v3-turbo", "Purfview/faster-whisper-large-v3-turbo"),
            ("base", "Systran/faster-whisper-base"),
        ]
        for size_key, expected_id in cases:
            result = _resolve_whisper_model(size_key)
            print(f"\n  resolve_whisper_model('{size_key}') => {result}")
            assert result == expected_id, (
                f"Expected {expected_id} for '{size_key}', got {result}"
            )

    def test_resolve_whisper_model_full_id_passthrough(self):
        """Full HuggingFace IDs should pass through unchanged."""
        from core.asr_service import _resolve_whisper_model

        full_id = "Purfview/faster-whisper-large-v3-turbo"
        result = _resolve_whisper_model(full_id)
        assert result == full_id

    def test_resolve_whisper_model_unknown(self):
        """Unknown size keys should return None."""
        from core.asr_service import _resolve_whisper_model

        result = _resolve_whisper_model("nonexistent-size")
        assert result is None

    def test_resolve_qwen_model_asr(self):
        """Qwen ASR model size keys should resolve correctly."""
        from core.asr_service import _resolve_qwen_model

        cases = [
            ("asr", "0.6B", "Qwen/Qwen3-ASR-0.6B"),
            ("asr", "1.7B", "Qwen/Qwen3-ASR-1.7B"),
        ]
        for model_type, size_key, expected_id in cases:
            result = _resolve_qwen_model(model_type, size_key)
            print(f"\n  resolve_qwen_model('{model_type}', '{size_key}') => {result}")
            assert result == expected_id

    def test_resolve_qwen_model_aligner(self):
        """Qwen aligner model size keys should resolve correctly."""
        from core.asr_service import _resolve_qwen_model

        result = _resolve_qwen_model("aligner", "0.6B")
        print(f"\n  resolve_qwen_model('aligner', '0.6B') => {result}")
        assert result == "Qwen/Qwen3-ForcedAligner-0.6B"

    def test_resolve_qwen_model_unknown(self):
        """Unknown qwen size keys should return None."""
        from core.asr_service import _resolve_qwen_model

        result = _resolve_qwen_model("asr", "99B")
        assert result is None

        result = _resolve_qwen_model("invalid_type", "0.6B")
        assert result is None


class TestScriptPaths:
    """Verify ASR subprocess scripts exist on disk."""

    def test_whisper_script_exists(self):
        """whisper_transcribe.py must exist."""
        script = PROJECT_ROOT / "core" / "asr_scripts" / "whisper_transcribe.py"
        assert script.exists(), f"Script not found: {script}"
        print(f"\n  Whisper script: {script}")

    def test_qwen_script_exists(self):
        """qwen_transcribe.py must exist."""
        script = PROJECT_ROOT / "core" / "asr_scripts" / "qwen_transcribe.py"
        assert script.exists(), f"Script not found: {script}"
        print(f"\n  Qwen script: {script}")

    def test_common_script_exists(self):
        """common.py must exist for subprocess IPC."""
        script = PROJECT_ROOT / "core" / "asr_scripts" / "common.py"
        assert script.exists(), f"Script not found: {script}"


class TestWhisperTranscription:
    """End-to-end whisper transcription test with stall diagnosis.

    Skipped if plugin-whisper is not installed.
    """

    @pytest.fixture(autouse=True)
    def _require_whisper(self):
        """Skip entire class if whisper plugin not installed."""
        pm = _get_plugin_manager()
        if not pm.is_installed("plugin-whisper"):
            pytest.skip("plugin-whisper not installed")

    def test_whisper_transcription_with_progress(self):
        """Run whisper transcription and verify progress callbacks fire.

        This is the main diagnostic test. It:
        1. Resolves the model
        2. Checks model is downloaded (or downloads it)
        3. Launches the subprocess
        4. Monitors progress callbacks with timestamps
        5. Detects stalls (>30s with no progress)
        6. Verifies the result contains segments
        """
        from core.asr_service import _resolve_whisper_model, transcribe_with_whisper

        pm = _get_plugin_manager()
        settings = _get_settings()

        model_size = settings.get("asr_model_size", "large-v3-turbo")
        language = settings.get("asr_language", "zh")
        device = settings.get("asr_device", "cpu")
        compute_type = settings.get("asr_compute_type", "int8")
        vad_filter = settings.get("asr_vad_filter", True)

        # Step 1: Resolve model
        model_id = _resolve_whisper_model(model_size)
        print(f"\n  [STAGE 1] Model resolution:")
        print(f"    model_size={model_size} => model_id={model_id}")
        assert model_id is not None, f"Cannot resolve whisper model size: {model_size}"

        # Step 2: Check if model is downloaded
        model_downloaded = pm.is_model_downloaded(model_id)
        model_path = pm.get_model_path(model_id)
        print(f"  [STAGE 2] Model download status:")
        print(f"    model_id={model_id}")
        print(f"    downloaded={model_downloaded}")
        print(f"    path={model_path}")

        # Step 3: Check subprocess script
        script_path = PROJECT_ROOT / "core" / "asr_scripts" / "whisper_transcribe.py"
        print(f"  [STAGE 3] Subprocess script:")
        print(f"    exists={script_path.exists()}")
        print(f"    path={script_path}")

        # Step 4: Run transcription with progress monitoring
        print(f"  [STAGE 4] Starting transcription (timeout={TRANSCRIPTION_TIMEOUT}s):")
        print(f"    media={TEST_VIDEO}")
        print(f"    device={device}, compute_type={compute_type}")
        print(f"    language={language}, vad_filter={vad_filter}")

        cb, last_call, stall_detected = _make_progress_cb("whisper")

        cancel_event = threading.Event()
        result_holder: dict = {}
        error_holder: list = []

        def run_transcription():
            try:
                result_holder["value"] = transcribe_with_whisper(
                    plugin_manager=pm,
                    media_path=str(TEST_VIDEO),
                    model_size=model_size,
                    language=language,
                    device=device,
                    compute_type=compute_type,
                    vad_filter=vad_filter,
                    progress_cb=cb,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                error_holder.append(exc)

        thread = threading.Thread(target=run_transcription, daemon=True)
        thread.start()
        thread.join(timeout=TRANSCRIPTION_TIMEOUT)

        if thread.is_alive():
            # Timeout -- cancel and report
            cancel_event.set()
            thread.join(timeout=10)
            pytest.fail(
                f"Transcription timed out after {TRANSCRIPTION_TIMEOUT}s. "
                f"Last progress was {time.monotonic() - last_call[0]:.1f}s ago. "
                f"This confirms the stall issue."
            )

        if error_holder:
            exc = error_holder[0]
            pytest.fail(f"Transcription raised {type(exc).__name__}: {exc}")

        result = result_holder.get("value", {})
        print(f"\n  [RESULT] success={result.get('success')}")

        if not result.get("success"):
            print(f"  [RESULT] error={result.get('error')}")
            pytest.fail(f"Transcription failed: {result.get('error')}")

        data = result.get("data", {})
        segments = data.get("segments", [])
        print(f"  [RESULT] segments={len(segments)}")
        if segments:
            first = segments[0]
            print(f"  [RESULT] first_segment: {json.dumps(first, ensure_ascii=False)[:200]}")

        assert result["success"], f"Transcription failed: {result.get('error')}"
        assert len(segments) > 0, "Transcription returned no segments"

    def test_whisper_plugin_python_executable(self):
        """Verify the plugin's Python executable can run a simple script."""
        pm = _get_plugin_manager()
        python_path = pm.get_plugin_python("plugin-whisper")
        assert python_path.exists(), f"Python not found: {python_path}"

        import subprocess
        from core.plugin_manager import _clean_subprocess_env

        env = _clean_subprocess_env()
        proc = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.version); print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        print(f"\n  Plugin Python: {python_path}")
        print(f"  Version: {proc.stdout.strip()}")
        print(f"  Return code: {proc.returncode}")

        assert proc.returncode == 0, f"Plugin Python failed: {proc.stderr}"
        assert "OK" in proc.stdout

    def test_whisper_import_check(self):
        """Verify faster-whisper can be imported in the plugin venv."""
        pm = _get_plugin_manager()
        python_path = pm.get_plugin_python("plugin-whisper")

        import subprocess
        from core.plugin_manager import _clean_subprocess_env

        env = _clean_subprocess_env()
        proc = subprocess.run(
            [
                str(python_path), "-c",
                "import faster_whisper; print(f'faster-whisper {faster_whisper.__version__}')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        print(f"\n  Import test: {proc.stdout.strip()}")
        if proc.returncode != 0:
            print(f"  Stderr: {proc.stderr}")
        assert proc.returncode == 0, f"Cannot import faster-whisper: {proc.stderr}"


class TestQwenTranscription:
    """End-to-end qwen transcription test with stall diagnosis.

    Skipped if plugin-qwen-cpu is not installed.
    """

    @pytest.fixture(autouse=True)
    def _require_qwen(self):
        """Skip entire class if qwen plugin not installed."""
        pm = _get_plugin_manager()
        if not pm.is_installed("plugin-qwen-cpu"):
            pytest.skip("plugin-qwen-cpu not installed")

    def test_qwen_transcription_with_progress(self):
        """Run qwen transcription and verify progress callbacks fire.

        Same diagnostic structure as the whisper test.
        """
        from core.asr_service import _resolve_qwen_model, transcribe_with_qwen

        pm = _get_plugin_manager()
        settings = _get_settings()

        language = settings.get("asr_language", "zh")
        device = "cpu"  # Always CPU for this test

        # Step 1: Resolve models
        asr_model_id = _resolve_qwen_model("asr", "0.6B")
        aligner_model_id = _resolve_qwen_model("aligner", "0.6B")
        print(f"\n  [STAGE 1] Model resolution:")
        print(f"    asr: 0.6B => {asr_model_id}")
        print(f"    aligner: 0.6B => {aligner_model_id}")
        assert asr_model_id is not None
        assert aligner_model_id is not None

        # Step 2: Check download status
        asr_downloaded = pm.is_model_downloaded(asr_model_id)
        aligner_downloaded = pm.is_model_downloaded(aligner_model_id)
        print(f"  [STAGE 2] Model download status:")
        print(f"    asr ({asr_model_id}): downloaded={asr_downloaded}")
        print(f"    aligner ({aligner_model_id}): downloaded={aligner_downloaded}")

        # Step 3: Check subprocess script
        script_path = PROJECT_ROOT / "core" / "asr_scripts" / "qwen_transcribe.py"
        print(f"  [STAGE 3] Subprocess script:")
        print(f"    exists={script_path.exists()}")
        print(f"    path={script_path}")

        # Step 4: Run transcription
        print(f"  [STAGE 4] Starting transcription (timeout={TRANSCRIPTION_TIMEOUT}s):")
        print(f"    media={TEST_VIDEO}")
        print(f"    device={device}, language={language}")

        cb, last_call, stall_detected = _make_progress_cb("qwen")

        cancel_event = threading.Event()
        result_holder: dict = {}
        error_holder: list = []

        def run_transcription():
            try:
                result_holder["value"] = transcribe_with_qwen(
                    plugin_manager=pm,
                    media_path=str(TEST_VIDEO),
                    asr_model_size="0.6B",
                    aligner_model_size="0.6B",
                    language=language,
                    device=device,
                    progress_cb=cb,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                error_holder.append(exc)

        thread = threading.Thread(target=run_transcription, daemon=True)
        thread.start()
        thread.join(timeout=TRANSCRIPTION_TIMEOUT)

        if thread.is_alive():
            cancel_event.set()
            thread.join(timeout=10)
            pytest.fail(
                f"Transcription timed out after {TRANSCRIPTION_TIMEOUT}s. "
                f"Last progress was {time.monotonic() - last_call[0]:.1f}s ago."
            )

        if error_holder:
            exc = error_holder[0]
            pytest.fail(f"Transcription raised {type(exc).__name__}: {exc}")

        result = result_holder.get("value", {})
        print(f"\n  [RESULT] success={result.get('success')}")

        if not result.get("success"):
            print(f"  [RESULT] error={result.get('error')}")
            pytest.fail(f"Transcription failed: {result.get('error')}")

        data = result.get("data", {})
        segments = data.get("segments", [])
        print(f"  [RESULT] segments={len(segments)}")
        if segments:
            first = segments[0]
            print(f"  [RESULT] first_segment: {json.dumps(first, ensure_ascii=False)[:200]}")

        assert result["success"], f"Transcription failed: {result.get('error')}"
        assert len(segments) > 0, "Transcription returned no segments"

    def test_qwen_plugin_python_executable(self):
        """Verify the qwen plugin's Python executable works."""
        pm = _get_plugin_manager()
        python_path = pm.get_plugin_python("plugin-qwen-cpu")
        assert python_path.exists(), f"Python not found: {python_path}"

        import subprocess
        from core.plugin_manager import _clean_subprocess_env

        env = _clean_subprocess_env()
        proc = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.version); print('OK')"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        print(f"\n  Plugin Python: {python_path}")
        print(f"  Version: {proc.stdout.strip()}")
        assert proc.returncode == 0, f"Plugin Python failed: {proc.stderr}"

    def test_qwen_import_check(self):
        """Verify transformers and torch can be imported in the plugin venv."""
        pm = _get_plugin_manager()
        python_path = pm.get_plugin_python("plugin-qwen-cpu")

        import subprocess
        from core.plugin_manager import _clean_subprocess_env

        env = _clean_subprocess_env()
        proc = subprocess.run(
            [
                str(python_path), "-c",
                (
                    "import transformers; import torch; "
                    "print(f'transformers {transformers.__version__}'); "
                    "print(f'torch {torch.__version__}')"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        print(f"\n  {proc.stdout.strip()}")
        if proc.returncode != 0:
            print(f"  Stderr: {proc.stderr}")
        assert proc.returncode == 0, f"Cannot import dependencies: {proc.stderr}"


class TestSubprocessIPC:
    """Test the subprocess IPC mechanism directly (without full transcription)."""

    def test_run_in_plugin_simple_script(self):
        """Verify run_in_plugin can execute a trivial script and read stdout events."""
        pm = _get_plugin_manager()

        if not pm.is_installed("plugin-whisper"):
            pytest.skip("plugin-whisper not installed")

        import subprocess
        from core.plugin_manager import _clean_subprocess_env

        python_path = pm.get_plugin_python("plugin-whisper")
        env = _clean_subprocess_env()

        # Write a tiny test script that emits progress events via stdout
        test_script = PROJECT_ROOT / "data" / "plugins" / "tasks" / "_test_ipc.py"
        test_script.parent.mkdir(parents=True, exist_ok=True)
        test_script.write_text(
            'import json, sys, time\n'
            'print(json.dumps({"type": "progress", "percent": 10.0, "message": "start"}), flush=True)\n'
            'time.sleep(0.5)\n'
            'print(json.dumps({"type": "progress", "percent": 50.0, "message": "mid"}), flush=True)\n'
            'time.sleep(0.5)\n'
            'print(json.dumps({"type": "progress", "percent": 100.0, "message": "done"}), flush=True)\n',
            encoding="utf-8",
        )

        try:
            result = subprocess.run(
                [str(python_path), str(test_script)],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            print(f"\n  Test script stdout:")
            events = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        events.append(event)
                        print(f"    {event}")
                    except json.JSONDecodeError:
                        print(f"    [non-JSON] {line}")

            print(f"  Return code: {result.returncode}")
            if result.stderr:
                print(f"  Stderr: {result.stderr[:500]}")

            assert result.returncode == 0
            assert len(events) == 3
            assert events[0]["percent"] == 10.0
            assert events[2]["percent"] == 100.0
        finally:
            test_script.unlink(missing_ok=True)


# ------------------------------------------------------------------
# Standalone runner
# ------------------------------------------------------------------

def _run_standalone():
    """Run all checks outside of pytest for quick debugging."""
    print("=" * 60)
    print("  ASR Transcription Pipeline Diagnostic")
    print("=" * 60)

    # 1. Test video
    print(f"\n[1] Test video check:")
    if TEST_VIDEO.exists():
        size_mb = TEST_VIDEO.stat().st_size / (1024 * 1024)
        print(f"  OK: {TEST_VIDEO} ({size_mb:.1f} MB)")
    else:
        print(f"  FAIL: {TEST_VIDEO} not found")
        return

    # 2. Plugin status
    print(f"\n[2] Plugin status:")
    try:
        pm = _get_plugin_manager()
        plugins = pm.list_plugins()
        for p in plugins:
            marker = "[INSTALLED]" if p["status"] == "installed" else "[NOT INSTALLED]"
            print(f"  {marker} {p['plugin_id']} - {p['display_name']}")
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return

    # 3. Model status
    print(f"\n[3] Model status:")
    try:
        models = pm.list_models()
        for m in models:
            marker = "[DOWNLOADED]" if m["status"] == "downloaded" else "[NOT DOWNLOADED]"
            size_gb = m["size_bytes"] / (1024 ** 3)
            print(f"  {marker} {m['model_id']} ({size_gb:.1f} GB)")
    except Exception as exc:
        print(f"  FAIL: {exc}")

    # 4. Settings
    print(f"\n[4] Settings:")
    settings = _get_settings()
    relevant_keys = [
        "asr_engine", "asr_model_size", "asr_language",
        "asr_device", "asr_compute_type", "asr_vad_filter",
    ]
    for key in relevant_keys:
        print(f"  {key}: {settings.get(key, '<not set>')}")

    # 5. Model resolution
    print(f"\n[5] Model resolution:")
    try:
        from core.asr_service import _resolve_whisper_model, _resolve_qwen_model

        whisper_id = _resolve_whisper_model(settings.get("asr_model_size", "large-v3-turbo"))
        print(f"  whisper ({settings.get('asr_model_size', 'large-v3-turbo')}): {whisper_id}")

        qwen_asr = _resolve_qwen_model("asr", "0.6B")
        qwen_aligner = _resolve_qwen_model("aligner", "0.6B")
        print(f"  qwen asr (0.6B): {qwen_asr}")
        print(f"  qwen aligner (0.6B): {qwen_aligner}")
    except Exception as exc:
        print(f"  FAIL: {exc}")

    # 6. Run transcription if plugin available
    print(f"\n[6] Transcription test:")
    if pm.is_installed("plugin-whisper"):
        print(f"  Running whisper transcription (timeout={TRANSCRIPTION_TIMEOUT}s)...")
        try:
            from core.asr_service import transcribe_with_whisper

            cb, last_call, stall_detected = _make_progress_cb("whisper")
            cancel_event = threading.Event()
            result_holder: dict = {}
            error_holder: list = []

            def run():
                try:
                    result_holder["value"] = transcribe_with_whisper(
                        plugin_manager=pm,
                        media_path=str(TEST_VIDEO),
                        model_size=settings.get("asr_model_size", "large-v3-turbo"),
                        language=settings.get("asr_language", "zh"),
                        device=settings.get("asr_device", "cpu"),
                        compute_type=settings.get("asr_compute_type", "int8"),
                        vad_filter=settings.get("asr_vad_filter", True),
                        progress_cb=cb,
                        cancel_event=cancel_event,
                    )
                except Exception as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=run, daemon=True)
            t.start()
            t.join(timeout=TRANSCRIPTION_TIMEOUT)

            if t.is_alive():
                cancel_event.set()
                t.join(timeout=10)
                print(f"  TIMEOUT after {TRANSCRIPTION_TIMEOUT}s!")
                print(f"  Last progress {time.monotonic() - last_call[0]:.1f}s ago")
            elif error_holder:
                print(f"  ERROR: {error_holder[0]}")
            else:
                result = result_holder.get("value", {})
                if result.get("success"):
                    segments = result.get("data", {}).get("segments", [])
                    print(f"  OK: {len(segments)} segments")
                else:
                    print(f"  FAIL: {result.get('error')}")

            if stall_detected[0]:
                print(f"  WARNING: Stall detected during execution")
        except Exception as exc:
            print(f"  FAIL: {exc}")
    else:
        print(f"  SKIPPED: plugin-whisper not installed")

    if pm.is_installed("plugin-qwen-cpu"):
        print(f"\n  Running qwen transcription (timeout={TRANSCRIPTION_TIMEOUT}s)...")
        try:
            from core.asr_service import transcribe_with_qwen

            cb, last_call, stall_detected = _make_progress_cb("qwen")
            cancel_event = threading.Event()
            result_holder.clear()
            error_holder.clear()

            def run_qwen():
                try:
                    result_holder["value"] = transcribe_with_qwen(
                        plugin_manager=pm,
                        media_path=str(TEST_VIDEO),
                        language=settings.get("asr_language", "zh"),
                        device="cpu",
                        progress_cb=cb,
                        cancel_event=cancel_event,
                    )
                except Exception as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=run_qwen, daemon=True)
            t.start()
            t.join(timeout=TRANSCRIPTION_TIMEOUT)

            if t.is_alive():
                cancel_event.set()
                t.join(timeout=10)
                print(f"  TIMEOUT after {TRANSCRIPTION_TIMEOUT}s!")
            elif error_holder:
                print(f"  ERROR: {error_holder[0]}")
            else:
                result = result_holder.get("value", {})
                if result.get("success"):
                    segments = result.get("data", {}).get("segments", [])
                    print(f"  OK: {len(segments)} segments")
                else:
                    print(f"  FAIL: {result.get('error')}")

            if stall_detected[0]:
                print(f"  WARNING: Stall detected during execution")
        except Exception as exc:
            print(f"  FAIL: {exc}")
    else:
        print(f"\n  SKIPPED: plugin-qwen-cpu not installed")

    print(f"\n{'=' * 60}")
    print(f"  Diagnostic complete.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    _run_standalone()
