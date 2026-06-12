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


def _read_version() -> str:
    """Read version from pyproject.toml (single source of truth)."""
    try:
        import tomllib
        with open(project_root / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "0.0.0"


__version__ = _read_version()


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
# Bundle pyproject.toml so core.__version__ can read it at runtime
datas.append((str(project_root / "pyproject.toml"), "."))

# ASR subprocess scripts (macOS .app bundle needs them as datas)
if sys.platform == "darwin":
    _asr_scripts = project_root / "core" / "asr_scripts"
    if _asr_scripts.is_dir():
        datas.append((str(_asr_scripts), "core/asr_scripts"))

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
    "core.asr_service",
    "core.plugin_manager",
    "core.media_server",
    "core.export_timeline",
    "core.ffmpeg_presets",
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

# ========== ML backend excludes ==========
# ASR transcription runs in isolated subprocesses (via uv-managed envs),
# NOT inside the main process.  These heavy packages are only needed at
# subprocess runtime and must NOT be bundled into the desktop executable.
ML_EXCLUDES = [
    # -- Deep learning frameworks (hundreds of MB) --
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "tensorflow_core",
    "keras",
    "jax",
    "jaxlib",
    "flax",
    # -- ONNX runtime --
    "onnxruntime",
    "onnx",
    # -- HuggingFace heavy deps --
    "transformers",
    "accelerate",
    "safetensors",
    "tokenizers",
    "huggingface_hub",      # model download only, lazy-imported in plugin_manager
    "hf_xet",               # XET storage backend for huggingface_hub (8.8 MB)
    # -- ModelScope --
    "modelscope",           # model download only, lazy-imported in plugin_manager
    # -- CTranslate2 / faster-whisper --
    "ctranslate2",
    "faster_whisper",
    # -- Heavy scientific / ML transitive deps --
    "numpy",
    "scipy",
    "pandas",
    "sklearn",
    "scikit_learn",
    "matplotlib",
    "PIL",
    "Pillow",
    "cv2",
    "opencv",
    "tqdm",                 # progress bars, not needed in bundled app
    "datasets",
    "evaluate",
    "librosa",
    "soundfile",
    "audioread",
    # -- Misc heavy unused --
    "notebook",
    "ipython",
    "ipykernel",
    "jupyter",
]


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

# Apply platform-specific GUI excludes
if sys.platform == "win32":
    a.excludes += EXCLUDES_WIN32
elif sys.platform == "linux":
    a.excludes += EXCLUDES_LINUX
elif sys.platform == "darwin":
    a.excludes += EXCLUDES_DARWIN

# Apply ML backend excludes (ASR runs in subprocesses, not main process)
a.excludes += ML_EXCLUDES

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

# macOS .app bundle
if sys.platform == "darwin":
    BUNDLE(
        coll,
        name="Milo Cut.app",
        icon=ICON,
        bundle_identifier="com.milocut.app",
        info_plist={
            "CFBundleName": "Milo Cut",
            "CFBundleDisplayName": "Milo Cut",
            "CFBundleVersion": __version__,
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13",
        },
    )
