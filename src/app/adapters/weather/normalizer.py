from __future__ import annotations


def _normalize_temperature(value: float | int | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if numeric > 150:
        numeric -= 273.15
    return round(numeric, 1)


def normalize_weather_response(payload: dict[str, object]) -> dict[str, object]:
    weather = payload.get("weather")
    condition = None
    icon_key = None
    if isinstance(weather, list) and weather:
        current = weather[0] or {}
        if isinstance(current, dict):
            condition = current.get("main") or current.get("description")
            icon_key = current.get("icon")

    main = payload.get("main")
    temperature = None
    if isinstance(main, dict):
        temperature = main.get("temp")
    if temperature is None:
        current_weather = payload.get("current_weather")
        if isinstance(current_weather, dict):
            temperature = current_weather.get("temperature")
            condition = condition or current_weather.get("weathercode")
    return {
        "ok": True,
        "temperature_c": _normalize_temperature(temperature),
        "condition": condition or "unknown",
        "icon_key": icon_key or "unknown",
        "raw": payload,
    }
