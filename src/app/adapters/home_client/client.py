from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class HomeClient:
    base_url: str
    http_timeout_ms: int = 3000
    retry_count: int = 1

    def control(self, content: str) -> dict[str, object]:
        payload = json.dumps({"content": content}).encode("utf-8")
        request = Request(
            url=f"{self.base_url.rstrip('/')}/device/control",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        last_error: Exception | None = None
        for _ in range(self.retry_count + 1):
            try:
                with urlopen(request, timeout=self.http_timeout_ms / 1000.0) as resp:
                    body = resp.read().decode("utf-8")
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    data = {"raw": body}
                data.setdefault("ok", True)
                return data
            except (URLError, TimeoutError) as exc:
                last_error = exc
        return {"ok": False, "message": str(last_error) if last_error else "home_client_request_failed"}
