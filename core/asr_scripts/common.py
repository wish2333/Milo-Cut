"""Common utilities for ASR subprocess scripts.

Every subprocess script launched via PluginManager.run_in_plugin() should
import this module and use report() for stdout IPC and start_stdin_watchdog()
for orphan process defense.

Usage in a subprocess script:

    from core.asr_scripts.common import report, start_stdin_watchdog, parse_args

    def main():
        args = parse_args()
        start_stdin_watchdog()
        report("progress", percent=10.0, message="Loading model...")
        # ... do work ...
        report("result", path=str(args.result_path))
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from typing import Any


def report(event_type: str, **kwargs: Any) -> None:
    """Write a JSON event to stdout for the parent process.

    Event types:
    - "progress": percent (float), message (str)
    - "result": path (str) -- path to the result JSON file
    - "error": message (str)
    - "log": message (str)
    """
    event = {"type": event_type, **kwargs}
    line = json.dumps(event, ensure_ascii=False)
    print(line, flush=True)


def start_stdin_watchdog() -> None:
    """Start a daemon thread that watches stdin for EOF.

    When the parent process exits or crashes, the stdin pipe breaks (EOF).
    The watchdog detects this and calls os._exit(1) to prevent orphan processes.

    This MUST be called at the start of every subprocess script.
    """

    def _watchdog() -> None:
        try:
            # Block until stdin closes (parent exits)
            while sys.stdin.read(1):
                pass
        except Exception:
            pass
        # Parent is gone -- self-terminate
        os._exit(1)

    thread = threading.Thread(target=_watchdog, daemon=True, name="stdin-watchdog")
    thread.start()


def parse_args() -> argparse.Namespace:
    """Parse common arguments for ASR subprocess scripts.

    All scripts receive --result-path so they know where to write output.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--result-path", required=True, help="Path to write result JSON")
    return parser.parse_known_args()[0]


def write_result(result_path: str, data: dict[str, Any]) -> None:
    """Write the final result to a JSON file and notify the parent via stdout.

    This avoids piping large result data through stdout (which can overflow
    the OS pipe buffer for word-level timestamps on long videos).
    """
    import pathlib

    path = pathlib.Path(result_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report("result", path=str(path))
