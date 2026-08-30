"""v3.0.0 M2: persistence safety (fsync + backup rotation + recovery chain)."""

from __future__ import annotations

import json

import pytest

from core.persistence import atomic_save_with_backup


@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    from core.project_service import ProjectService

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    return service


class TestAtomicSaveWithBackup:
    def test_save_creates_bak_rotation(self, tmp_path):
        path = tmp_path / "project.json"
        atomic_save_with_backup(path, '{"v": 1}')
        atomic_save_with_backup(path, '{"v": 2}')
        atomic_save_with_backup(path, '{"v": 3}')

        assert json.loads(path.read_text(encoding="utf-8")) == {"v": 3}
        assert json.loads(path.with_suffix(".json.bak.1").read_text(encoding="utf-8")) == {"v": 2}
        assert json.loads(path.with_suffix(".json.bak.2").read_text(encoding="utf-8")) == {"v": 1}

    def test_rotations_beyond_keep_are_dropped(self, tmp_path):
        path = tmp_path / "p.json"
        for i in range(6):
            atomic_save_with_backup(path, f'{{"v": {i}}}', keep=2)

        assert json.loads(path.read_text(encoding="utf-8")) == {"v": 5}
        assert json.loads(path.with_suffix(".json.bak.1").read_text(encoding="utf-8")) == {"v": 4}
        assert json.loads(path.with_suffix(".json.bak.2").read_text(encoding="utf-8")) == {"v": 3}
        assert not path.with_suffix(".json.bak.3").exists()

    def test_tmp_never_replaces_valid_file(self, tmp_path):
        """Interrupted tmp write leaves the previous file intact."""
        path = tmp_path / "p.json"
        atomic_save_with_backup(path, '{"v": 1}')
        before = path.read_text(encoding="utf-8")

        tmp = path.with_suffix(".json.tmp")
        tmp.write_text('{"half":', encoding="utf-8")  # simulated torn write
        # main file untouched by the stray tmp
        assert path.read_text(encoding="utf-8") == before


class TestOpenRecoveryChain:
    def _save_and_corrupt(self, svc):
        path = svc._current_path
        svc.save_project()
        # enough content for two rotations
        svc.save_project()
        path.write_text('{"corrupt":', encoding="utf-8")
        return path

    def test_recovers_from_bak1(self, svc):
        path = self._save_and_corrupt(svc)
        res = svc.open_project(str(path))
        assert res["success"] or res["error"] == "MEDIA_NOT_FOUND"
        assert res.get("recovered_from", "").endswith(".bak.1")

    def test_all_corrupt_reports_tried(self, svc):
        path = self._save_and_corrupt(svc)
        path.write_text('{"corrupt":', encoding="utf-8")
        path.with_suffix(".json.bak.1").write_text("nope", encoding="utf-8")
        path.with_suffix(".json.bak.2").write_text("[[[", encoding="utf-8")

        res = svc.open_project(str(path))
        assert not res["success"]
        assert "无可用备份" in res["error"]
        assert len(res["data"]["tried"]) == 3

    def test_recovery_survives_schema_validation_failure(self, svc):
        """Main file parses as JSON but fails model validation -> bak wins."""
        path = svc._current_path
        svc.save_project()
        svc.save_project()
        path.write_text('{"schema_version": 2, "timelines": "not-a-list"}', encoding="utf-8")

        res = svc.open_project(str(path))
        assert res["success"] or res["error"] == "MEDIA_NOT_FOUND"
        assert res.get("recovered_from", "").endswith(".bak.1")


class TestNormalSavePathTimingGuard:
    def test_save_project_still_works(self, svc):
        res = svc.save_project()
        assert res["success"]
        assert svc._current_path.exists()


class TestRecentProjectsCorruptFallback:
    def test_corrupt_project_still_listed_with_bak_meta(self, svc, monkeypatch):
        """macOS smoke fix: corrupted project.json stays in the recent list."""
        monkeypatch.setattr(
            "core.project_service.get_projects_dir",
            lambda: svc._current_path.parent.parent,
        )
        svc.save_project()
        svc.save_project()
        svc._current_path.write_text('{"corrupt":', encoding="utf-8")

        res = svc.get_recent_projects()
        assert res["success"]
        entries = [e for e in res["data"] if e["path"] == str(svc._current_path)]
        assert len(entries) == 1, "corrupted project must stay visible"
        assert entries[0]["corrupted"] is True
        assert entries[0]["name"] == "t"
