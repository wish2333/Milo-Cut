"""HTTP API bridge service for external tool integration (e.g., Milo-Cut Neo).

Provides a localhost-only REST API that external applications can use to
interact with Milo-Cut: query project state, trigger analysis, and
exchange timeline data.

Uses stdlib http.server (same pattern as media_server.py) so no
additional dependencies are required.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from core import __version__
from core.logging import get_logger

logger = get_logger()

_DEFAULT_PORT = 18230
_EXPECTED_CONN_ERRORS = (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)


class _QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that suppresses tracebacks for expected connection errors."""

    def handle_error(self, request, client_address):
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, _EXPECTED_CONN_ERRORS):
            return
        super().handle_error(request, client_address)


# ------------------------------------------------------------------
# JSON response helpers
# ------------------------------------------------------------------


def _json_response(
    handler: BaseHTTPRequestHandler,
    code: int,
    data: Any = None,
    error: str | None = None,
) -> None:
    """Send a JSON response with CORS headers."""
    body: dict[str, Any] = {"success": code < 400}
    if data is not None:
        body["data"] = data
    if error is not None:
        body["error"] = error

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


# ------------------------------------------------------------------
# Request handler
# ------------------------------------------------------------------


class _BridgeHandler(BaseHTTPRequestHandler):
    """HTTP handler for the bridge REST API."""

    # Injected by BridgeService before starting
    get_projects_fn: Callable[[], list[dict]] | None = None
    get_project_fn: Callable[[str], dict | None] | None = None
    start_analysis_fn: Callable[[str, str | None], dict | None] | None = None

    def log_message(self, format, *args):
        """Suppress default stderr logging."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        clean = self.path.split("?", 1)[0]

        if clean == "/api/v1/health":
            return _json_response(self, 200, {"status": "ok", "version": __version__})

        if clean == "/api/v1/projects":
            return self._handle_get_projects()

        # /api/v1/projects/{name}/timeline
        parts = clean.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "v1" and parts[2] == "projects" and parts[3] != "timeline":
            return self._handle_get_timeline(parts[3])

        _json_response(self, 404, error="Not found")

    def do_POST(self):
        clean = self.path.split("?", 1)[0]

        if clean == "/api/v1/analyze":
            return self._handle_start_analysis()

        _json_response(self, 404, error="Not found")

    # --- Route handlers ---

    def _handle_get_projects(self) -> None:
        if not self.get_projects_fn:
            return _json_response(self, 503, error="Service not available")
        try:
            projects = self.get_projects_fn()
            _json_response(self, 200, data=projects)
        except Exception as e:
            logger.error("Bridge API error: {}", e)
            _json_response(self, 500, error=str(e))

    def _handle_get_timeline(self, project_name: str) -> None:
        if not self.get_project_fn:
            return _json_response(self, 503, error="Service not available")
        try:
            project = self.get_project_fn(project_name)
            if project is None:
                return _json_response(self, 404, error=f"Project not found: {project_name}")
            # Extract timeline-relevant data only
            segments = project.get("data", {}).get("transcript", {}).get("segments", [])
            edits = project.get("data", {}).get("edits", [])
            timeline = {
                "project_name": project_name,
                "segments": segments,
                "edits": edits,
            }
            _json_response(self, 200, data=timeline)
        except Exception as e:
            logger.error("Bridge API error: {}", e)
            _json_response(self, 500, error=str(e))

    def _handle_start_analysis(self) -> None:
        if not self.start_analysis_fn:
            return _json_response(self, 503, error="Service not available")

        # Parse request body
        body: dict[str, Any] = {}
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            try:
                raw = self.rfile.read(content_length)
                body = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return _json_response(self, 400, error="Invalid JSON body")

        project_name = body.get("project_name", "")
        analysis_type = body.get("type")
        if not project_name:
            return _json_response(self, 400, error="Missing 'project_name'")

        try:
            result = self.start_analysis_fn(project_name, analysis_type)
            if result is None:
                return _json_response(self, 404, error=f"Project not found: {project_name}")
            _json_response(self, 202, data=result)
        except Exception as e:
            logger.error("Bridge API error: {}", e)
            _json_response(self, 500, error=str(e))


# ------------------------------------------------------------------
# BridgeService
# ------------------------------------------------------------------


class BridgeService:
    """Manages a localhost HTTP API server for external tool integration."""

    def __init__(
        self,
        *,
        get_projects_fn: Callable[[], list[dict]] | None = None,
        get_project_fn: Callable[[str], dict | None] | None = None,
        start_analysis_fn: Callable[[str, str | None], dict | None] | None = None,
    ) -> None:
        self._server: _QuietHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._enabled: bool = False
        self._get_projects_fn = get_projects_fn
        self._get_project_fn = get_project_fn
        self._start_analysis_fn = start_analysis_fn

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return (
            self._server is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    def start(self, port: int = _DEFAULT_PORT) -> dict:
        """Start the HTTP API server.

        Returns {"success": True, "data": {"port": N}} on success.
        """
        if self.is_running:
            return {"success": True, "data": {"port": self._port}}

        # Inject callbacks into handler (staticmethod prevents self-binding)
        handler_attrs = {
            "get_projects_fn": staticmethod(self._get_projects_fn) if self._get_projects_fn else None,
            "get_project_fn": staticmethod(self._get_project_fn) if self._get_project_fn else None,
            "start_analysis_fn": staticmethod(self._start_analysis_fn) if self._start_analysis_fn else None,
        }
        handler_cls = type("BoundBridgeHandler", (_BridgeHandler,), handler_attrs)

        # Find an available port
        if port == 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()

        try:
            server = _QuietHTTPServer(("127.0.0.1", port), handler_cls)
        except OSError as e:
            return {"success": False, "error": f"Failed to start bridge server: {e}"}

        self._server = server
        self._port = port
        self._enabled = True

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._thread = thread

        logger.info(f"Bridge API server started on http://127.0.0.1:{port}")
        self._enabled = True
        return {"success": True, "data": {"port": port}}

    def stop(self) -> None:
        """Stop the bridge server if running."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._port = 0
        self._enabled = False
        logger.info("Bridge API server stopped")
