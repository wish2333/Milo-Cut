"""File-based bridge protocol for inter-process communication.

Publishes data as JSONL files (``.milo.jsonl``) to an outgoing directory
for external tools to consume. Reads incoming JSONL files from an incoming
directory and archives them after processing.

Uses atomic writes (``os.replace``) for Windows compatibility and polls
incoming at 2s intervals to minimize I/O overhead.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from core.logging import get_logger
from core.paths import get_bridge_dir

logger = get_logger()

_FILE_SUFFIX = ".milo.jsonl"
_POLL_INTERVAL = 2.0  # seconds


class FileProtocolManager:
    """Manages file-based JSONL communication with external tools."""

    def __init__(self, base_dir: Path | None = None) -> None:
        base = base_dir or get_bridge_dir()
        self._outgoing = base / "outgoing"
        self._incoming = base / "incoming"
        self._archive = base / "archive"
        for d in (self._outgoing, self._incoming, self._archive):
            d.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._poll_thread: threading.Thread | None = None
        self._poll_stop = threading.Event()
        self._incoming_callback: Callable[[str, list[dict]], None] | None = None

    @property
    def outgoing_dir(self) -> Path:
        return self._outgoing

    @property
    def incoming_dir(self) -> Path:
        return self._incoming

    @property
    def archive_dir(self) -> Path:
        return self._archive

    # ------------------------------------------------------------------
    # Publish (outgoing)
    # ------------------------------------------------------------------

    def publish(self, data_type: str, records: list[dict]) -> dict:
        """Write records as JSONL to the outgoing directory.

        Uses atomic write: write to temp file, then ``os.replace`` to target.

        Args:
            data_type: Type label (e.g. "edit_timeline", "analysis_results").
            records: List of dicts, each written as one JSONL line.

        Returns:
            {"success": True, "data": {"path": str, "records": N}}
        """
        if not records:
            return {"success": True, "data": {"path": "", "records": 0}}

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{data_type}{_FILE_SUFFIX}"
        target = self._outgoing / filename

        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"

        with self._lock:
            try:
                # Write to temp file in same directory, then atomic replace
                fd, tmp_path = tempfile.mkstemp(dir=str(self._outgoing), suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(content)
                    # os.replace() overwrites atomically (Windows-safe)
                    os.replace(tmp_path, str(target))
                except Exception:
                    # Clean up temp file on error
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise

                logger.info(f"Published {len(records)} records to {filename}")
                return {
                    "success": True,
                    "data": {"path": str(target), "records": len(records)},
                }
            except Exception as e:
                logger.error(f"Failed to publish {data_type}: {e}")
                return {"success": False, "error": str(e)}

    def publish_edit_timeline(
        self,
        segments: list[dict],
        edits: list[dict],
    ) -> dict:
        """Publish edit timeline data (segments + edit actions)."""
        records: list[dict] = []
        edit_map: dict[str, dict] = {}
        for e in edits:
            tid = e.get("target_id", "")
            if tid:
                edit_map[tid] = e

        for seg in segments:
            sid = seg.get("id", "")
            edit = edit_map.get(sid, {})
            records.append(
                {
                    "type": "segment",
                    "id": sid,
                    "start": seg.get("start", 0),
                    "end": seg.get("end", 0),
                    "text": seg.get("text", ""),
                    "action": edit.get("action", "keep"),
                    "edit_status": edit.get("status", ""),
                }
            )

        return self.publish("edit_timeline", records)

    def publish_topic_drift(
        self,
        results: list[dict],
        topic_description: str = "",
    ) -> dict:
        """Publish topic drift analysis results."""
        records = [
            {
                "type": "topic_drift",
                "segment_id": r.get("segment_id", ""),
                "topic": r.get("topic", ""),
                "relevance": r.get("relevance", 1.0),
                "reason": r.get("reason", ""),
            }
            for r in results
        ]
        if topic_description:
            records.insert(
                0,
                {
                    "type": "meta",
                    "topic_description": topic_description,
                },
            )
        return self.publish("topic_drift", records)

    # ------------------------------------------------------------------
    # Consume (incoming)
    # ------------------------------------------------------------------

    def poll_incoming(self) -> list[tuple[str, list[dict]]]:
        """Scan incoming directory for new JSONL files.

        Parses each file, archives it, and returns (filename, records) pairs.
        """
        results: list[tuple[str, list[dict]]] = []

        with self._lock:
            files = sorted(self._incoming.glob(f"*{_FILE_SUFFIX}"))
            for f in files:
                try:
                    records = self._parse_jsonl(f)
                    results.append((f.name, records))
                    # Archive the processed file
                    archive_path = self._archive / f.name
                    os.replace(str(f), str(archive_path))
                except Exception as e:
                    logger.error(f"Failed to process incoming file {f.name}: {e}")

        return results

    def _parse_jsonl(self, path: Path) -> list[dict]:
        """Parse a JSONL file into a list of dicts."""
        records: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
        return records

    # ------------------------------------------------------------------
    # Polling lifecycle
    # ------------------------------------------------------------------

    def on_incoming(self, callback: Callable[[str, list[dict]], None]) -> None:
        """Register a callback for incoming files.

        Callback receives (filename, records) for each incoming file.
        """
        self._incoming_callback = callback

    def start_polling(self, interval: float = _POLL_INTERVAL) -> None:
        """Start background polling of incoming directory."""
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return

        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="file-protocol-poll"
        )
        self._poll_thread.start()
        logger.info(f"File protocol polling started (interval={interval}s)")

    def stop_polling(self) -> None:
        """Stop background polling."""
        self._poll_stop.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=3)
            self._poll_thread = None
        logger.info("File protocol polling stopped")

    def _poll_loop(self) -> None:
        """Main polling loop (runs in background thread)."""
        while not self._poll_stop.is_set():
            try:
                results = self.poll_incoming()
                if results and self._incoming_callback:
                    for filename, records in results:
                        try:
                            self._incoming_callback(filename, records)
                        except Exception as e:
                            logger.error(f"Incoming callback error for {filename}: {e}")
            except Exception as e:
                logger.error(f"Polling error: {e}")

            self._poll_stop.wait(_POLL_INTERVAL)
