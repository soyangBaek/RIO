from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen

from src.app.adapters.weather.normalizer import normalize_weather_response


@dataclass(slots=True)
class WeatherClient:
    base_url: str
    http_timeout_ms: int = 3000
    retry_count: int = 1

    def fetch_current(self, *, location: str = "seoul") -> dict[str, object]:
        last_error: Exception | None = None
        for _ in range(self.retry_count + 1):
            try:
                with urlopen(f"{self.base_url}?q={location}", timeout=self.http_timeout_ms / 1000.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return normalize_weather_response(payload)
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
        return {"ok": False, "message": str(last_error) if last_error else "weather_request_failed"}
