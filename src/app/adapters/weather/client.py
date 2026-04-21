from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import urlopen

from src.app.adapters.weather.normalizer import normalize_weather_response


@dataclass(slots=True)
class WeatherClient:
    base_url: str
    locations: dict[str, dict[str, float]] = field(default_factory=dict)
    default_location: str = "seoul"
    http_timeout_ms: int = 3000
    retry_count: int = 1

    def _resolve_coords(self, location: str | None) -> tuple[str, dict[str, float]] | None:
        name = (location or self.default_location).strip().lower()
        coords = self.locations.get(name)
        if coords is None and name != self.default_location:
            coords = self.locations.get(self.default_location)
            name = self.default_location
        if coords is None:
            return None
        return name, coords

    def fetch_current(self, *, location: str | None = None) -> dict[str, object]:
        resolved = self._resolve_coords(location)
        if resolved is None:
            return {"ok": False, "message": f"unknown_location:{location or self.default_location}"}
        _name, coords = resolved
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if lat is None or lon is None:
            return {"ok": False, "message": "location_missing_coordinates"}
        url = (
            f"{self.base_url}?latitude={lat}&longitude={lon}"
            "&current_weather=true&timezone=auto"
        )
        last_error: Exception | None = None
        for _ in range(self.retry_count + 1):
            try:
                with urlopen(url, timeout=self.http_timeout_ms / 1000.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return normalize_weather_response(payload)
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
        return {"ok": False, "message": str(last_error) if last_error else "weather_request_failed"}
