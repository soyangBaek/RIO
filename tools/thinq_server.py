"""ThinQ Bridge Server – 거실 스마트홈 대시보드.

RIO 로봇에서 보내는 PUT /device/control 요청을 수신하고,
디바이스 상태를 추적하여 웹 대시보드에 실시간 반영합니다.

실행:
    python tools/thinq_server.py [--host 0.0.0.0] [--port 8123]

웹 대시보드:
    http://<라즈베리파이IP>:8123/
"""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "ui"

# ── Device state store ──────────────────────────────────────────────

_lock = threading.Lock()
_device_states: dict[str, dict] = {
    "tv.living_room": {"name": "TV", "on": False, "last_action": None, "updated_at": None},
    "light.main": {"name": "거실 조명", "on": False, "last_action": None, "updated_at": None},
    "aircon.living_room": {"name": "에어컨", "on": False, "last_action": None, "updated_at": None, "temperature_c": None},
    "cleaner.bot": {"name": "로봇청소기", "on": False, "last_action": None, "updated_at": None},
    "speaker.main": {"name": "음악", "on": False, "last_action": None, "updated_at": None},
}

# SSE subscriber queues
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _broadcast_state():
    """Push current state to all SSE subscribers."""
    with _lock:
        snapshot = json.dumps(_get_state_snapshot())
    dead: list[queue.Queue] = []
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.put_nowait(snapshot)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


