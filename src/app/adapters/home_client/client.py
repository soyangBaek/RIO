from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class HomeClient:
    base_url: str
    control_path: str = "/device/control"
    control_url: str | None = None
    http_timeout_ms: int = 3000
    retry_count: int = 1

    def resolve_control_url(self) -> str:
        return self.control_url or f"{self.base_url.rstrip('/')}/{self.control_path.strip('/')}"

    def health_check(self) -> dict[str, object]:
        """Check if the ThinQ bridge is reachable via GET /health."""
        url = f"{self.base_url.rstrip('/')}/health"
        request = Request(url=url, method="GET")
        try:
            with urlopen(request, timeout=self.http_timeout_ms / 1000.0) as resp:
                body = resp.read().decode("utf-8")
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {"raw": body}
            return {"ok": True, "bridge_status": "up", **data}
        except (URLError, TimeoutError) as exc:
            return {"ok": False, "bridge_status": "down", "message": str(exc)}

    def control(self, content: str) -> dict[str, object]:
        payload = json.dumps({"content": content}).encode("utf-8")
        request_url = self.resolve_control_url()
        request = Request(
            url=request_url,
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
                data.setdefault("request_url", request_url)
                data.setdefault("request_method", "PUT")
                data.setdefault("request_content", content)
                return data
            except (URLError, TimeoutError) as exc:
                last_error = exc
        return {
            "ok": False,
            "message": str(last_error) if last_error else "home_client_request_failed",
            "request_url": request_url,
            "request_method": "PUT",
            "request_content": content,
        }

    def reset_all(self) -> dict[str, object]:
        """Turn every registered device off via POST /api/reset."""
        request_url = f"{self.base_url.rstrip('/')}/api/reset"
        request = Request(
            url=request_url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
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
                data.setdefault("request_url", request_url)
                data.setdefault("request_method", "POST")
                data.setdefault("request_content", "all:off")
                return data
            except (URLError, TimeoutError) as exc:
                last_error = exc
        return {
            "ok": False,
            "message": str(last_error) if last_error else "home_client_reset_failed",
            "request_url": request_url,
            "request_method": "POST",
            "request_content": "all:off",
        }
