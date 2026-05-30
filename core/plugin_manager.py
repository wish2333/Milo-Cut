"""Plugin manager for isolated ASR engine environments.

Uses uv to create isolated virtual environments for each ASR plugin,
keeping the main application free of heavy ML dependencies (PyTorch, CTranslate2).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from core.paths import get_plugin_data_dir

# ================================================================
# Plugin registry -- single source of truth for available plugins
# ================================================================

PLUGIN_REGISTRY: dict[str, dict[str, Any]] = {
    "plugin-whisper": {
        "display_name": "Faster Whisper ASR",
        "engine": "faster-whisper",
        "dependencies": ["faster-whisper>=1.0.0"],
        "models": {
            "Purfview/faster-whisper-large-v3-turbo": {
                "display_name": "Large V3 Turbo (recommended)",
                "size_bytes": 1_500_000_000,
            },
            "Systran/faster-whisper-base": {
                "display_name": "Base (lightweight)",
                "size_bytes": 74_000_000,
            },
        },
    },
    "plugin-qwen-cpu": {
        "display_name": "Qwen3 ASR (CPU)",
        "engine": "qwen3-asr",
        "dependencies": ["qwen-asr", "transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
        "models": {
            "Qwen/Qwen3-ASR-0.6B": {
                "display_name": "Qwen3 ASR 0.6B (lightweight)",
                "size_bytes": 1_880_000_000,
            },
            "Qwen/Qwen3-ASR-1.7B": {
                "display_name": "Qwen3 ASR 1.7B (recommended)",
                "size_bytes": 4_700_000_000,
            },
            "Qwen/Qwen3-ForcedAligner-0.6B": {
                "display_name": "Qwen3 ForcedAligner 0.6B",
                "size_bytes": 1_840_000_000,
            },
        },
    },
    "plugin-qwen-gpu": {
        "display_name": "Qwen3 ASR (GPU)",
        "engine": "qwen3-asr",
        "dependencies": ["qwen-asr", "transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
        "pytorch_index": "https://download.pytorch.org/whl/cu124",
        "models": {
            "Qwen/Qwen3-ASR-0.6B": {
                "display_name": "Qwen3 ASR 0.6B (lightweight)",
                "size_bytes": 1_880_000_000,
            },
            "Qwen/Qwen3-ASR-1.7B": {
                "display_name": "Qwen3 ASR 1.7B (recommended)",
                "size_bytes": 4_700_000_000,
            },
            "Qwen/Qwen3-ForcedAligner-0.6B": {
                "display_name": "Qwen3 ForcedAligner 0.6B",
                "size_bytes": 1_840_000_000,
            },
        },
    },
    "plugin-qwen-mlx": {
        "display_name": "Qwen3 ASR (Apple Silicon)",
        "engine": "qwen3-asr",
        "dependencies": ["mlx-qwen3-asr[aligner]"],
        "models": {
            "Qwen/Qwen3-ASR-0.6B": {
                "display_name": "Qwen3 ASR 0.6B (lightweight)",
                "size_bytes": 1_880_000_000,
            },
            "Qwen/Qwen3-ASR-1.7B": {
                "display_name": "Qwen3 ASR 1.7B (recommended)",
                "size_bytes": 4_700_000_000,
            },
            "Qwen/Qwen3-ForcedAligner-0.6B": {
                "display_name": "Qwen3 ForcedAligner 0.6B",
                "size_bytes": 1_840_000_000,
            },
        },
    },
}


PYTORCH_MIRRORS: dict[str, dict[str, Any]] = {
    "official": {
        "name": "Official (Recommended)",
        "url": "https://download.pytorch.org/whl/cu124",
        "stable": True,
        "note": "Most reliable, may be slow in China",
    },
    "aliyun": {
        "name": "Alibaba Cloud",
        "url": "https://mirrors.aliyun.com/pytorch-wheels/cu124",
        "stable": True,
        "note": "Stable but may lag behind official",
    },
    "nju": {
        "name": "Nanjing University",
        "url": "https://mirrors.nju.edu.cn/pytorch/whl/cu124",
        "stable": False,
        "note": "Newer but stability unknown",
    },
}


# ================================================================
# Model download mirrors
# ================================================================

MODEL_MIRRORS: dict[str, dict[str, str]] = {
    "huggingface": {
        "id": "huggingface",
        "display_name": "HuggingFace (Global)",
        "endpoint": "https://huggingface.co",
    },
    "hf-mirror": {
        "id": "hf-mirror",
        "display_name": "HF-Mirror (China)",
        "endpoint": "https://hf-mirror.com",
    },
    "modelscope": {
        "id": "modelscope",
        "display_name": "ModelScope (China)",
        "endpoint": "",
    },
}

# Mapping from HuggingFace model IDs to ModelScope equivalents.
# Models not listed here are assumed to use the same ID on both platforms.
MODELSCOPE_ID_MAP: dict[str, str] = {
    "Purfview/faster-whisper-large-v3-turbo": "Purfview/faster-whisper-large-v3-turbo",
    "Systran/faster-whisper-base": "Systran/faster-whisper-base",
}


# ================================================================
# Subprocess task state
# ================================================================


class SubprocessState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubprocessTask:
    """Tracks the state of a subprocess launched via run_in_plugin."""

    task_id: str
    process: subprocess.Popen | None = None
    state: SubprocessState = SubprocessState.PENDING
    returncode: int | None = None
    error: str = ""
    result_path: str = ""
    log_lines: list[str] = field(default_factory=list)


# ================================================================
# Helper functions
# ================================================================


def _get_uv_path() -> Path:
    """Locate the uv binary.

    Priority:
    1. Next to the frozen executable (PyInstaller bundle).
    2. Next to the main script (development).
    3. On PATH.
    """
    # Frozen: uv bundled alongside the exe
    if getattr(sys, "frozen", False):
        frozen_dir = Path(sys.executable).parent
        for name in ("uv.exe", "uv"):
            candidate = frozen_dir / name
            if candidate.is_file():
                return candidate

    # Development: uv next to the project root
    dev_dir = Path(__file__).resolve().parent.parent
    for name in ("uv.exe", "uv"):
        candidate = dev_dir / name
        if candidate.is_file():
            return candidate

    # PATH fallback
    found = shutil.which("uv")
    if found:
        return Path(found)

    raise FileNotFoundError(
        "uv binary not found. Install from https://github.com/astral-sh/uv/releases "
        "or place uv.exe in the application directory."
    )


def _clean_subprocess_env() -> dict[str, str]:
    """Return a clean environment dict for subprocess calls.

    Removes PyInstaller-injected variables that conflict with plugin venvs:
    - PYTHONPATH: PyInstaller modifies this for frozen modules
    - PYTHONHOME: PyInstaller sets this to the frozen Python prefix
    - LD_LIBRARY_PATH: may cause C extension symbol conflicts on Linux

    Also sets variables to prevent ML libraries from polluting stdout,
    which would corrupt the JSON IPC protocol (tqdm writes \\r-based
    progress bars without \\n, causing pipe buffer deadlocks).
    """
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    if sys.platform != "win32":
        env.pop("LD_LIBRARY_PATH", None)

    # Prevent tqdm and ML libraries from writing progress bars to stdout.
    # These libraries use \\r (not \\n) which corrupts our JSON-line IPC
    # protocol and can cause pipe buffer deadlocks on Windows.
    env["TQDM_DISABLE"] = "1"
    env["TRANSFORMERS_VERBOSITY"] = "error"
    env["CT2_VERBOSE"] = "0"  # suppress CTranslate2 info messages

    return env


def _detect_download_source() -> str:
    """Detect the best model download source based on network conditions.

    Returns one of:
    - "huggingface": direct HuggingFace Hub (default for international)
    - "modelscope": ModelScope mirror (better for mainland China)
    - "hf-mirror": hf-mirror.com proxy (HuggingFace mirror in China)
    """
    import socket

    # Quick connectivity check to HuggingFace
    try:
        socket.setdefaulttimeout(3)
        sock = socket.create_connection(("huggingface.co", 443), timeout=3)
        sock.close()
        return "huggingface"
    except (socket.timeout, OSError):
        pass

    # Try hf-mirror
    try:
        socket.setdefaulttimeout(3)
        sock = socket.create_connection(("hf-mirror.com", 443), timeout=3)
        sock.close()
        return "hf-mirror"
    except (socket.timeout, OSError):
        pass

    # Fallback to ModelScope
    return "modelscope"


def detect_gpu() -> dict[str, Any]:
    """Detect GPU status for plugin installation recommendations.

    Returns:
        dict with keys:
        - has_nvidia_gpu: Whether an NVIDIA GPU was detected
        - cuda_available: Whether CUDA runtime is usable (via nvidia-smi)
        - cuda_version: CUDA version string or None
        - gpu_name: GPU model name or None
        - recommendation: "gpu", "cpu", or "install_cuda"
        - cuda_download_url: URL to download CUDA toolkit or None
    """
    result: dict[str, Any] = {
        "has_nvidia_gpu": False,
        "cuda_available": False,
        "cuda_version": None,
        "gpu_name": None,
        "recommendation": "cpu",
        "cuda_download_url": None,
    }

    # Try nvidia-smi (works even without PyTorch, detects CUDA from driver)
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
            **_subprocess_kwargs(),
        )
        if proc.returncode == 0:
            output = proc.stdout
            # Parse GPU name
            for line in output.split("\n"):
                if "|" in line and "NVIDIA" in line and "GPU" in line:
                    # e.g. "| NVIDIA GeForce RTX 4090 ... |"
                    parts = line.split("|")
                    for part in parts:
                        part = part.strip()
                        if "NVIDIA" in part and "GPU" in part:
                            result["has_nvidia_gpu"] = True
                            result["gpu_name"] = part.split("  ")[0].strip()
                            break
                    if result["has_nvidia_gpu"]:
                        break
            # Fallback: query GPU name directly
            if not result["has_nvidia_gpu"]:
                proc2 = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=5,
                    **_subprocess_kwargs(),
                )
                if proc2.returncode == 0 and proc2.stdout.strip():
                    result["has_nvidia_gpu"] = True
                    result["gpu_name"] = proc2.stdout.strip().split("\n")[0]

            # Parse CUDA version from nvidia-smi header
            # e.g. "CUDA Version: 12.4"
            for line in output.split("\n"):
                if "CUDA Version" in line:
                    import re
                    match = re.search(r"CUDA Version:\s*([\d.]+)", line)
                    if match:
                        result["cuda_available"] = True
                        result["cuda_version"] = match.group(1)
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Build recommendation
    if result["cuda_available"]:
        result["recommendation"] = "gpu"
    elif result["has_nvidia_gpu"]:
        result["recommendation"] = "install_cuda"
        result["cuda_download_url"] = "https://developer.nvidia.com/cuda-downloads"
    else:
        result["recommendation"] = "cpu"

    return result


# ================================================================
# PluginManager core class
# ================================================================


class PluginManager:
    """Manages ASR plugin lifecycle: install, uninstall, model download, subprocess IPC."""

    def __init__(
        self,
        plugins_dir: Path | None = None,
        model_dir: Path | None = None,
    ) -> None:
        self._plugins_dir = plugins_dir or get_plugin_data_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)

        # Model directory is decoupled from plugins_dir.
        # registry.json, tasks/, venv/ stay in plugins_dir; only models/ moves here.
        # Custom model_dir must be defensive -- a bad path must not crash startup.
        default_model_dir = self._plugins_dir / "models"
        if model_dir:
            try:
                self._model_dir = Path(model_dir)
                self._model_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(
                    "Custom model_dir {} is invalid ({}), falling back to default",
                    model_dir,
                    e,
                )
                self._model_dir = default_model_dir
                self._model_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._model_dir = default_model_dir
            self._model_dir.mkdir(parents=True, exist_ok=True)

        self._registry_path = self._plugins_dir / "registry.json"
        self._tasks_dir = self._plugins_dir / "tasks"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

        self._registry: dict[str, dict[str, Any]] = self._load_registry()
        self._subprocess_tasks: dict[str, SubprocessTask] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------
    # Registry persistence
    # ------------------------------------------------------------

    def _load_registry(self) -> dict[str, dict[str, Any]]:
        """Load the plugin registry from disk."""
        if not self._registry_path.exists():
            return {}
        try:
            return json.loads(self._registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load plugin registry: {}", exc)
            return {}

    def _save_registry(self) -> None:
        """Save the plugin registry to disk with atomic write."""
        tmp = self._registry_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._registry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self._registry_path)

    # ------------------------------------------------------------
    # Plugin queries
    # ------------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return all registered plugins with their installation status.

        Platform filtering:
        - macOS: show MLX variant, hide GPU variant
        - non-macOS: hide MLX variant
        """
        result: list[dict[str, Any]] = []
        for plugin_id, meta in PLUGIN_REGISTRY.items():
            # Platform filtering
            is_mlx = plugin_id == "plugin-qwen-mlx"
            is_gpu = plugin_id == "plugin-qwen-gpu"
            if is_mlx and sys.platform != "darwin":
                continue
            if is_gpu and sys.platform == "darwin":
                continue

            entry = self._registry.get(plugin_id, {})
            result.append({
                "plugin_id": plugin_id,
                "display_name": meta["display_name"],
                "engine": meta["engine"],
                "version": entry.get("version", "1.0.0"),
                "status": "installed" if entry.get("installed") else "not_installed",
                "installed_at": entry.get("installed_at", ""),
                "venv_path": str(self._get_venv_path(plugin_id)),
            })
        return result

    def is_installed(self, plugin_id: str) -> bool:
        """Check if a plugin is installed and its venv exists."""
        entry = self._registry.get(plugin_id, {})
        if not entry.get("installed"):
            return False
        venv = self._get_venv_path(plugin_id)
        return venv.exists()

    def get_plugin_python(self, plugin_id: str) -> Path:
        """Return the Python executable path inside the plugin's venv."""
        venv = self._get_venv_path(plugin_id)
        if sys.platform == "win32":
            return venv / "Scripts" / "python.exe"
        return venv / "bin" / "python3"

    def _get_venv_path(self, plugin_id: str) -> Path:
        """Return the venv directory path for a plugin."""
        return self._plugins_dir / plugin_id / "venv"

    # ------------------------------------------------------------
    # Plugin install / uninstall
    # ------------------------------------------------------------

    def install_plugin(
        self,
        plugin_id: str,
        progress_cb: Callable[[float, str], None] | None = None,
        mirror: str = "official",
        no_cache: bool = False,
    ) -> None:
        """Install a plugin by creating a uv venv and installing dependencies.

        Args:
            plugin_id: Plugin to install.
            progress_cb: Optional progress callback.
            mirror: PyTorch mirror key (from PYTORCH_MIRRORS). Used when the
                plugin has a ``pytorch_index`` field.
            no_cache: If True, pass ``--no-cache`` to uv pip install.

        Raises:
            ValueError: If plugin_id is not in the registry.
            RuntimeError: If uv or installation fails.
        """
        if plugin_id not in PLUGIN_REGISTRY:
            raise ValueError(f"Unknown plugin: {plugin_id}")

        meta = PLUGIN_REGISTRY[plugin_id]
        venv_path = self._get_venv_path(plugin_id)
        plugin_python = self.get_plugin_python(plugin_id)
        uv = _get_uv_path()

        # Clean up existing venv if present
        if venv_path.exists():
            shutil.rmtree(venv_path, ignore_errors=True)

        if progress_cb:
            progress_cb(5.0, "Creating isolated environment...")

        # Create venv with uv
        env = _clean_subprocess_env()
        self._run_uv(
            [str(uv), "venv", str(venv_path), "--python", "3.11"],
            env=env,
        )

        if progress_cb:
            progress_cb(20.0, "Installing dependencies...")

        # Resolve dependencies -- all plugins now use 'dependencies' key
        deps: list[str] = list(meta.get("dependencies", []))

        if deps:
            if progress_cb:
                progress_cb(50.0, f"Installing {len(deps)} packages...")

            cmd = [str(uv), "pip", "install"] + deps + ["--python", str(plugin_python)]

            # If the plugin defines a pytorch_index, use --extra-index-url with the
            # resolved mirror URL so CUDA wheels are pulled correctly.
            # NOTE: --find-links doesn't work here because uv still prefers PyPI
            # (CPU) packages. --extra-index-url adds the mirror as a proper index.
            pytorch_index = meta.get("pytorch_index")
            if pytorch_index:
                mirror_info = PYTORCH_MIRRORS.get(mirror)
                extra_index_url = mirror_info["url"] if mirror_info else pytorch_index
                cmd.extend(["--extra-index-url", extra_index_url])

            if no_cache:
                cmd.append("--no-cache")

            self._run_uv(cmd, env=env)

        if progress_cb:
            progress_cb(90.0, "Finalizing...")

        # Update registry
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._registry[plugin_id] = {
            "installed": True,
            "version": meta.get("version", "1.0.0"),
            "installed_at": now,
            "engine": meta["engine"],
        }
        self._save_registry()

        if progress_cb:
            progress_cb(100.0, "Installation complete")

        logger.info("Plugin {} installed successfully", plugin_id)

    def uninstall_plugin(self, plugin_id: str) -> None:
        """Uninstall a plugin by removing its venv and registry entry.

        Raises:
            ValueError: If plugin_id is not in the registry.
        """
        if plugin_id not in PLUGIN_REGISTRY:
            raise ValueError(f"Unknown plugin: {plugin_id}")

        venv_path = self._get_venv_path(plugin_id)
        if venv_path.exists():
            shutil.rmtree(venv_path, ignore_errors=True)

        self._registry.pop(plugin_id, None)
        self._save_registry()
        logger.info("Plugin {} uninstalled", plugin_id)

    # ------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------

    def list_models(self) -> list[dict[str, Any]]:
        """Return all registered models with their download status."""
        result: list[dict[str, Any]] = []
        for plugin_id, meta in PLUGIN_REGISTRY.items():
            for model_id, model_meta in meta["models"].items():
                local_path = self._get_model_path(model_id)
                result.append({
                    "model_id": model_id,
                    "display_name": model_meta["display_name"],
                    "plugin_id": plugin_id,
                    "engine": meta["engine"],
                    "size_bytes": model_meta["size_bytes"],
                    "local_path": str(local_path),
                    "status": "downloaded" if local_path.exists() else "not_downloaded",
                })
        return result

    def is_model_downloaded(self, model_id: str) -> bool:
        """Check if a model is downloaded and structurally valid."""
        return self.validate_model(model_id)["valid"]

    def get_model_path(self, model_id: str) -> Path:
        """Return the local path for a model. Does not trigger download."""
        return self._get_model_path(model_id)

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate that a downloaded model directory is structurally correct.

        Checks:
        1. Directory name contains '--' separator (safe_name format).
        2. Directory exists on disk.
        3. Required files are present based on engine type.

        Returns:
            {"valid": bool, "errors": list[str]}
        """
        errors: list[str] = []

        # -- directory name format --
        safe_name = model_id.replace("/", "--")
        if "--" not in safe_name:
            errors.append(f"Model id '{model_id}' does not contain a valid separator")

        model_path = self._model_dir / safe_name

        if not model_path.exists():
            errors.append(f"Model directory does not exist: {model_path}")
            return {"valid": False, "errors": errors}

        if not model_path.is_dir():
            errors.append(f"Model path is not a directory: {model_path}")
            return {"valid": False, "errors": errors}

        # -- determine engine type from PLUGIN_REGISTRY --
        engine: str | None = None
        for _plugin_id, plugin_info in PLUGIN_REGISTRY.items():
            if model_id in plugin_info.get("models", {}):
                engine = plugin_info.get("engine")
                break

        # -- required files per engine --
        if engine == "faster-whisper":
            required = ["model.bin", "config.json"]
        elif engine == "qwen3-asr":
            required = ["model.safetensors", "config.json"]
        else:
            # Unknown engine -- only check that the directory is non-empty
            if not any(model_path.iterdir()):
                errors.append(f"Model directory is empty: {model_path}")
            return {"valid": len(errors) == 0, "errors": errors}

        for fname in required:
            if not (model_path / fname).exists():
                errors.append(f"Missing required file: {fname}")

        return {"valid": len(errors) == 0, "errors": errors}

    def _get_model_path(self, model_id: str) -> Path:
        """Compute the local model storage path."""
        safe_name = model_id.replace("/", "--")
        return self._model_dir / safe_name

    def ensure_model(
        self,
        model_id: str,
        progress_cb: Callable[[float, str], None] | None = None,
        mirror: str | None = None,
    ) -> Path:
        """Ensure a model is downloaded. Returns the local path.

        Uses huggingface_hub for download with automatic source detection
        (HuggingFace / hf-mirror / ModelScope).

        Args:
            model_id: HuggingFace model ID.
            progress_cb: Optional progress callback ``(percent, message)``.
            mirror: Force a specific download mirror (e.g. "huggingface",
                "hf-mirror", "modelscope"). ``None`` auto-detects.

        Raises:
            ValueError: If model_id is not in any plugin registry.
            RuntimeError: If download fails.
        """
        local_path = self._get_model_path(model_id)
        if local_path.exists():
            return local_path

        # Find model metadata
        model_meta = self._find_model_meta(model_id)
        if model_meta is None:
            raise ValueError(f"Unknown model: {model_id}")

        if progress_cb:
            progress_cb(0.0, f"Downloading {model_meta['display_name']}...")

        source = mirror if mirror else _detect_download_source()
        logger.info("Downloading model {} from {}", model_id, source)

        local_path.mkdir(parents=True, exist_ok=True)

        try:
            if source == "modelscope":
                self._download_from_modelscope(model_id, local_path, progress_cb)
            else:
                endpoint = (
                    "https://hf-mirror.com" if source == "hf-mirror"
                    else "https://huggingface.co"
                )
                self._download_from_hf(model_id, local_path, endpoint, progress_cb)
        except Exception as exc:
            # Clean up partial download
            shutil.rmtree(local_path, ignore_errors=True)
            raise RuntimeError(f"Model download failed: {exc}") from exc

        if progress_cb:
            progress_cb(100.0, "Download complete")

        logger.info("Model {} downloaded to {}", model_id, local_path)
        return local_path

    def delete_model(self, model_id: str) -> None:
        """Delete a downloaded model."""
        local_path = self._get_model_path(model_id)
        if local_path.exists():
            shutil.rmtree(local_path, ignore_errors=True)
            logger.info("Model {} deleted", model_id)

    def _find_model_meta(self, model_id: str) -> dict[str, Any] | None:
        """Find model metadata across all plugins."""
        for meta in PLUGIN_REGISTRY.values():
            if model_id in meta["models"]:
                return meta["models"][model_id]
        return None

    def _download_from_hf(
        self,
        model_id: str,
        local_path: Path,
        endpoint: str,
        progress_cb: Callable[[float, str], None] | None,
    ) -> None:
        """Download a model from HuggingFace Hub."""
        from huggingface_hub import snapshot_download

        def _progress_callback(progress: float) -> None:
            if progress_cb:
                progress_cb(progress * 100.0, f"Downloading {model_id}...")

        snapshot_download(
            repo_id=model_id,
            local_dir=str(local_path),
            endpoint=endpoint,
        )

    def _download_from_modelscope(
        self,
        model_id: str,
        local_path: Path,
        progress_cb: Callable[[float, str], None] | None,
    ) -> None:
        """Download a model from ModelScope."""
        from modelscope import snapshot_download as ms_download

        # Translate HuggingFace model ID to ModelScope equivalent
        ms_model_id = MODELSCOPE_ID_MAP.get(model_id, model_id)
        logger.info("ModelScope: using model ID {} (mapped from {})", ms_model_id, model_id)
        ms_download(ms_model_id, local_dir=str(local_path))

    # ------------------------------------------------------------
    # uv command execution
    # ------------------------------------------------------------

    @staticmethod
    def _run_uv(
        args: list[str],
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        """Run a uv command with clean environment.

        Raises:
            RuntimeError: If the command fails.
        """
        if env is None:
            env = _clean_subprocess_env()

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                **_subprocess_kwargs(),
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"uv command failed (exit {result.returncode}): {result.stderr}"
                )
            return result
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"uv command timed out after {timeout}s") from exc

    # ------------------------------------------------------------
    # Subprocess IPC (run_in_plugin)
    # ------------------------------------------------------------

    def run_in_plugin(
        self,
        plugin_id: str,
        script_path: Path,
        args: list[str] | None = None,
        task_id: str | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> SubprocessTask:
        """Run a Python script inside a plugin's isolated venv.

        Communication:
        - stdout: line-delimited JSON events (progress, result pointer, error)
        - stderr: merged to log file
        - stdin: orphan process defense (EOF detection -> os._exit(1))

        Results are written to a file (not stdout) to avoid pipe overflow.

        Raises:
            ValueError: If plugin is not installed.
            RuntimeError: If subprocess fails to start.
        """
        if not self.is_installed(plugin_id):
            raise ValueError(f"Plugin {plugin_id} is not installed")

        plugin_python = self.get_plugin_python(plugin_id)
        if not plugin_python.exists():
            raise ValueError(f"Plugin Python not found: {plugin_python}")

        tid = task_id or str(uuid.uuid4())[:8]
        result_path = self._tasks_dir / f"{tid}_result.json"
        log_path = self._tasks_dir / f"{tid}.log"

        env = _clean_subprocess_env()
        cmd = [str(plugin_python), str(script_path)] + (args or [])

        # Append result path so the script knows where to write output
        cmd.extend(["--result-path", str(result_path)])

        logger.info("Starting plugin subprocess: {}", " ".join(cmd))

        # Prepare stderr log file
        log_file = open(log_path, "w", encoding="utf-8")

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log_file,
                env=env,
                **_subprocess_kwargs(),
            )
        except Exception as exc:
            log_file.close()
            raise RuntimeError(f"Failed to start subprocess: {exc}") from exc

        task = SubprocessTask(
            task_id=tid,
            process=proc,
            state=SubprocessState.RUNNING,
            result_path=str(result_path),
        )

        with self._lock:
            self._subprocess_tasks[tid] = task

        # Start stdout reader thread
        reader = threading.Thread(
            target=self._read_subprocess_output,
            args=(task, progress_cb),
            daemon=True,
        )
        reader.start()

        # Start cancel watcher thread
        if cancel_event:
            watcher = threading.Thread(
                target=self._watch_cancellation,
                args=(task, cancel_event),
                daemon=True,
            )
            watcher.start()

        return task

    def _read_subprocess_output(
        self,
        task: SubprocessTask,
        progress_cb: Callable[[float, str], None] | None,
    ) -> None:
        """Read line-delimited JSON events from subprocess stdout."""
        assert task.process is not None
        assert task.process.stdout is not None

        try:
            for line in task.process.stdout:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON stdout from subprocess: {}", line)
                    continue

                event_type = event.get("type", "")

                if event_type == "progress" and progress_cb:
                    progress_cb(
                        event.get("percent", 0.0),
                        event.get("message", ""),
                    )
                elif event_type == "result":
                    task.result_path = event.get("path", task.result_path)
                    logger.info("Subprocess result saved to {}", task.result_path)
                elif event_type == "error":
                    task.error = event.get("message", "Unknown error")
                    logger.error("Subprocess error: {}", task.error)
                elif event_type == "log":
                    msg = event.get("message", "")
                    task.log_lines.append(msg)

        except Exception as exc:
            logger.error("Error reading subprocess output: {}", exc)

        # Wait for process to finish
        task.process.wait()
        task.returncode = task.process.returncode

        if task.state == SubprocessState.CANCELLED:
            return

        if task.returncode == 0:
            task.state = SubprocessState.COMPLETED
        else:
            task.state = SubprocessState.FAILED
            task.error = task.error or _classify_exit_code(task.returncode)

    def _watch_cancellation(
        self,
        task: SubprocessTask,
        cancel_event: threading.Event,
    ) -> None:
        """Watch for cancellation signal and terminate the subprocess."""
        cancel_event.wait()

        if task.state != SubprocessState.RUNNING:
            return

        task.state = SubprocessState.CANCELLED
        proc = task.process
        if proc is None:
            return

        logger.info("Cancelling subprocess {}", task.task_id)

        # Close stdin to signal the child's watchdog
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass

        # Give the process a moment to exit gracefully
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            # Force kill
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        timeout=5,
                        **_subprocess_kwargs(),
                    )
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()

    def get_subprocess_state(self, task_id: str) -> dict[str, Any]:
        """Return the current state of a subprocess task."""
        with self._lock:
            task = self._subprocess_tasks.get(task_id)
        if task is None:
            return {"state": "not_found"}
        return {
            "task_id": task.task_id,
            "state": task.state.value,
            "returncode": task.returncode,
            "error": task.error,
            "result_path": task.result_path,
        }

    def get_asr_log(self, task_id: str) -> str:
        """Return the log content for an ASR task."""
        log_path = self._tasks_dir / f"{task_id}.log"
        if not log_path.exists():
            return ""
        return log_path.read_text(encoding="utf-8", errors="replace")

    def list_asr_logs(self) -> list[dict[str, str]]:
        """Return ASR log file list sorted by modification time (newest first)."""
        logs: list[dict[str, str]] = []
        for log_file in self._tasks_dir.glob("*.log"):
            stat = log_file.stat()
            logs.append({
                "task_id": log_file.stem,
                "path": str(log_file),
                "size": str(stat.st_size),
                "modified": str(stat.st_mtime),
            })
        logs.sort(key=lambda x: x["modified"], reverse=True)
        return logs


# ================================================================
# Module-level helpers
# ================================================================


def _subprocess_kwargs() -> dict[str, Any]:
    """Platform-specific subprocess arguments."""
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        # NOTE: Use CREATE_NO_WINDOW instead of STARTUPINFO/SW_HIDE.
        # STARTUPINFO/SW_HIDE prevented CTranslate2 from loading models
        # in the subprocess, but CREATE_NO_WINDOW works correctly.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _classify_exit_code(returncode: int) -> str:
    """Classify an abnormal exit code into a user-friendly error message.

    Handles:
    - SIGSEGV (11 on Unix, 139 with bash, 0xC0000005 on Windows)
    - SIGABRT (6 on Unix, 134 with bash, 0xC0000409 on Windows)
    - CUDA/GPU OOM (often manifests as SIGSEGV)
    """
    if returncode < 0:
        sig = -returncode
        if sig == signal.SIGSEGV:
            return (
                "Process crashed with segmentation fault (SIGSEGV). "
                "This may indicate GPU memory overflow or incompatible model. "
                "Try switching to CPU mode or a smaller model."
            )
        if sig == signal.SIGABRT:
            return (
                "Process aborted (SIGABRT). "
                "This may indicate a CUDA/GPU error. "
                "Try switching to CPU mode."
            )
        return f"Process killed by signal {sig}"

    # Windows exception codes
    if returncode in (0xC0000005, -1073741819):
        return (
            "Process crashed with access violation (0xC0000005). "
            "This may indicate GPU memory overflow. "
            "Try switching to CPU mode or a smaller model."
        )
    if returncode in (0xC0000409, -1073740791):
        return (
            "Process aborted with stack buffer overrun (0xC0000409). "
            "Try switching to CPU mode."
        )

    return f"Process exited with code {returncode}"
