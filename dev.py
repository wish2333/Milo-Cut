# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""PyWebVue one-click development startup script.

Cross-platform (Windows / macOS / Linux).

============================================================
Usage
============================================================

    uv run dev.py              Start Vite dev server + app (default)
    uv run dev.py --no-vite    Load frontend_dist/ from disk (no Vite)
    uv run dev.py --setup      Only install dependencies

============================================================
How it works
============================================================

    1. uv sync                        Install Python dependencies
    2. npm/bun install                 Install frontend dependencies
    3. Start Vite dev server           Background process at :5173
    4. Start main.py                   Launch the pywebview window
    5. On exit (Ctrl+C or window close): stop all background processes

============================================================
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
_bg_procs: list[subprocess.Popen] = []

DEFAULT_FRONTEND_DIR = PROJECT_ROOT / "frontend"


# ================================================================
# Helpers
# ================================================================

def _info(msg: str) -> None:
    print(f"[INFO] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def _find_cmd(*names: str) -> str | None:
    """Return the first available command, or None."""
    for name in names:
        if shutil.which(name) is not None:
            return name
    return None


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command, exit on failure."""
    _info(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        _error(f"Command failed (exit {r.returncode}): {' '.join(cmd)}")


def _spawn_bg(cmd: list[str], cwd: Path | None = None) -> None:
    """Start a background process (registered for cleanup on exit)."""
    _info(f"  $ {' '.join(cmd)}  [background]")
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(cmd, cwd=cwd, **kw)
    _bg_procs.append(proc)


def _kill_bg() -> None:
    """Terminate all background processes."""
    for proc in _bg_procs:
        if proc.poll() is not None:
            continue
        try:
            if sys.platform == "win32":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
            proc.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
            proc.kill()
    _bg_procs.clear()


# ================================================================
# Setup
# ================================================================

def _setup_python() -> None:
    """Install Python dependencies via uv."""
    uv = _find_cmd("uv")
    if uv is None:
        _error("uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/")
    _info("[1] Installing Python dependencies...")
    _run([uv, "sync"], cwd=PROJECT_ROOT)


def _setup_frontend(frontend_dir: Path) -> str:
    """Install frontend dependencies. Returns the package manager name."""
    pm = _find_cmd("bun", "npm", "yarn")
    if pm is None:
        _error("No package manager found. Install bun/npm/yarn first.")
    _info("[2] Installing frontend dependencies...")
    _run([pm, "install"], cwd=frontend_dir)
    return pm


# ================================================================
# Start
# ================================================================

def _start_vite(frontend_dir: Path, pm: str) -> None:
    """Start Vite dev server in background and wait for it to be ready."""
    import time
    import urllib.request

    _info(f"[3] Starting Vite dev server ({pm})...")
    _spawn_bg([pm, "run", "dev"], cwd=frontend_dir)

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen("http://localhost:5173", timeout=1)
            _info("    Vite ready at http://localhost:5173")
            return
        except Exception:
            time.sleep(0.5)
    _error("Vite dev server failed to start on port 5173 within 20s")


def _start_app(env_extra: dict[str, str] | None = None) -> None:
    """Start main.py via uv run to use the project .venv."""
    uv = _find_cmd("uv")
    if uv is None:
        _error("uv not found.")

    main_py = PROJECT_ROOT / "main.py"
    if not main_py.exists():
        _error(f"Entry script not found: {main_py}")

    env = {**os.environ}
    if env_extra:
        env.update(env_extra)

    cmd = [uv, "run", str(main_py)]
    _info(f"Starting app: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    except KeyboardInterrupt:
        pass


# ================================================================
# Signal handling
# ================================================================

def _on_signal(signum: int, _frame) -> None:
    _info("\nShutting down...")
    _kill_bg()
    sys.exit(0)


# ================================================================
# Main
# ================================================================

def main() -> None:
    ap = argparse.ArgumentParser(
        description="PyWebVue one-click dev startup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  uv run dev.py                           Start Vite + app (default)
  uv run dev.py --no-vite                  Load from disk (production preview)
  uv run dev.py --frontend-dir ./my-app    Custom Vue project path
  uv run dev.py --setup                    Only install dependencies
""",
    )
    ap.add_argument("--no-vite", action="store_true",
                    help="Skip Vite, load frontend from disk")
    ap.add_argument("--setup", action="store_true",
                    help="Only install dependencies, then exit")
    ap.add_argument("--frontend-dir", type=str, default=None,
                    help="Vue project root with package.json (default: ./frontend)")
    args = ap.parse_args()

    # Graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, _on_signal)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _on_signal)

    # --- Step 1: Python deps ---
    _setup_python()

    # --- Step 2: Frontend deps ---
    frontend_dir = (
        Path(args.frontend_dir) if args.frontend_dir
        else DEFAULT_FRONTEND_DIR
    )
    pm: str | None = None
    if not args.no_vite:
        if not (frontend_dir / "package.json").exists():
            _error(f"No package.json in {frontend_dir}. "
                   f"Use --frontend-dir to point to your Vue project.")
        pm = _setup_frontend(frontend_dir)

    if args.setup:
        _info("Setup complete.")
        return

    # --- Step 3: Vite dev server (background) ---
    if not args.no_vite and pm:
        _start_vite(frontend_dir, pm)

    # --- Step 4: Start the app ---
    try:
        _start_app()
    finally:
        _kill_bg()


if __name__ == "__main__":
    main()
