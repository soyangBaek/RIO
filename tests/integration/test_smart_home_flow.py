"""T-067: 스마트홈 플로우 통합 테스트.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.domains.smart_home.payloads import build_payload, SmartHomePayload
from src.app.domains.smart_home.service import SmartHomeService


class TestSmartHomeFlow(unittest.TestCase):
    def test_payload_build(self):
        p = build_payload("smarthome.aircon.on", "에어컨 켜줘")
        self.assertIsInstance(p, SmartHomePayload)
        self.assertEqual(p.content, "에어컨 켜줘")
        body = p.to_body()
        self.assertIn("content", body)

    def test_payload_default_command(self):
        p = build_payload("smarthome.light.on")
        self.assertEqual(p.content, "불 켜줘")

    def test_service_dummy_success(self):
        """home_client 없을 때 dummy 성공."""
        results = []

        def on_done(success, result=None, error=""):
            results.append(success)

        service = SmartHomeService(home_client=None)
        service.handle({"intent": "smarthome.aircon.on", "task_id": "t1"}, on_done)

        import time
        time.sleep(1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0])


if __name__ == "__main__":
    unittest.main()
