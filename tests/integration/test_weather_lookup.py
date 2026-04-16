"""T-068: 날씨 조회 통합 테스트.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.adapters.weather.client import WeatherClient
from src.app.adapters.weather.normalizer import WeatherNormalizer
from src.app.core.events.topics import Topics


class TestWeatherLookup(unittest.TestCase):
    def test_normalizer_openweather_format(self):
        raw = {
            "main": {"temp": 25, "humidity": 60},
            "weather": [{"main": "Clear", "description": "맑음", "icon": "01d"}],
        }
        norm = WeatherNormalizer()
        result = norm.normalize(raw)
        self.assertEqual(result["temperature"], 25)
        self.assertEqual(result["condition"], "clear")

    def test_normalizer_to_speech(self):
        norm = WeatherNormalizer()
        data = {"temperature": 22, "condition": "clear", "description": "맑음"}
        text = norm.to_speech(data)
        self.assertIn("22", text)
        self.assertIn("맑음", text)

    def test_dummy_weather_client(self):
        """API URL 없을 때 dummy 응답."""
        client = WeatherClient()
        event = client.fetch_weather()
        self.assertEqual(event.topic, Topics.WEATHER_RESULT)
        self.assertTrue(event.payload["ok"])
        self.assertIn("temperature", event.payload["data"])


if __name__ == "__main__":
    unittest.main()
