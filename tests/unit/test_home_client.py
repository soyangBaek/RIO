from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.app.adapters.home_client.client import HomeClient


class _RecordingHandler(BaseHTTPRequestHandler):
    server_version = "RIOTest/1.0"
    protocol_version = "HTTP/1.1"

    def do_PUT(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        self.server.recorded = {  # type: ignore[attr-defined]
            "method": "PUT",
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": body,
        }
        payload = json.dumps({"ok": True, "message": "accepted"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class HomeClientTest(unittest.TestCase):
    def test_control_sends_put_request_to_configured_path(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        try:
            client = HomeClient(base_url=base_url, control_path="/device/control", http_timeout_ms=1000)
            response = client.control("aircon.living_room:set_temperature:28")
        finally:
            thread.join(timeout=2.0)
            server.server_close()

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_url"], f"{base_url}/device/control")
        self.assertEqual(response["request_method"], "PUT")
        self.assertEqual(response["request_content"], "aircon.living_room:set_temperature:28")
        recorded = server.recorded  # type: ignore[attr-defined]
        self.assertEqual(recorded["method"], "PUT")
        self.assertEqual(recorded["path"], "/device/control")
        self.assertEqual(json.loads(recorded["body"]), {"content": "aircon.living_room:set_temperature:28"})

    def test_control_url_overrides_base_url_and_path(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        control_url = f"http://127.0.0.1:{server.server_port}/bridge/thinq/control"

        try:
            client = HomeClient(
                base_url="http://127.0.0.1",
                control_path="/device/control",
                control_url=control_url,
                http_timeout_ms=1000,
            )
            response = client.control("speaker.main:play")
        finally:
            thread.join(timeout=2.0)
            server.server_close()

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_url"], control_url)
        self.assertEqual(response["request_content"], "speaker.main:play")
        recorded = server.recorded  # type: ignore[attr-defined]
        self.assertEqual(recorded["path"], "/bridge/thinq/control")
        self.assertEqual(json.loads(recorded["body"]), {"content": "speaker.main:play"})


if __name__ == "__main__":
    unittest.main()
