from __future__ import annotations


_WMO_TO_ICON: dict[int, tuple[str, str]] = {
    0: ("clear", "sunny"),
    1: ("mostly clear", "sunny"),
    2: ("partly cloudy", "cloudy"),
    3: ("overcast", "cloudy"),
    45: ("fog", "fog"),
    48: ("fog", "fog"),
    51: ("drizzle", "rainy"),
    53: ("drizzle", "rainy"),
    55: ("drizzle", "rainy"),
    56: ("freezing drizzle", "rainy"),
    57: ("freezing drizzle", "rainy"),
    61: ("rain", "rainy"),
    63: ("rain", "rainy"),
    65: ("rain", "rainy"),
    66: ("freezing rain", "rainy"),
    67: ("freezing rain", "rainy"),
    71: ("snow", "snowy"),
    73: ("snow", "snowy"),
    75: ("snow", "snowy"),
    77: ("snow grains", "snowy"),
    80: ("rain showers", "rainy"),
    81: ("rain showers", "rainy"),
    82: ("rain showers", "rainy"),
    85: ("snow showers", "snowy"),
    86: ("snow showers", "snowy"),
    95: ("thunderstorm", "thunder"),
    96: ("thunderstorm with hail", "thunder"),
    99: ("thunderstorm with hail", "thunder"),
}


def _normalize_temperature(value: float | int | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric > 150:
        numeric -= 273.15
    return round(numeric, 1)


def _resolve_condition_icon(code: object, fallback_condition: str | None) -> tuple[str, str]:
    if isinstance(code, bool):
        return (fallback_condition or "unknown", "unknown")
    if isinstance(code, (int, float)):
        mapped = _WMO_TO_ICON.get(int(code))
        if mapped is not None:
            return mapped
    if isinstance(fallback_condition, str) and fallback_condition:
        return (fallback_condition, "unknown")
    return ("unknown", "unknown")


def normalize_weather_response(payload: dict[str, object]) -> dict[str, object]:
    weather = payload.get("weather")
    condition: str | None = None
    icon_key: str | None = None
    if isinstance(weather, list) and weather:
        current = weather[0] or {}
        if isinstance(current, dict):
            condition = current.get("main") or current.get("description")
            icon_key = current.get("icon")

    main = payload.get("main")
    temperature: float | int | None = None
    if isinstance(main, dict):
        raw_temp = main.get("temp")
        if isinstance(raw_temp, (int, float)):
            temperature = raw_temp

    current_weather = payload.get("current_weather")
    if isinstance(current_weather, dict):
        if temperature is None:
            cw_temp = current_weather.get("temperature")
            if isinstance(cw_temp, (int, float)):
                temperature = cw_temp
        code = current_weather.get("weathercode")
        mapped_condition, mapped_icon = _resolve_condition_icon(code, condition)
        condition = mapped_condition
        icon_key = mapped_icon

    return {
        "ok": True,
        "temperature_c": _normalize_temperature(temperature),
        "condition": condition or "unknown",
        "icon_key": icon_key or "unknown",
        "raw": payload,
    }
