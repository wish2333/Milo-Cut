# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# PyInstaller spec for PyWebVue desktop applications
# ============================================================
#
# Usage:
#   pyinstaller --clean app.spec       onedir build (folder + exe)
#   uv run build.py                    onedir build (same as above)
#   uv run build.py --onefile          onefile build (single exe)
#
# ---------- USER CONFIGURATION ----------
# The sections marked [MODIFY] are where you should customize
# for your own project. Everything else usually works as-is.
# =============================================


import sys
from pathlib import Path

project_root = Path(SPECPATH)


# ========== [MODIFY] Entry point ==========
# Change this to your main Python script path.
# Default: main.py (at project root)
ENTRY_SCRIPT = str(project_root / "main.py")


# ========== [MODIFY] Output name ==========
# The name of the generated executable (without extension).
# Default: "app"
APP_NAME = "milo-cut"


# ========== [MODIFY] Frontend assets ==========
# How to bundle your frontend:
#
#   Standard: bundle the Vite build output directory
#     datas = [(str(project_root / "frontend_dist"), "frontend_dist")]
#
#   Custom: bundle your own directory
#     datas = [(str(project_root / "my_dist"), "my_dist")]
#
# Build frontend first:  cd frontend && npm run build
# Output goes to:        frontend_dist/
_frontend_dist = project_root / "frontend_dist"
datas = [(str(_frontend_dist), "frontend_dist")]

# opentimelineio plugin manifest (JSON data files not auto-collected by PyInstaller)
try:
    import opentimelineio
    _otio_dir = Path(opentimelineio.__file__).parent
    _otio_manifest = _otio_dir / "adapters" / "builtin_adapters.plugin_manifest.json"
    if _otio_manifest.exists():
        datas.append((str(_otio_manifest), "opentimelineio/adapters"))
except ImportError:
    pass


# ========== [MODIFY] Icon ==========
# Path to your .ico (Windows) or .icns (macOS) icon file.
# Set to None to use the default icon.
ICON = None  # Example: str(project_root / "assets" / "icon.ico")


# ========== [MODIFY] Hidden imports ==========
# If you import additional Python packages in your code,
# add them here so PyInstaller can find them.
hiddenimports = [
    "pywebvue",
    "pywebvue.app",
    "pywebvue.bridge",
    "core",
    "core.events",
    "core.paths",
    "core.config",
    "core.logging",
    "core.models",
    "core.ffmpeg_service",
    "core.subtitle_service",
    "core.task_manager",
    "core.project_service",
]


# ========== [MODIFY] GUI framework excludes ==========
# pywebview auto-selects the best engine per platform:
#   Windows  -> EdgeWebView2 (or CEF if no Edge)
#   macOS    -> Cocoa WebKit
#   Linux    -> GTK WebKit
#
# Exclude GUI frameworks you are NOT using to reduce bundle size.
# Only modify this if you know what you are doing.
EXCLUDES_WIN32 = ["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"]
EXCLUDES_LINUX = ["PyQt5", "PyQt6", "PySide2", "PySide6"]
EXCLUDES_DARWIN = ["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"]


# ========== Usually no need to modify below ==========

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

if sys.platform == "win32":
    a.excludes += EXCLUDES_WIN32
elif sys.platform == "linux":
    a.excludes += EXCLUDES_LINUX
elif sys.platform == "darwin":
    a.excludes += EXCLUDES_DARWIN

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
