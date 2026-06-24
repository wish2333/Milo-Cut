"""Tests for core.config."""

import json

from core.config import load_settings, save_settings


class TestConfig:
    def test_load_defaults(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("core.paths.get_settings_path", lambda: tmp_dir / "settings.json")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        settings = load_settings()
        assert settings["theme"] == "light"
        assert settings["language"] == "zh-CN"
        assert isinstance(settings["filler_words"], list)
        assert len(settings["filler_words"]) == 10
        assert isinstance(settings["error_trigger_words"], list)
        assert len(settings["error_trigger_words"]) == 9

    def test_save_and_load(self, tmp_dir, monkeypatch):
        monkeypatch.setattr("core.paths.get_settings_path", lambda: tmp_dir / "settings.json")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        settings = load_settings()
        settings["theme"] = "dark"
        save_settings(settings)
        loaded = load_settings()
        assert loaded["theme"] == "dark"

    def test_atomic_write(self, tmp_dir, monkeypatch):
        settings_path = tmp_dir / "settings.json"
        monkeypatch.setattr("core.paths.get_settings_path", lambda: settings_path)
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        save_settings({"theme": "light"})
        assert settings_path.exists()
        assert not (tmp_dir / "settings.json.tmp").exists()

    def test_corrupted_file_returns_defaults(self, tmp_dir, monkeypatch):
        settings_path = tmp_dir / "settings.json"
        settings_path.write_text("not json", encoding="utf-8")
        monkeypatch.setattr("core.paths.get_settings_path", lambda: settings_path)
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        settings = load_settings()
        assert settings["theme"] == "light"

    def test_missing_keys_use_defaults(self, tmp_dir, monkeypatch):
        settings_path = tmp_dir / "settings.json"
        settings_path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        monkeypatch.setattr("core.paths.get_settings_path", lambda: settings_path)
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
        settings = load_settings()
        assert settings["theme"] == "dark"
        assert settings["language"] == "zh-CN"  # default filled in


def test_default_settings_has_new_smart_keys(tmp_dir, monkeypatch):
    """_DEFAULT_SETTINGS should have llm_smart_batch_size and llm_smart_overlap_size, not old keys."""
    from core.config import _DEFAULT_SETTINGS

    assert "llm_smart_batch_size" in _DEFAULT_SETTINGS
    assert "llm_smart_overlap_size" in _DEFAULT_SETTINGS
    assert _DEFAULT_SETTINGS["llm_smart_batch_size"] == 20
    assert _DEFAULT_SETTINGS["llm_smart_overlap_size"] == 4
    assert "llm_smart_window_duration" not in _DEFAULT_SETTINGS
    assert "llm_smart_overlap_duration" not in _DEFAULT_SETTINGS


def test_load_settings_cleans_deprecated_keys(tmp_dir, monkeypatch):
    """load_settings should pop deprecated keys and write back cleaned version (audit #10)."""
    settings_path = tmp_dir / "settings.json"
    monkeypatch.setattr("core.paths.get_settings_path", lambda: settings_path)
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_dir)
    # Write settings with deprecated keys
    settings = {
        "llm_smart_window_duration": 60.0,
        "llm_smart_overlap_duration": 10.0,
        "llm_smart_batch_size": 25,
    }
    save_settings(settings)
    # Load should clean deprecated keys
    loaded = load_settings()
    assert "llm_smart_window_duration" not in loaded
    assert "llm_smart_overlap_duration" not in loaded
    assert loaded["llm_smart_batch_size"] == 25
    # Verify written back
    reloaded_raw = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "llm_smart_window_duration" not in reloaded_raw
