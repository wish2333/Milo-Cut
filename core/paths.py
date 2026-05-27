"""Centralized application data paths.

Migrated from ff-intelligent-neo core/paths.py, adapted for Milo-Cut.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "milo-cut"


def get_app_dir() -> Path:
    """Return the application root directory.

    - Frozen (PyInstaller): directory containing the executable.
    - Development: project root (parent of this file's parent).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Return the data directory, creating it if needed."""
    d = get_app_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    """Return the log directory."""
    d = get_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_path() -> Path:
    """Return the settings file path."""
    return get_data_dir() / "settings.json"


def get_projects_dir() -> Path:
    """Return the default projects directory."""
    d = get_data_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_temp_dir() -> Path:
    """Return temp directory for export intermediate files."""
    d = get_data_dir() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_plugin_data_dir() -> Path:
    """Return the cross-platform plugin data directory.

    - Windows: %LOCALAPPDATA%/MiloCut/
    - macOS: ~/Library/Application Support/MiloCut/
    - Linux: ~/.local/share/milocut/

    This directory persists across app updates and is suitable for
    plugin venvs, ML models, and plugin registries.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / "MiloCut"
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "MiloCut"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        d = base / "milocut"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _old_appdata_dir() -> Path | None:
    """Check for legacy data in APPDATA / XDG_CONFIG_HOME."""
    if sys.platform == "win32":
        candidate = Path(os.environ.get("APPDATA", "")) / APP_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        candidate = Path(base) / APP_NAME
    return candidate if candidate.is_dir() else None


def migrate_if_needed() -> None:
    """One-time migration from legacy APPDATA location to local data/."""
    old = _old_appdata_dir()
    if old is None:
        return
    new = get_data_dir()
    if new.exists() and any(new.iterdir()):
        return
    shutil.copytree(old, new, dirs_exist_ok=True)
