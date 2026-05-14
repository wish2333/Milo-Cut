#!/usr/bin/env bash
# PyWebVue development startup script (macOS / Linux)
#
# Usage:
#   ./dev.sh              Demo mode
#   ./dev.sh --vite       Vue dev mode
#   ./dev.sh --setup      Only install dependencies
#   ./dev.sh --help       Show all options
#
# All arguments are passed to dev.py

set -euo pipefail

if ! command -v uv &>/dev/null; then
    echo "[ERROR] uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

uv run dev.py "$@"
