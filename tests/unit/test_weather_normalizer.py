from __future__ import annotations

import unittest

from src.app.adapters.weather.client import WeatherClient
from src.app.adapters.weather.normalizer import normalize_weather_response


class NormalizeOpenMeteoResponse(unittest.TestCase):
    def test_clear_sky_maps_to_sunny(self) -> None:
        result = normalize_weather_response(
            {"current_weather": {"temperature": 22.4, "weathercode": 0}}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["icon_key"], "sunny")
        self.assertEqual(result["condition"], "clear")
        self.assertEqual(result["temperature_c"], 22.4)

    def test_rain_codes_map_to_rainy(self) -> None:
        for code in (51, 61, 65, 80, 82):
            result = normalize_weather_response(
                {"current_weather": {"temperature": 12.0, "weathercode": code}}
            )
            self.assertEqual(result["icon_key"], "rainy", msg=f"code={code}")

    def test_snow_codes_map_to_snowy(self) -> None:
        for code in (71, 73, 75, 85, 86):
            result = normalize_weather_response(
                {"current_weather": {"temperature": -2.0, "weathercode": code}}
            )
            self.assertEqual(result["icon_key"], "snowy", msg=f"code={code}")

    def test_thunderstorm_codes_map_to_thunder(self) -> None:
        for code in (95, 96, 99):
            result = normalize_weather_response(
                {"current_weather": {"temperature": 20.0, "weathercode": code}}
            )
            self.assertEqual(result["icon_key"], "thunder", msg=f"code={code}")

    def test_unknown_code_falls_back(self) -> None:
        result = normalize_weather_response(
            {"current_weather": {"temperature": 15.0, "weathercode": 1234}}
        )
        self.assertEqual(result["icon_key"], "unknown")
        self.assertEqual(result["condition"], "unknown")


class WeatherClientLocationResolver(unittest.TestCase):
    def _client(self) -> WeatherClient:
        return WeatherClient(
            base_url="https://example.invalid/forecast",
            locations={
                "seoul": {"latitude": 37.5665, "longitude": 126.9780},
                "busan": {"latitude": 35.1796, "longitude": 129.0756},
            },
            default_location="seoul",
        )

    def test_named_location_resolves(self) -> None:
        client = self._client()
        resolved = client._resolve_coords("busan")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        name, coords = resolved
        self.assertEqual(name, "busan")
        self.assertAlmostEqual(coords["latitude"], 35.1796)

    def test_none_defaults_to_seoul(self) -> None:
        client = self._client()
        resolved = client._resolve_coords(None)
        assert resolved is not None
        self.assertEqual(resolved[0], "seoul")

    def test_unknown_location_falls_back_to_default(self) -> None:
        client = self._client()
        resolved = client._resolve_coords("atlantis")
        assert resolved is not None
        self.assertEqual(resolved[0], "seoul")

    def test_unknown_location_with_empty_default_returns_none(self) -> None:
        client = WeatherClient(base_url="x", locations={}, default_location="seoul")
        self.assertIsNone(client._resolve_coords("atlantis"))


if __name__ == "__main__":
    unittest.main()
