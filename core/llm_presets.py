"""LLM prompt preset management.

Presets are parameter snapshots for LLM features (P0/P1/P2, not P3).
Each preset stores the complete configuration (simple-mode params + optional
advanced-mode system_override), so users can quickly switch between
different scenarios (e.g. "academic report" vs "daily vlog").

A preset does NOT take effect directly -- it must be "applied", which writes
its contents into ``settings.json["llm_prompts"][func_key]`` (the "current"
override).  ``core.llm_prompts.get_effective_prompt`` reads that override
unchanged.

Storage (weakly typed, D-33): ``settings.json["llm_prompt_presets"]`` maps
each func_key to a list of preset dicts::

    {
        "llm_prompt_presets": {
            "smart_delete": [
                {
                    "id": "preset-uuid",
                    "name": "学术报告",
                    "params": {"custom_fillers": ["那么", "那个"]},
                    "system_override": "",
                    "model": "",               # D-73 reserved (Phase 1 stores, no UI)
                    "created_at": "2025-01-01T00:00:00"
                }
            ]
        }
    }

Built-in preset (D-44): only a single "默认" preset is provided per feature
(empty params + empty system_override), equivalent to current behavior.
Other presets are user-created.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Features that support presets (P0/P1/P2; P3 search excluded per D-41).
PRESET_SUPPORTED_KEYS: tuple[str, ...] = (
    "smart_delete",
    "subtitle_correction_a",
    "subtitle_correction_b",
    "highlight",
)

_DEFAULT_PRESET_NAME = "默认"
# Stable id for the built-in default preset (cannot be deleted by users).
_DEFAULT_PRESET_ID = "default"


def _utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _gen_preset_id() -> str:
    """Generate a unique preset id."""
    return f"preset-{uuid.uuid4().hex[:12]}"


def _make_default_preset() -> dict[str, Any]:
    """Create the built-in default preset (stable id, empty contents)."""
    return {
        "id": _DEFAULT_PRESET_ID,
        "name": _DEFAULT_PRESET_NAME,
        "params": {},
        "system_override": "",
        "model": "",  # D-73 reserved
        "created_at": _utc_now_iso(),
    }


def _is_default_preset(preset: dict[str, Any]) -> bool:
    """True if *preset* is the built-in default (stable id)."""
    return preset.get("id") == _DEFAULT_PRESET_ID


def _ensure_default_presets(
    presets_by_key: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Ensure every supported key's list contains exactly one default preset.

    The built-in default (stable id ``default``) is auto-injected if missing
    (e.g. settings.json pre-dates this feature or was hand-edited).  User
    presets are left untouched.
    """
    for key in PRESET_SUPPORTED_KEYS:
        lst = presets_by_key.setdefault(key, [])
        # Remove any stale duplicate defaults, then prepend one if none remain.
        lst = [p for p in lst if not _is_default_preset(p)]
        lst.insert(0, _make_default_preset())
        presets_by_key[key] = lst
    return presets_by_key


# ------------------------------------------------------------------
# CRUD operations
# ------------------------------------------------------------------


def get_presets(func_key: str) -> list[dict[str, Any]]:
    """Read the preset list for the given feature (always includes default).

    Args:
        func_key: One of :data:`PRESET_SUPPORTED_KEYS`.

    Returns:
        List of preset dicts.  An empty list is returned for unknown keys
        (caller decides how to surface the error).
    """
    if func_key not in PRESET_SUPPORTED_KEYS:
        logger.warning("get_presets: unsupported func_key=%s", func_key)
        return []

    from core.config import load_settings

    presets_by_key = load_settings().get("llm_prompt_presets", {})
    _ensure_default_presets(presets_by_key)
    return list(presets_by_key.get(func_key, []))


