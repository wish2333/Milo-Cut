"""Tests for core.llm_presets module (v2.1.0 Phase 1).

Covers preset CRUD: get (with built-in default), save (UUID + created_at),
apply (writes to llm_prompts override), delete (protected default).

Settings are isolated per-test via monkeypatch on core.paths.get_settings_path.
"""

from __future__ import annotations

import pytest

from core.llm_presets import (
    PRESET_SUPPORTED_KEYS,
    apply_preset,
    delete_preset,
    get_presets,
    save_preset,
)


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Redirect settings.json to an isolated temp file per test.

    With config.load_settings now deep-copying _DEFAULT_SETTINGS, patching
    get_settings_path is sufficient; we also patch load_settings/save_settings
    for robustness against any other path-binding quirk.
    """
    import json as _json

    settings_path = tmp_path / "settings.json"

    def _load() -> dict:
        import copy as _copy

        from core.config import _DEFAULT_SETTINGS
        if not settings_path.exists():
            return _copy.deepcopy(_DEFAULT_SETTINGS)
        try:
            data = _json.loads(settings_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return _copy.deepcopy(_DEFAULT_SETTINGS)
        merged = _copy.deepcopy(_DEFAULT_SETTINGS)
        merged.update(data)
        return merged

    def _save(settings: dict) -> None:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = settings_path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        import os as _os
        _os.replace(tmp, settings_path)

    monkeypatch.setattr("core.config.load_settings", _load)
    monkeypatch.setattr("core.config.save_settings", _save)
    return settings_path


# ------------------------------------------------------------------
# get_presets
# ------------------------------------------------------------------


class TestGetPresets:
    def test_unknown_key_returns_empty(self, isolated_settings):
        assert get_presets("search") == []
        assert get_presets("nonexistent") == []

    def test_returns_built_in_default(self, isolated_settings):
        """First read of a supported key auto-creates the default preset."""
        presets = get_presets("smart_delete")
        assert len(presets) == 1
        default = presets[0]
        assert default["id"] == "default"  # stable built-in id
        assert default["name"] == "默认"
        assert default["params"] == {}
        assert default["system_override"] == ""
        assert default["model"] == ""  # D-73 reserved
        assert "created_at" in default

    def test_all_supported_keys_have_default(self, isolated_settings):
        for key in PRESET_SUPPORTED_KEYS:
            presets = get_presets(key)
            assert len(presets) >= 1
            assert presets[0]["name"] == "默认"


# ------------------------------------------------------------------
# save_preset
# ------------------------------------------------------------------


class TestSavePreset:
    def test_save_appends_to_list(self, isolated_settings):
        preset = save_preset(
            "smart_delete",
            "学术报告",
            params={"custom_fillers": ["那么", "那个"]},
        )
        assert preset["name"] == "学术报告"
        assert preset["params"] == {"custom_fillers": ["那么", "那个"]}
        assert preset["id"].startswith("preset-")
        assert preset["created_at"]

        presets = get_presets("smart_delete")
        # default + 1 saved
        assert len(presets) == 2
        assert presets[-1]["id"] == preset["id"]

    def test_save_generates_unique_ids(self, isolated_settings):
        p1 = save_preset("highlight", "A", params={"focus_keywords": ["x"]})
        p2 = save_preset("highlight", "B", params={"focus_keywords": ["y"]})
        assert p1["id"] != p2["id"]

    def test_save_strips_name(self, isolated_settings):
        preset = save_preset("smart_delete", "  带空格  ", params={})
        assert preset["name"] == "带空格"

    def test_save_empty_name_uses_default_name(self, isolated_settings):
        preset = save_preset("smart_delete", "", params={})
        assert preset["name"] == "默认"

    def test_save_with_system_override(self, isolated_settings):
        preset = save_preset(
            "subtitle_correction_a",
            "高级",
            params={},
            system_override="custom system prompt",
        )
        assert preset["system_override"] == "custom system prompt"

    def test_save_with_reserved_model(self, isolated_settings):
        """D-73: model field is stored even though Phase 1 has no UI."""
        preset = save_preset("smart_delete", "M", params={}, model="gpt-4o")
        assert preset["model"] == "gpt-4o"

    def test_save_unknown_key_raises(self, isolated_settings):
        with pytest.raises(ValueError, match="Unknown prompt key"):
            save_preset("invalid", "x", params={})


# ------------------------------------------------------------------
# apply_preset
# ------------------------------------------------------------------


class TestApplyPreset:
    def test_apply_writes_override(self, isolated_settings):
        preset = save_preset(
            "smart_delete",
            "学术",
            params={"custom_fillers": ["那么"]},
        )
        apply_preset("smart_delete", preset["id"])

        from core.config import load_settings

        override = load_settings()["llm_prompts"]["smart_delete"]
        assert override["params"] == {"custom_fillers": ["那么"]}
        # simple-mode preset -> system_override is None
        assert override["system_override"] is None

    def test_apply_with_system_override(self, isolated_settings):
        preset = save_preset(
            "highlight",
            "高级",
            params={},
            system_override="full override text",
        )
        apply_preset("highlight", preset["id"])

        from core.config import load_settings

        override = load_settings()["llm_prompts"]["highlight"]
        assert override["system_override"] == "full override text"
        assert override["params"] == {}

    def test_apply_effective_prompt_reads_override(self, isolated_settings):
        """Applied preset should be readable via get_effective_prompt."""
        from core.llm_prompts import get_effective_prompt

        preset = save_preset(
            "smart_delete",
            "学术",
            params={"custom_fillers": ["那个"]},
        )
        apply_preset("smart_delete", preset["id"])

        effective = get_effective_prompt("smart_delete")
        assert "那个" in effective
        assert "额外需要检测的口头禅" in effective

    def test_apply_empty_override_strips_to_none(self, isolated_settings):
        preset = save_preset("smart_delete", "空白", params={}, system_override="   ")
        apply_preset("smart_delete", preset["id"])

        from core.config import load_settings

        override = load_settings()["llm_prompts"]["smart_delete"]
        assert override["system_override"] is None

    def test_apply_unknown_preset_raises_keyerror(self, isolated_settings):
        with pytest.raises(KeyError, match="not found"):
            apply_preset("smart_delete", "preset-nonexistent")

    def test_apply_unknown_key_raises(self, isolated_settings):
        with pytest.raises(ValueError, match="Unknown prompt key"):
            apply_preset("invalid", "preset-x")


# ------------------------------------------------------------------
# delete_preset
# ------------------------------------------------------------------


class TestDeletePreset:
    def test_delete_user_preset(self, isolated_settings):
        preset = save_preset("smart_delete", "临时", params={"custom_fillers": ["嗯"]})
        presets_before = get_presets("smart_delete")
        assert len(presets_before) == 2
        assert len(presets_before) == 2

        delete_preset("smart_delete", preset["id"])

        presets_after = get_presets("smart_delete")
        ids = [p["id"] for p in presets_after]
        assert preset["id"] not in ids
        # default remains
        assert len(presets_after) == 1
        assert presets_after[0]["name"] == "默认"

    def test_cannot_delete_default_ever(self, isolated_settings):
        """The built-in default (stable id 'default') is always protected."""
        presets = get_presets("smart_delete")
        default_id = presets[0]["id"]
        assert default_id == "default"

        with pytest.raises(ValueError, match="Cannot delete the built-in default"):
            delete_preset("smart_delete", default_id)

        # Even when other presets exist, default is still protected.
        save_preset("smart_delete", "用户A", params={"custom_fillers": ["x"]})
        with pytest.raises(ValueError, match="Cannot delete the built-in default"):
            delete_preset("smart_delete", default_id)

    def test_delete_unknown_preset_raises_keyerror(self, isolated_settings):
        with pytest.raises(KeyError, match="not found"):
            delete_preset("smart_delete", "preset-nonexistent")

    def test_delete_unknown_key_raises(self, isolated_settings):
        with pytest.raises(ValueError, match="Unknown prompt key"):
            delete_preset("invalid", "preset-x")


# ------------------------------------------------------------------
# Cross-feature isolation
# ------------------------------------------------------------------


class TestFeatureIsolation:
    def test_presets_isolated_per_feature(self, isolated_settings):
        """Saving a preset for one feature does not affect another."""
        save_preset("smart_delete", "SD", params={"custom_fillers": ["a"]})
        save_preset("highlight", "HL", params={"focus_keywords": ["b"]})

        sd = get_presets("smart_delete")
        hl = get_presets("highlight")

        assert len(sd) == 2  # default + 1
        assert len(hl) == 2  # default + 1
        assert sd[-1]["name"] == "SD"
        assert hl[-1]["name"] == "HL"
