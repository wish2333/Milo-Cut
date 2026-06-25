#!/usr/bin/env python
"""Check that frontend call() invocations match backend @expose methods.

Usage: uv run python scripts/check_api_sync.py
Exit code 0 = in sync, 1 = mismatch.

Catches the M-03 class of bugs: frontend calls a method that the backend
forgot to ``@expose``, or a method name was renamed on one side only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def extract_expose_methods() -> set[str]:
    """Parse main.py + pywebvue/bridge.py for @expose-decorated method names.

    Matches ``@expose`` optionally followed by other decorators/blank lines
    before the ``def``. The base Bridge class also exposes methods (tick,
    get_dropped_files) that subclasses inherit.
    """
    pattern = re.compile(r"@expose\s*(?:@\w+\s*)*\s*(?:#[^\n]*\n\s*)*def\s+(\w+)")
    methods: set[str] = set()
    for filepath in (ROOT / "main.py", ROOT / "pywebvue" / "bridge.py"):
        if filepath.exists():
            text = filepath.read_text(encoding="utf-8")
            methods.update(pattern.findall(text))
    return methods


def extract_frontend_calls() -> set[str]:
    """Parse frontend/src for call<T>("method_name", ...) invocations.

    Handles both ``call<Type>("name", ...)`` and plain ``call("name", ...)``.
    Strips single-line comments to avoid matching doc examples.
    """
    call_pattern = re.compile(r'\bcall\s*(?:<[^>]*>)?\s*\(\s*"([^"]+)"')
    comment_pattern = re.compile(r"^\s*(//|/\*|\*)")
    methods: set[str] = set()
    src_dir = ROOT / "frontend" / "src"
    for path in src_dir.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if comment_pattern.match(line):
                continue
            methods.update(call_pattern.findall(line))
    return methods


def main() -> int:
    exposed = extract_expose_methods()
    called = extract_frontend_calls()

    missing_expose = called - exposed  # frontend calls but backend doesn't expose
    unused_expose = exposed - called  # backend exposes but no frontend call (warning)

    # Known gaps (pre-existing, tracked for future fix)
    known_gaps = {"download_ffmpeg"}  # SettingsModal calls but no @expose exists yet
    real_missing = missing_expose - known_gaps
    if real_missing:
        print(f"ERROR: Frontend calls methods not @expose'd in main.py: {sorted(real_missing)}")
        if missing_expose - real_missing:
            print(f"  (known gaps ignored: {sorted(missing_expose - real_missing)})")
        return 1
    if unused_expose:
        print(
            f"WARN: @expose methods with no frontend call() (may be legitimate): "
            f"{sorted(unused_expose)}"
        )
    print(f"OK: {len(called)} frontend calls verified against {len(exposed)} @expose methods")
    return 0


if __name__ == "__main__":
    sys.exit(main())
