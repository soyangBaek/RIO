"""HTTP client for the local smart-home home-client.

Implements the contract from ``docs/prd.md``:

    PUT http://<HOME_CLIENT_IP>/device/control
    body: {"content": "에어컨 켜줘"}

Returns a normalised ``{ok, status, error?}`` dict that
:class:`SmartHomeService` consumes. Failures (non-2xx, timeouts, socket
errors) stay inside this adapter — the service layer does not branch on
HTTP-level details.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HomeClientConfig:
    base_url: str = "http://127.0.0.1:8080"
    endpoint: str = "/device/control"
    timeout_s: float = 3.0
    retry_count: int = 1


class HomeClientAdapter:
    def __init__(self, config: HomeClientConfig) -> None:
        self._cfg = config

    def send_command(self, body: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self._cfg
        url = cfg.base_url.rstrip("/") + cfg.endpoint
        encoded = json.dumps(body).encode("utf-8")

        last_error: str = ""
        for attempt in range(cfg.retry_count + 1):
            req = urllib.request.Request(
                url,
                data=encoded,
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
                    status = resp.getcode()
                    if 200 <= status < 300:
                        return {"ok": True, "status": status}
                    return {
                        "ok": False,
                        "status": status,
                        "error": f"http_{status}",
                    }
            except urllib.error.HTTPError as e:
                return {
                    "ok": False,
                    "status": getattr(e, "code", 0),
                    "error": f"http_{getattr(e, 'code', 'unknown')}",
                }
            except urllib.error.URLError as e:
                last_error = str(getattr(e, "reason", e))
            except Exception as e:
                last_error = str(e)

        return {"ok": False, "status": 0, "error": last_error or "unknown"}
