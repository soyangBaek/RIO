"""T-066: 사진 촬영 시퀀스 통합 테스트.
"""
import sys
import unittest

sys.path.insert(0, ".")

from src.app.adapters.camera.capture import CameraCapture
from src.app.adapters.camera.storage import PhotoStorage
from src.app.domains.photo.service import PhotoService


class TestPhotoSequence(unittest.TestCase):
    def test_dummy_capture(self):
        """headless 모드에서 더미 사진 촬영."""
        capture = CameraCapture(headless=True)
        path = capture.capture_photo()
        self.assertIn(".jpg", path)

    def test_photo_service_callback(self):
        """PhotoService가 done_callback을 호출하는지."""
        results = []

        def on_done(success, result=None, error=""):
            results.append({"success": success, "result": result, "error": error})

        service = PhotoService(camera_capture=None, sfx_player=None)
        service.handle({"task_id": "test"}, on_done)

        # 비동기이므로 잠시 대기
        import time
        time.sleep(5)  # countdown 3s + margin

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])


if __name__ == "__main__":
    unittest.main()
