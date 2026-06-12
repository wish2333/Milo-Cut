"""Milo-Cut core package."""

from importlib.metadata import version as _metadata_version, PackageNotFoundError


def _read_version() -> str:
    """Get app version with packaging fallback.

    Tries importlib.metadata first (dev/pip env), then falls back
    to reading pyproject.toml directly (PyInstaller bundle).
    """
    # Method 1: importlib.metadata (dev env / pip install)
    try:
        return _metadata_version("milo-cut")
    except PackageNotFoundError:
        pass
    # Method 2: read pyproject.toml (PyInstaller packaging fallback)
    try:
        import tomllib
        from pathlib import Path

        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with open(toml_path, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "Could not read version from pyproject.toml", exc_info=True
        )
    return "0.0.0"


__version__: str = _read_version()
