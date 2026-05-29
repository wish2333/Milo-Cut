"""Comprehensive E2E test: All engines x All models x CPU/CUDA -> SRT generation.

Coverage:
- Engine: faster-whisper (plugin-whisper), qwen3-asr (plugin-qwen-cpu/gpu)
- Models: All downloaded models (base, large-v3-turbo, Qwen 0.6B/1.7B)
- Device: cpu, cuda
- Output: SRT subtitle file validation

Usage:
    uv run python tests/test_e2e_srt.py              # all tests
    uv run python tests/test_e2e_srt.py --quick       # whisper-base CPU only
    uv run python tests/test_e2e_srt.py --engine whisper
    uv run python tests/test_e2e_srt.py --device cuda
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

TEST_VIDEO = PROJECT_ROOT / "test" / "test.mp4"
OUTPUT_DIR = PROJECT_ROOT / "data" / "plugins" / "tasks"
TIMEOUT = 300  # seconds per transcription

# Engine -> (plugin_id, script_name, model_resolver)
ENGINE_CONFIG = {
    "whisper": {
        "plugin_id": "plugin-whisper",
        "script": "core/asr_scripts/whisper_transcribe.py",
        "models": {
            "Systran/faster-whisper-base": {"plugin_id": "plugin-whisper"},
            "Purfview/faster-whisper-large-v3-turbo": {"plugin_id": "plugin-whisper"},
        },
        "arg_template": [
            "--media-path", "{video}",
            "--model-path", "{model_path}",
            "--language", "zh",
            "--device", "{device}",
            "--compute-type", "int8",
            "--word-timestamps", "true",
            "--vad-filter", "true",
        ],
    },
    "qwen3-asr": {
        "plugin_id": "plugin-qwen-cpu",
        "script": "core/asr_scripts/qwen_transcribe.py",
        "models": {
            "Qwen/Qwen3-ASR-0.6B": {"plugin_id": "plugin-qwen-cpu"},
            "Qwen/Qwen3-ASR-1.7B": {"plugin_id": "plugin-qwen-cpu"},
        },
        "known_issue": "qwen_transcribe.py uses AutoModelForSpeechSeq2Seq but Qwen3-ASR needs qwen-asr package (Qwen3ASRModel)",
        "arg_template": [
            "--media-path", "{video}",
            "--asr-model-path", "{asr_model_path}",
            "--aligner-model-path", "{aligner_model_path}",
            "--language", "zh",
            "--device", "{device}",
        ],
    },
}


def run_test_case(engine: str, model_id: str, device: str) -> dict:
    """Run a single transcription + SRT test case."""
    from core.plugin_manager import PluginManager
    from core.export_service import export_srt

    pm = PluginManager()
    config = ENGINE_CONFIG[engine]
    model_path = pm.ensure_model(model_id)

    progress_log = []
    def progress_cb(pct, msg):
        progress_log.append((pct, msg))

    # Build args
    if engine == "qwen3-asr":
        # Select GPU or CPU plugin based on device
        if device == "cuda":
            config["plugin_id"] = "plugin-qwen-gpu"
            config["models"][model_id]["plugin_id"] = "plugin-qwen-gpu"
        else:
            config["plugin_id"] = "plugin-qwen-cpu"
            config["models"][model_id]["plugin_id"] = "plugin-qwen-cpu"

        aligner_path = pm.ensure_model("Qwen/Qwen3-ForcedAligner-0.6B")
        args = []
        for arg in config["arg_template"]:
            if arg == "{video}":
                args.append(str(TEST_VIDEO))
            elif arg == "{asr_model_path}":
                args.append(str(model_path))
            elif arg == "{aligner_model_path}":
                args.append(str(aligner_path))
            elif arg == "{device}":
                args.append(device)
            else:
                args.append(arg)
    else:
        args = []
        for arg in config["arg_template"]:
            if arg == "{video}":
                args.append(str(TEST_VIDEO))
            elif arg == "{model_path}":
                args.append(str(model_path))
            elif arg == "{device}":
                args.append(device)
            else:
                args.append(arg)

    script_path = PROJECT_ROOT / config["script"]
    plugin_id = config["plugin_id"]

    start = time.time()
    task = pm.run_in_plugin(plugin_id, script_path, args=args, progress_cb=progress_cb)
    task.process.wait(timeout=TIMEOUT)
    elapsed = time.time() - start

    result = {
        "engine": engine,
        "model": model_id,
        "device": device,
        "elapsed": round(elapsed, 1),
        "exit_code": task.process.returncode,
        "segment_count": 0,
        "srt_valid": False,
        "srt_has_chinese": False,
        "srt_segments": 0,
        "error": None,
    }

    if task.process.returncode != 0:
        result["error"] = f"Exit code {task.process.returncode}"
        # Check log
        log_path = str(task.result_path).replace("_result.json", ".log")
        if Path(log_path).exists():
            log = Path(log_path).read_text(encoding="utf-8", errors="replace")
            if log.strip():
                result["error"] += f" | {log[:200]}"
        return result

    # Read transcription result
    if not Path(task.result_path).exists():
        result["error"] = "Result file missing"
        return result

    with open(task.result_path, "r", encoding="utf-8") as f:
        trans_result = json.load(f)

    result["segment_count"] = trans_result.get("segment_count", 0)

    # Generate SRT
    srt_path = OUTPUT_DIR / f"{engine}_{model_id.split('/')[-1]}_{device}.srt"
    segments = []
    for seg in trans_result.get("segments", []):
        segments.append({
            "id": seg["id"],
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "type": "subtitle",
        })

    export_result = export_srt(
        segments=segments,
        edits=[],
        output_path=str(srt_path),
        media_duration=trans_result.get("duration", 0),
    )

    if not export_result.get("success"):
        result["error"] = f"SRT export failed: {export_result.get('error')}"
        return result

    # Validate SRT
    if srt_path.exists():
        content = srt_path.read_text(encoding="utf-8")
        result["srt_valid"] = "-->" in content
        result["srt_has_chinese"] = any("\u4e00" <= c <= "\u9fff" for c in content)
        result["srt_segments"] = content.count("-->")

    return result


def main():
    parser = argparse.ArgumentParser(description="E2E SRT generation test")
    parser.add_argument("--quick", action="store_true", help="Run only whisper-base CPU")
    parser.add_argument("--engine", choices=["whisper", "qwen3-asr"], help="Test specific engine")
    parser.add_argument("--device", choices=["cpu", "cuda"], help="Test specific device")
    args = parser.parse_args()

    # Build test matrix
    test_cases = []
    if args.quick:
        test_cases.append(("whisper", "Systran/faster-whisper-base", "cpu"))
    else:
        engines = [args.engine] if args.engine else ENGINE_CONFIG.keys()
        devices = [args.device] if args.device else ["cpu", "cuda"]

        for engine in engines:
            for model_id in ENGINE_CONFIG[engine]["models"]:
                for device in devices:
                    test_cases.append((engine, model_id, device))

    print("=" * 70)
    print(f"E2E Test: Transcription -> SRT Generation")
    print(f"  Test cases: {len(test_cases)}")
    print(f"  Video: {TEST_VIDEO}")
    print("=" * 70)

    results = []
    for engine, model_id, device in test_cases:
        print(f"\n--- {engine} | {model_id} | {device} ---")
        result = run_test_case(engine, model_id, device)
        results.append(result)

        status = "PASS" if result["srt_valid"] and result["srt_has_chinese"] else "FAIL"
        print(f"  [{status}] {result['elapsed']}s, "
              f"{result['segment_count']} segs, "
              f"SRT: {result['srt_segments']} segs, "
              f"CN={result['srt_has_chinese']}")
        if result["error"]:
            print(f"  ERROR: {result['error']}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r["srt_valid"] and r["srt_has_chinese"])
    failed = len(results) - passed
    print(f"  Passed: {passed}/{len(results)}")
    print(f"  Failed: {failed}/{len(results)}")

    for r in results:
        status = "PASS" if r["srt_valid"] and r["srt_has_chinese"] else "FAIL"
        print(f"  [{status}] {r['engine']} | {r['model']} | {r['device']} | "
              f"{r['elapsed']}s | {r['segment_count']} segs")
        if r["error"]:
            print(f"         Error: {r['error']}")

    if failed > 0:
        print(f"\n{failed} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} tests PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
