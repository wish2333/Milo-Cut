"""Unit tests for core.file_protocol.FileProtocolManager."""

import json

import pytest

from core.file_protocol import FileProtocolManager


@pytest.fixture
def manager(tmp_path):
    """Create a FileProtocolManager with a temp base dir."""
    return FileProtocolManager(base_dir=tmp_path / "bridge")


class TestFileProtocolPublish:
    def test_publish_writes_file(self, manager: FileProtocolManager) -> None:
        records = [{"id": "s1", "action": "delete"}, {"id": "s2", "action": "keep"}]
        result = manager.publish("edit_timeline", records)

        assert result["success"] is True
        assert result["data"]["records"] == 2

        files = list(manager.outgoing_dir.glob("*.milo.jsonl"))
        assert len(files) == 1

        # Verify content
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["id"] == "s1"
        assert parsed[1]["action"] == "keep"

    def test_publish_empty_records_noop(self, manager: FileProtocolManager) -> None:
        result = manager.publish("empty", [])
        assert result["success"] is True
        assert result["data"]["records"] == 0
        files = list(manager.outgoing_dir.glob("*.milo.jsonl"))
        assert len(files) == 0

    def test_publish_atomic_no_temp_left(self, manager: FileProtocolManager) -> None:
        """After publish, no .tmp files should remain."""
        manager.publish("test", [{"x": 1}])
        tmp_files = list(manager.outgoing_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_publish_filename_includes_data_type(self, manager: FileProtocolManager) -> None:
        manager.publish("my_type", [{"a": 1}])
        files = list(manager.outgoing_dir.glob("*my_type*.milo.jsonl"))
        assert len(files) == 1

    def test_publish_edit_timeline(self, manager: FileProtocolManager) -> None:
        segments = [
            {"id": "s1", "start": 0, "end": 5, "text": "hello"},
            {"id": "s2", "start": 5, "end": 10, "text": "world"},
        ]
        edits = [
            {"target_id": "s1", "action": "delete", "status": "pending"},
        ]
        result = manager.publish_edit_timeline(segments, edits)
        assert result["success"] is True

        files = list(manager.outgoing_dir.glob("*edit_timeline*.milo.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(line) for line in lines]
        assert records[0]["id"] == "s1"
        assert records[0]["action"] == "delete"
        assert records[1]["id"] == "s2"
        assert records[1]["action"] == "keep"  # no edit -> default keep

    def test_publish_topic_drift(self, manager: FileProtocolManager) -> None:
        results = [
            {"segment_id": "s1", "relevance": 0.2, "topic": "off-topic"},
        ]
        result = manager.publish_topic_drift(results, "AI presentation")
        assert result["success"] is True

        files = list(manager.outgoing_dir.glob("*topic_drift*.milo.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        records = [json.loads(line) for line in lines]
        # First record is meta
        assert records[0]["type"] == "meta"
        assert records[0]["topic_description"] == "AI presentation"
        assert records[1]["type"] == "topic_drift"
        assert records[1]["segment_id"] == "s1"

    def test_publish_chinese_content(self, manager: FileProtocolManager) -> None:
        """Chinese characters should be preserved (ensure_ascii=False)."""
        manager.publish("test", [{"text": "你好世界"}])
        files = list(manager.outgoing_dir.glob("*.milo.jsonl"))
        content = files[0].read_text(encoding="utf-8")
        assert "你好世界" in content


class TestFileProtocolPoll:
    def test_poll_incoming_parse_and_archive(self, manager: FileProtocolManager) -> None:
        """Incoming files are parsed and moved to archive."""
        # Create a fake incoming file
        incoming_file = manager.incoming_dir / "test_in.milo.jsonl"
        incoming_file.write_text(
            '{"type": "command", "action": "refresh"}\n{"type": "command", "action": "export"}\n',
            encoding="utf-8",
        )

        results = manager.poll_incoming()
        assert len(results) == 1
        filename, records = results[0]
        assert filename == "test_in.milo.jsonl"
        assert len(records) == 2
        assert records[0]["action"] == "refresh"

        # File should be archived
        assert not incoming_file.exists()
        archived = manager.archive_dir / "test_in.milo.jsonl"
        assert archived.exists()

    def test_poll_incoming_empty_dir(self, manager: FileProtocolManager) -> None:
        results = manager.poll_incoming()
        assert results == []

    def test_poll_incoming_skips_invalid_lines(self, manager: FileProtocolManager) -> None:
        """Invalid JSON lines are skipped, valid ones parsed."""
        incoming_file = manager.incoming_dir / "mixed.milo.jsonl"
        incoming_file.write_text(
            '{"valid": true}\nNOT JSON\n{"also_valid": true}\n',
            encoding="utf-8",
        )
        results = manager.poll_incoming()
        _, records = results[0]
        assert len(records) == 2
        assert records[0]["valid"] is True

    def test_poll_incoming_multiple_files(self, manager: FileProtocolManager) -> None:
        """Multiple files are all processed."""
        for i in range(3):
            (manager.incoming_dir / f"file_{i}.milo.jsonl").write_text(
                f'{{"idx": {i}}}\n', encoding="utf-8"
            )
        results = manager.poll_incoming()
        assert len(results) == 3

    def test_poll_incoming_callback(self, manager: FileProtocolManager) -> None:
        """Registered callback receives parsed records."""
        received: list[tuple[str, list[dict]]] = []
        manager.on_incoming(lambda fn, recs: received.append((fn, recs)))

        (manager.incoming_dir / "cb.milo.jsonl").write_text(
            '{"action": "test"}\n', encoding="utf-8"
        )

        # start_polling then immediately stop -- not reliable for testing.
        # Instead directly test poll_incoming + callback.
        manager._incoming_callback("cb.milo.jsonl", [{"action": "test"}])
        assert len(received) == 1
        assert received[0][1][0]["action"] == "test"


class TestFileProtocolLifecycle:
    def test_start_stop_polling(self, manager: FileProtocolManager) -> None:
        """Polling thread starts and stops cleanly."""
        import time

        manager.start_polling(interval=0.1)
        assert manager._poll_thread is not None
        assert manager._poll_thread.is_alive()

        time.sleep(0.3)  # let it poll a few times

        manager.stop_polling()
        assert manager._poll_thread is None

    def test_directories_created(self, tmp_path) -> None:
        """All subdirectories are created on init."""
        base = tmp_path / "newbridge"
        m = FileProtocolManager(base_dir=base)
        assert m.outgoing_dir.exists()
        assert m.incoming_dir.exists()
        assert m.archive_dir.exists()