def save_preset(
    func_key: str,
    name: str,
    params: dict[str, Any],
    system_override: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Save a new preset for the given feature.

    Generates a UUID + created_at timestamp and appends to the feature's list.

    Args:
        func_key: Feature key.
        name: Human-readable preset name.
        params: Simple-mode parameter snapshot.
        system_override: Advanced-mode full prompt (empty = simple mode).
        model: Reserved model field (D-73, Phase 1 stores without UI).

    Returns:
        The created preset dict.
    """
    if func_key not in PRESET_SUPPORTED_KEYS:
        raise ValueError(f"Unknown prompt key: {func_key}")

    from core.config import load_settings, save_settings

    settings = load_settings()
    presets_by_key = settings.get("llm_prompt_presets", {})
    _ensure_default_presets(presets_by_key)

    preset: dict[str, Any] = {
        "id": _gen_preset_id(),
        "name": name.strip() or _DEFAULT_PRESET_NAME,
        "params": params or {},
        "system_override": system_override or "",
        "model": model or "",
        "created_at": _utc_now_iso(),
    }

    presets_by_key.setdefault(func_key, [])
    presets_by_key[func_key].append(preset)

    settings["llm_prompt_presets"] = presets_by_key
    save_settings(settings)
    logger.info("Saved preset %s for %s", preset["id"], func_key)
    return preset


def apply_preset(func_key: str, preset_id: str) -> dict[str, Any]:
    """Apply a preset -- writes its contents into the current override.

    This is semantically equivalent to :func:`update_llm_prompt` but sources
    values from the preset rather than caller-supplied args.

    Args:
        func_key: Feature key.
        preset_id: Target preset id.

    Returns:
        The applied preset dict.

    Raises:
        KeyError: If the preset is not found.
        ValueError: If func_key is unsupported.
    """
    if func_key not in PRESET_SUPPORTED_KEYS:
        raise ValueError(f"Unknown prompt key: {func_key}")

    presets = get_presets(func_key)
    target: dict[str, Any] | None = None
    for p in presets:
        if p["id"] == preset_id:
            target = p
            break
    if target is None:
        raise KeyError(
            f"Preset {preset_id} not found in {func_key}"
        )

    # Write into llm_prompts override (mirrors update_llm_prompt semantics).
    from core.config import load_settings, save_settings

    settings = load_settings()
    prompts = settings.get("llm_prompts", {})

    override: dict[str, Any] = {}
    system_override = target.get("system_override", "")
    override["system_override"] = (
        system_override if system_override and system_override.strip() else None
    )
    override["params"] = dict(target.get("params", {}))

    prompts[func_key] = override
    settings["llm_prompts"] = prompts
    save_settings(settings)
    logger.info("Applied preset %s to %s", preset_id, func_key)
    return target


def delete_preset(func_key: str, preset_id: str) -> None:
    """Delete a preset by id.

    The built-in default preset (empty params + empty override) is protected
    and cannot be deleted.

    Args:
        func_key: Feature key.
        preset_id: Target preset id.

    Raises:
        KeyError: If the preset is not found.
        ValueError: If attempting to delete the built-in default.
    """
    if func_key not in PRESET_SUPPORTED_KEYS:
        raise ValueError(f"Unknown prompt key: {func_key}")

    from core.config import load_settings, save_settings

    settings = load_settings()
    presets_by_key = settings.get("llm_prompt_presets", {})
    _ensure_default_presets(presets_by_key)

    presets = presets_by_key.get(func_key, [])
    target: dict[str, Any] | None = None
    for p in presets:
        if p["id"] == preset_id:
            target = p
            break
    if target is None:
        raise KeyError(
            f"Preset {preset_id} not found in {func_key}"
        )

    # Protect the built-in default (stable id) -- cannot be deleted.
    if _is_default_preset(target):
        raise ValueError("Cannot delete the built-in default preset")

    presets_by_key[func_key] = [p for p in presets if p["id"] != preset_id]
    # Default preset is always retained (never removed above), so no re-add needed.

    settings["llm_prompt_presets"] = presets_by_key
    save_settings(settings)
    logger.info("Deleted preset %s from %s", preset_id, func_key)