def _get_state_snapshot() -> dict:
    return {
        "devices": {
            dev_id: {**info}
            for dev_id, info in _device_states.items()
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _process_control(content: str) -> dict:
    """Parse device command string and update state."""
    parts = content.split(":")
    if len(parts) < 2:
        return {"ok": False, "message": f"Invalid command format: {content}"}

    device_id = parts[0]
    action = parts[1]
    params = parts[2:] if len(parts) > 2 else []

    now = datetime.now(timezone.utc).isoformat()

    with _lock:
        if device_id not in _device_states:
            _device_states[device_id] = {
                "name": device_id,
                "on": False,
                "last_action": None,
                "updated_at": None,
            }
        dev = _device_states[device_id]
        dev["last_action"] = action
        dev["updated_at"] = now

        if action in ("on", "start", "play"):
            dev["on"] = True
        elif action in ("off", "stop"):
            dev["on"] = False
        elif action == "set_temperature" and params:
            dev["on"] = True
            try:
                dev["temperature_c"] = int(params[0])
            except ValueError:
                pass

    _broadcast_state()

    return {
        "ok": True,
        "message": f"{device_id} → {action}",
        "device_id": device_id,
        "action": action,
    }


# ── Event log ───────────────────────────────────────────────────────

_event_log: list[dict] = []
_event_log_lock = threading.Lock()
MAX_LOG = 100


def _log_event(entry: dict):
    with _event_log_lock:
        _event_log.append(entry)
        if len(_event_log) > MAX_LOG:
            del _event_log[: len(_event_log) - MAX_LOG]


# ── HTTP Handler ────────────────────────────────────────────────────

class ThinQHandler(BaseHTTPRequestHandler):
    """Handles device control requests and serves the dashboard."""

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {fmt % args}")

    # ── GET routes ──────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_dashboard()
        elif path == "/api/state":
            self._serve_json_state()
        elif path == "/api/events":
            self._serve_sse()
        elif path == "/api/log":
            self._serve_event_log()
        else:
            self._send(404, "text/plain", "Not Found")

    def _serve_dashboard(self):
        html_path = ASSETS_DIR / "thinq_dashboard.html"
        if not html_path.exists():
            self._send(500, "text/plain", "Dashboard HTML not found")
            return
        content = html_path.read_text(encoding="utf-8")
        self._send(200, "text/html; charset=utf-8", content)

    def _serve_json_state(self):
        with _lock:
            data = _get_state_snapshot()
        self._send(200, "application/json", json.dumps(data, ensure_ascii=False))

    def _serve_event_log(self):
        with _event_log_lock:
            data = list(_event_log)
        self._send(200, "application/json", json.dumps(data, ensure_ascii=False))

    def _serve_sse(self):
        """Server-Sent Events stream for real-time updates."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q: queue.Queue = queue.Queue(maxsize=50)
        with _sse_lock:
            _sse_clients.append(q)

        try:
            # Send initial state
            with _lock:
                init = json.dumps(_get_state_snapshot())
            self.wfile.write(f"data: {init}\n\n".encode())
            self.wfile.flush()

            while True:
                try:
                    data = q.get(timeout=25)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    # ── PUT route ───────────────────────────────────────────────────

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in ("/device/control", "/bridge/thinq/control", "/api/thinq/control"):
            self._handle_control()
        else:
            self._send(404, "text/plain", "Not Found")

    def _handle_control(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Empty body"}))
            return

        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Invalid JSON"}))
            return

        content = body.get("content")
        if not content or not isinstance(content, str):
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Missing 'content' field"}))
            return

        result = _process_control(content)

        _log_event({
            "time": datetime.now(timezone.utc).isoformat(),
            "content": content,
            "result": result,
        })

        self._send(200, "application/json", json.dumps(result, ensure_ascii=False))

    # ── POST route (convenience alias) ──────────────────────────────

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/reset":
            self._handle_reset()
        elif path == "/api/toggle":
            self._handle_toggle()
        else:
            self.do_PUT()

    def _handle_toggle(self):
        """Toggle a device on/off from the web dashboard."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Empty body"}))
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Invalid JSON"}))
            return
        device_id = body.get("device_id")
        if not device_id or not isinstance(device_id, str):
            self._send(400, "application/json", json.dumps({"ok": False, "message": "Missing device_id"}))
            return
        with _lock:
            dev = _device_states.get(device_id)
            if not dev:
                self._send(404, "application/json", json.dumps({"ok": False, "message": "Unknown device"}))
                return
            new_on = not dev["on"]
        action = "on" if new_on else "off"
        # Map special actions per device type
        if device_id == "cleaner.bot":
            action = "start" if new_on else "stop"
        elif device_id == "speaker.main":
            action = "play" if new_on else "stop"
        content = f"{device_id}:{action}"
        result = _process_control(content)
        _log_event({"time": datetime.now(timezone.utc).isoformat(), "content": content, "result": result})
        self._send(200, "application/json", json.dumps(result, ensure_ascii=False))

    def _handle_reset(self):
        """Reset all device states to off."""
        with _lock:
            for dev in _device_states.values():
                dev["on"] = False
                dev["last_action"] = "reset"
                dev["updated_at"] = datetime.now(timezone.utc).isoformat()
        _broadcast_state()
        self._send(200, "application/json", json.dumps({"ok": True, "message": "All devices reset"}))

    # ── OPTIONS (CORS) ──────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── helpers ──────────────────────────────────────────────────────

    def _send(self, code: int, content_type: str, body: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


# ── Threaded server ─────────────────────────────────────────────────

class ThreadedHTTPServer(HTTPServer):
    """Handle each request in a new thread (needed for SSE)."""
    daemon_threads = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self.process_request_thread, args=(request, client_address))
        t.daemon = True
        t.start()

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    parser = argparse.ArgumentParser(description="ThinQ Bridge Server – 거실 스마트홈 대시보드")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8123, help="Port (default: 8123)")
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.host, args.port), ThinQHandler)
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  ThinQ Bridge Server                        ║")
    print(f"║  Dashboard : http://{args.host}:{args.port}/         ║")
    print(f"║  Control   : PUT /device/control             ║")
    print(f"║  SSE Stream: GET /api/events                 ║")
    print(f"╚══════════════════════════════════════════════╝")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        server.shutdown()


if __name__ == "__main__":
    main()
