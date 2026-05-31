"""Lazy proxy generation manager.

Generates proxy video files on-demand (first preview request), not on import.
Integrates with TaskManager for background execution.
"""

from __future__ import annotations

import threading
from typing import Any

from loguru import logger

from core.config import load_settings
from core.models import TaskType
from core.task_manager import TaskManager


class ProxyManager:
    """Manages lazy proxy video generation with TaskManager integration.

    Design principles (from audit report 1.3.0):
    - Lazy generation: proxy created on first preview request, not on import
    - Always queue, never discard: system busy does not cause task evaporation
    - Deduplication: avoids creating duplicate proxy tasks for the same media
    """

    def __init__(self, task_manager: TaskManager) -> None:
        self._task_manager = task_manager
        self._pending_media: set[str] = set()
        self._lock = threading.Lock()

    def request_proxy(
        self,
        media_path: str,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """Request proxy generation for a media file.

        Always queues a task, never discards. Deduplicates requests for
        the same media path that are already pending or running.

        Args:
            media_path: Path to the source video file.
            priority: Task priority hint ("high", "normal", "low").
                      Passed through to payload; TaskManager processes FIFO.

        Returns:
            {"success": True, "data": {"task_id": str}}
            or {"success": True, "data": {"task_id": None}} if already pending.
        """
        settings = load_settings()

        if not settings.get("proxy_auto_generate", True):
            return {
                "success": True,
                "data": {"task_id": None, "message": "Auto proxy generation disabled"},
            }

        # Deduplicate: skip if this media already has a pending/running proxy task
        with self._lock:
            if media_path in self._pending_media:
                return {
                    "success": True,
                    "data": {"task_id": None, "message": "Proxy already pending"},
                }
            self._pending_media.add(media_path)

        resolution = settings.get("proxy_resolution", "720p")

        try:
            result = self._task_manager.create_task(
                TaskType.PROXY_GENERATION,
                payload={
                    "media_path": media_path,
                    "resolution": resolution,
                    "priority": priority,
                },
            )
            if not result["success"]:
                with self._lock:
                    self._pending_media.discard(media_path)
                return result

            task_id = result["data"]["id"]
            start_result = self._task_manager.start_task(task_id)
            if not start_result["success"]:
                with self._lock:
                    self._pending_media.discard(media_path)
                return start_result

            logger.info(
                "Proxy generation queued: {} ({}) priority={}",
                media_path, resolution, priority,
            )
            return {"success": True, "data": {"task_id": task_id}}

        except Exception:
            with self._lock:
                self._pending_media.discard(media_path)
            raise

    def on_proxy_complete(self, media_path: str) -> None:
        """Called when a proxy task completes (success or failure).

        Removes the media path from the pending set so future requests
        can re-generate if needed.
        """
        with self._lock:
            self._pending_media.discard(media_path)

    def has_pending(self, media_path: str) -> bool:
        """Check if a proxy task is already pending for the given media."""
        with self._lock:
            return media_path in self._pending_media
