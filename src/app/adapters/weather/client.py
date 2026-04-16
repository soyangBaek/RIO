"""Weather API HTTP client.

Keeps the query narrow — we only need the *current* weather for the
configured city/latlon. The response is converted through
:func:`normalize` into the internal shape. Timeouts/retries come from
``configs/thresholds.yaml`` (``task.http_timeout_ms``, ``task.http_retry_count``).

Failure modes surface as ``weather.result {ok: false, error}`` events in
the caller so scenarios INT-06b / OPS-01 behave correctly.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .normalizer import normalize

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeatherConfig:
    base_url: str = "https://api.openweathermap.org/data/2.5/weather"
    api_key: Optional[str] = None
    q: Optional[str] = None       # city name
    lat: Optional[float] = None
    lon: Optional[float] = None
    units: str = "metric"
    lang: str = "kr"
    timeout_s: float = 3.0
    retry_count: int = 1


class WeatherClient:
    def __init__(self, config: WeatherConfig) -> None:
        self._cfg = config

    def current(self) -> Dict[str, Any]:
        """Return the normalised weather dict, or ``{ok: False, error}``."""
        url = self._build_url()
        if url is None:
            return {"ok": False, "error": "no_api_key_or_location"}

        last_error: Optional[str] = None
        for attempt in range(self._cfg.retry_count + 1):
            try:
                with urllib.request.urlopen(url, timeout=self._cfg.timeout_s) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError as e:
                last_error = str(getattr(e, "reason", e))
                continue
            except Exception as e:
                last_error = str(e)
                continue

            data = normalize(raw)
            if data is None:
                return {"ok": False, "error": "unrecognised_response"}
            return {"ok": True, "data": data}

        return {"ok": False, "error": last_error or "unknown"}

    def _build_url(self) -> Optional[str]:
        cfg = self._cfg
        if not cfg.api_key:
            return None
        params: Dict[str, str] = {
            "appid": cfg.api_key,
            "units": cfg.units,
            "lang": cfg.lang,
        }
        if cfg.q:
            params["q"] = cfg.q
        elif cfg.lat is not None and cfg.lon is not None:
            params["lat"] = str(cfg.lat)
            params["lon"] = str(cfg.lon)
        else:
            return None
        return f"{cfg.base_url}?{urllib.parse.urlencode(params)}"
