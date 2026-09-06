"""Atomic persistence with backup rotation (v3.0.0 M2 / PRD A4).

Guarantees:
- ``atomic_save_with_backup`` writes via tmp + flush + fsync, rotates
  ``.bak.1/.bak.2`` copies, then ``os.replace`` into place. A power failure
  can at worst leave the previous file intact (tmp never replaces a valid file).
- Backup/fsync failures are logged as warnings and never abort the save.
- ``load_json_with_recovery`` implements the open-side chain: main file ->
  ``.bak.1`` -> ``.bak.2``. The caller receives the parsed payload plus
  ``recovered_from`` metadata so the UI can toast the recovery.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from loguru import logger


def _bak_path(path: Path, index: int) -> Path:
    return path.with_suffix(path.suffix + f".bak.{index}")


def atomic_save_with_backup(path: Path, content: str, keep: int = 2) -> None:
    """Atomically replace ``path`` with ``content``, keeping ``keep`` backups.

    Order: write tmp -> flush + fsync -> rotate backups (copy, not rename, to
    avoid an overwrite window) -> os.replace -> best-effort directory fsync.
    Backup or directory-fsync failures only warn; the save itself proceeds.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    # Rotate: bak.N <- old bak.N-1; bak.1 <- current file. Copy semantics.
    for i in range(keep, 0, -1):
        dst = _bak_path(path, i)
        src = path if i == 1 else _bak_path(path, i - 1)
        if not src.exists():
            continue
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            logger.warning("Backup rotation failed for {} -> {}: {}", src, dst, e)

    os.replace(tmp, path)

    # Best-effort directory fsync (not supported on all platforms/filesystems).
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as e:
        logger.debug("Directory fsync skipped for {}: {}", path.parent, e)


def load_json_with_recovery(
    path: Path,
    keep: int = 2,
    validate: Callable[[dict], object] | None = None,
) -> tuple[object | None, str | None, list[str]]:
    """Load a JSON file with backup recovery chain: main -> bak.1 -> bak.2.

    ``validate`` (optional) receives the parsed dict and may transform it
    (e.g. schema migration + model validation). When it raises, the candidate
    is treated as corrupt and the chain moves on to the next backup.

    Returns ``(payload, recovered_from, tried)``:
    - ``payload`` is the validated object, or ``None`` when every candidate failed.
    - ``recovered_from`` is the backup path used, ``None`` for the main file.
    - ``tried`` lists every candidate path attempted.
    """
    path = Path(path)
    candidates: list[tuple[Path, str | None]] = [(path, None)]
    candidates += [(_bak_path(path, i), str(_bak_path(path, i))) for i in range(1, keep + 1)]

    tried: list[str] = []
    for candidate, recovered_from in candidates:
        tried.append(str(candidate))
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if validate is not None:
                payload = validate(payload)
        except Exception as e:
            logger.warning("Failed to load {}: {}", candidate, e)
            continue
        return (payload, recovered_from, tried)

    return (None, None, tried)
