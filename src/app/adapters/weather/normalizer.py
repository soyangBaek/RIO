"""Normalise the upstream weather API response to our internal shape.

Consumers (EffectPlanner TTS, HUD weather widget) expect a minimal dict:

    {
      "temperature_c": float,
      "condition": str,   # localized short string ("맑음", "Cloudy")
      "icon": str,        # slot name matching assets/ui/weather_*
    }

The normalizer handles two common upstream shapes — OpenWeatherMap (``main``
+ ``weather``) and a generic flat shape — without forcing either on the
caller. Unknown shapes yield ``None``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Map OWM ``main`` group → our icon slot.
_ICON_BY_MAIN: Dict[str, str] = {
    "Clear": "weather_sunny",
    "Clouds": "weather_cloudy",
    "Drizzle": "weather_rain",
    "Rain": "weather_rain",
    "Thunderstorm": "weather_rain",
    "Snow": "weather_cloudy",
    "Mist": "weather_cloudy",
    "Fog": "weather_cloudy",
    "Haze": "weather_cloudy",
}

_KO_CONDITION: Dict[str, str] = {
    "weather_sunny": "맑음",
    "weather_cloudy": "흐림",
    "weather_rain": "비",
}


def normalize(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    # OpenWeatherMap shape
    if "main" in raw and isinstance(raw["main"], dict) and "temp" in raw["main"]:
        temperature = raw["main"].get("temp")
        weather_list = raw.get("weather") or []
        main = (weather_list[0].get("main") if weather_list else "") or "Clouds"
        icon = _ICON_BY_MAIN.get(main, "weather_cloudy")
        condition = _KO_CONDITION.get(icon, main)
        return {
            "temperature_c": _coerce_float(temperature),
            "condition": condition,
            "icon": icon,
        }

    # Generic flat shape
    if "temperature_c" in raw and "condition" in raw:
        icon = raw.get("icon") or "weather_cloudy"
        return {
            "temperature_c": _coerce_float(raw.get("temperature_c")),
            "condition": str(raw.get("condition") or ""),
            "icon": str(icon),
        }

    return None


def _coerce_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
