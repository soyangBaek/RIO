"""T-046: 날씨 응답 정규화.

API 응답 → 통합 포맷.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class WeatherNormalizer:
    """날씨 API 응답 정규화."""

    def normalize(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """다양한 API 응답을 통합 포맷으로 변환."""

        # 통합 출력 포맷
        result: Dict[str, Any] = {
            "temperature": None,
            "condition": "unknown",
            "humidity": None,
            "description": "",
            "icon": "",
        }

        # OpenWeatherMap 형태
        if "main" in raw_response:
            main = raw_response["main"]
            result["temperature"] = main.get("temp")
            result["humidity"] = main.get("humidity")
            weather = raw_response.get("weather", [{}])
            if weather:
                result["condition"] = weather[0].get("main", "unknown").lower()
                result["description"] = weather[0].get("description", "")
                result["icon"] = weather[0].get("icon", "")
            return result

        # 직접 제공 포맷
        if "temperature" in raw_response:
            result.update({
                "temperature": raw_response.get("temperature"),
                "condition": raw_response.get("condition", "unknown"),
                "humidity": raw_response.get("humidity"),
                "description": raw_response.get("description", ""),
            })

        return result

    def to_speech(self, data: Dict[str, Any]) -> str:
        """날씨 데이터 → TTS용 문자열."""
        temp = data.get("temperature")
        desc = data.get("description") or data.get("condition", "")
        if temp is not None:
            return f"현재 기온 {temp}도, {desc}입니다."
        return "날씨 정보를 가져올 수 없습니다."
