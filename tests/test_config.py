"""Tests for core.config."""

import json
from pathlib import Path

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
