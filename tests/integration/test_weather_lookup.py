"""Weather lookup integration (no real network)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.adapters.weather import WeatherClient, WeatherConfig, normalize  # noqa: E402


def test_normalize_owm_shape():
    data = normalize({"main": {"temp": 21.3}, "weather": [{"main": "Clouds"}]})
    assert data == {"temperature_c": 21.3, "icon": "weather_cloudy", "condition": "흐림"}


def test_client_without_credentials_fails_fast():
    wc = WeatherClient(WeatherConfig())
    r = wc.current()
    assert r == {"ok": False, "error": "no_api_key_or_location"}


def test_client_parses_successful_response():
    cfg = WeatherConfig(api_key="fake", q="Seoul")
    wc = WeatherClient(cfg)

    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def read(self):
            import json
            return json.dumps({"main": {"temp": 18.0}, "weather": [{"main": "Clear"}]}).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=_Resp()):
        r = wc.current()
    assert r == {"ok": True, "data": {"temperature_c": 18.0, "icon": "weather_sunny", "condition": "맑음"}}


def test_client_returns_error_on_network_failure():
    cfg = WeatherConfig(api_key="fake", q="Seoul", retry_count=0)
    wc = WeatherClient(cfg)
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
        r = wc.current()
    assert r["ok"] is False and "offline" in r["error"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
