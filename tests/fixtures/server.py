"""Frontend HTTP server fixture supporting both external and embedded storefront serving."""

import http.server
import os
import socketserver
import threading
from collections.abc import Generator
from pathlib import Path

import pytest

from framework.config.settings import settings


class DualModeHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files from ./frontend with permissive CORS headers."""

    def __init__(self, *args, **kwargs):
        frontend_dir = str(Path(__file__).resolve().parents[2] / "frontend")
        super().__init__(*args, directory=frontend_dir, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        pass


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture(scope="session")
def live_server() -> Generator[str, None, None]:
    """Return configured BASE_URL when set, otherwise start an ephemeral storefront server."""
    configured_base_url = os.environ.get("BASE_URL") or (
        settings.BASE_URL if "BASE_URL" in settings.model_fields_set else None
    )
    if configured_base_url:
        yield configured_base_url.rstrip("/")
        return

    host = "127.0.0.1"
    server = ReusableTCPServer((host, 0), DualModeHTTPHandler)
    assigned_port = server.server_address[1]

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        yield f"http://{host}:{assigned_port}"
    finally:
        server.shutdown()
        server.server_close()
