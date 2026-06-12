"""Unit tests for core.bridge_service."""

import json
import threading
import urllib.request

import pytest

from core.bridge_service import BridgeService


class TestBridgeServiceHealth:
    """Test the health endpoint."""

    def test_health_endpoint(self) -> None:
        service = BridgeService()
        result = service.start(port=0)  # random port
        assert result["success"] is True
        port = result["data"]["port"]

        try:
            url = f"http://127.0.0.1:{port}/api/v1/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read())
                assert data["success"] is True
                assert data["data"]["status"] == "ok"
                assert "version" in data["data"]
        finally:
            service.stop()

    def test_cors_headers(self) -> None:
        service = BridgeService()
        result = service.start(port=0)
        assert result["success"] is True
        port = result["data"]["port"]

        try:
            url = f"http://127.0.0.1:{port}/api/v1/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        finally:
            service.stop()

    def test_404_for_unknown_route(self) -> None:
        service = BridgeService()
        result = service.start(port=0)
        assert result["success"] is True
        port = result["data"]["port"]

        try:
            url = f"http://127.0.0.1:{port}/api/v1/nonexistent"
            req = urllib.request.Request(url)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=5)
            assert exc_info.value.code == 404
        finally:
            service.stop()


class TestBridgeServiceProjects:
    """Test the projects endpoint with callback."""

    def test_projects_endpoint(self) -> None:
        test_projects = [
            {"name": "project1", "path": "/tmp/p1"},
            {"name": "project2", "path": "/tmp/p2"},
        ]
        service = BridgeService(get_projects_fn=lambda: test_projects)
        result = service.start(port=0)
        assert result["success"] is True
        port = result["data"]["port"]

        try:
            url = f"http://127.0.0.1:{port}/api/v1/projects"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read())
                assert data["success"] is True
                assert len(data["data"]) == 2
                assert data["data"][0]["name"] == "project1"
        finally:
            service.stop()

    def test_projects_endpoint_no_callback(self) -> None:
        service = BridgeService()  # no callback
        result = service.start(port=0)
        assert result["success"] is True
        port = result["data"]["port"]

        try:
            url = f"http://127.0.0.1:{port}/api/v1/projects"
            req = urllib.request.Request(url)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=5)
            assert exc_info.value.code == 503
        finally:
            service.stop()


class TestBridgeServiceLifecycle:
    """Test start/stop lifecycle."""

    def test_start_stop(self) -> None:
        service = BridgeService()
        assert not service.is_running
        result = service.start(port=0)
        assert result["success"] is True
        assert service.is_running
        assert service.port > 0

        service.stop()
        assert not service.is_running
        assert service.port == 0

    def test_start_twice_returns_same_port(self) -> None:
        service = BridgeService()
        r1 = service.start(port=0)
        assert r1["success"] is True
        port1 = r1["data"]["port"]

        r2 = service.start(port=0)
        assert r2["success"] is True
        assert r2["data"]["port"] == port1

        service.stop()

    def test_stop_when_not_started(self) -> None:
        service = BridgeService()
        service.stop()  # should not raise
        assert not service.is_running
