"""T-049: Home-client HTTP 클라이언트.

architecture.md §5.2: PUT /device/control, body: {"content": "<command>"}.
smarthome.request.sent / smarthome.result 이벤트 생성.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 3000


class HomeClient:
    """스마트홈 Home-client HTTP 어댑터."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1",
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
        retry_count: int = 1,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_ms / 1000
        self._retry_count = retry_count

    def send_command(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /device/control 호출.

        Returns: {"ok": bool, "status": int, "error": str?}
        """
        url = f"{self._base_url}/device/control"

        for attempt in range(1 + self._retry_count):
            try:
                data = json.dumps(body).encode("utf-8")
                req = Request(url, data=data, method="PUT")
                req.add_header("Content-Type", "application/json")

                with urlopen(req, timeout=self._timeout) as resp:
                    status = resp.status
                    resp_body = resp.read().decode()

                if 200 <= status < 300:
                    return {"ok": True, "status": status}
                else:
                    return {"ok": False, "status": status, "error": resp_body}

            except (URLError, Exception) as e:
                logger.warning(
                    "HomeClient attempt %d/%d failed: %s",
                    attempt + 1, 1 + self._retry_count, e,
                )
                if attempt >= self._retry_count:
                    return {"ok": False, "error": str(e)}

        return {"ok": False, "error": "max retries exceeded"}

    def send_and_emit(self, body: Dict[str, Any]) -> Event:
        """command 전송 + smarthome.result 이벤트 반환."""
        result = self.send_command(body)
        return Event(
            topic=Topics.SMARTHOME_RESULT,
            source="main/home_client",
            payload=result,
        )
