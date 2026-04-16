"""T-047: 날씨 API 클라이언트.

HTTP 요청 + weather.result 이벤트 생성.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
import json

from src.app.adapters.weather.normalizer import WeatherNormalizer
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 3000


class WeatherClient:
    """날씨 API 클라이언트."""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._timeout = timeout_ms / 1000
        self._normalizer = WeatherNormalizer()

    def fetch_weather(self) -> Event:
        """날씨 조회 → weather.result 이벤트 반환."""
        if not self._api_url:
            # dummy 응답
            dummy_data = {
                "temperature": 22,
                "condition": "clear",
                "humidity": 55,
                "description": "맑음",
            }
            normalized = self._normalizer.normalize(dummy_data)
            return Event(
                topic=Topics.WEATHER_RESULT,
                source="main/weather",
                payload={"ok": True, "data": normalized},
            )

        try:
            req = Request(self._api_url)
            if self._api_key:
                req.add_header("Authorization", f"Bearer {self._api_key}")

            with urlopen(req, timeout=self._timeout) as resp:
                raw = json.loads(resp.read().decode())

            normalized = self._normalizer.normalize(raw)
            return Event(
                topic=Topics.WEATHER_RESULT,
                source="main/weather",
                payload={"ok": True, "data": normalized},
            )

        except (URLError, json.JSONDecodeError, Exception) as e:
            logger.error("Weather API error: %s", e)
            return Event(
                topic=Topics.WEATHER_RESULT,
                source="main/weather",
                payload={"ok": False, "error": str(e)},
            )

    @property
    def normalizer(self) -> WeatherNormalizer:
        return self._normalizer
