"""Local HTTP media server with range request support.

Serves a single media file to the frontend video/audio player,
enabling proper seeking and streaming without loading the entire
file into memory.
"""

from __future__ import annotations

import mimetypes
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loguru import logger

_EXPECTED_CONN_ERRORS = (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)


class _QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that suppresses tracebacks for expected connection errors."""

    def handle_error(self, request, client_address):
        """Suppress traceback for client disconnects."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, _EXPECTED_CONN_ERRORS):
            return
        super().handle_error(request, client_address)


class _MediaHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves media and waveform files."""

    # Set by MediaServer before starting
    file_path: str = ""
    mime_type: str = "application/octet-stream"
    waveform_path: str = ""

    def log_message(self, format, *args):
        """Suppress default stderr logging."""

    def do_GET(self):
        # Route: /waveform serves the waveform JSON, /media serves the video
        if self.path == "/waveform":
            target = self.waveform_path
            content_type = "application/json"
        elif self.path == "/media":
            target = self.file_path
            content_type = self.mime_type
        else:
            self.send_error(404, "Not found")
            return

        if not target:
            self.send_error(404, "File not available")
            return

        path = Path(target)
        if not path.exists():
            self.send_error(404, "File not found")
            return

        file_size = path.stat().st_size

        # Parse Range header
        range_header = self.headers.get("Range")
        try:
            if range_header and range_header.startswith("bytes="):
                range_spec = range_header[6:]
                start_str, _, end_str = range_spec.partition("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    buf_size = 64 * 1024
                    while remaining > 0:
                        chunk = f.read(min(buf_size, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(64 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
        except _EXPECTED_CONN_ERRORS:
            # Client disconnected (seek, stop, navigate away) - expected
            pass

    def do_HEAD(self):
        if self.path == "/waveform":
            target = self.waveform_path
            content_type = "application/json"
        elif self.path == "/media":
            target = self.file_path
            content_type = self.mime_type
        else:
            self.send_error(404, "Not found")
            return

        if not target:
            self.send_error(404, "File not available")
            return

        path = Path(target)
        if not path.exists():
            self.send_error(404, "File not found")
            return

        file_size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()


class MediaServer:
    """Manages a local HTTP server for streaming a single media file."""

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._file_path: str = ""
        self._waveform_path: str = ""

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self, file_path: str) -> dict:
        """Start serving the given file on a random available port.

        Returns {"success": True, "data": {"url": "...", "port": N}} on success.
        """
        if self.is_running and self._file_path == file_path:
            return {
                "success": True,
                "data": {"url": f"http://127.0.0.1:{self._port}/media", "port": self._port},
            }

        # Stop existing server if running
        self.stop()

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        mime, _ = mimetypes.guess_type(file_path)
        if not mime:
            mime = "application/octet-stream"

        # Configure handler for this file
        handler_cls = type(
            "BoundMediaHandler",
            (_MediaHandler,),
            {"file_path": file_path, "mime_type": mime, "waveform_path": self._waveform_path},
        )

        # Find an available port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        try:
            server = _QuietHTTPServer(("127.0.0.1", port), handler_cls)
        except OSError as e:
            return {"success": False, "error": f"Failed to start server: {e}"}

        self._server = server
        self._port = port
        self._file_path = file_path

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._thread = thread

        url = f"http://127.0.0.1:{port}/media"
        logger.info("Media server started on {} for {}", url, file_path)
        return {"success": True, "data": {"url": url, "port": port}}

    def stop(self) -> None:
        """Stop the media server if running."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._port = 0
        self._file_path = ""
        self._waveform_path = ""
        logger.info("Media server stopped")

    def set_waveform(self, waveform_path: str) -> None:
        """Set the waveform JSON file path. The running handler picks it up immediately."""
        self._waveform_path = waveform_path
        # Update the bound handler class so in-flight requests see the new path
        if self._server:
            handler_cls = self._server.RequestHandlerClass
            handler_cls.waveform_path = waveform_path
        logger.info("Waveform path set to {}", waveform_path)
