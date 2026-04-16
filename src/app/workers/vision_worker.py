"""T-051: Vision Worker – 별도 프로세스 진입점.

카메라 프레임 → 얼굴 검출/추적 → 제스처 인식 → vision.* 이벤트 발행.
"""
from __future__ import annotations

import logging
import time
from multiprocessing import Process
from typing import Any, Dict, Optional

from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 2.0


class VisionWorker:
    """Vision Worker 프로세스."""

    def __init__(
        self,
        event_bus: QueueBus,
        config: Dict[str, Any],
        headless: bool = False,
    ) -> None:
        self._bus = event_bus
        self._config = config
        self._headless = headless
        self._process: Optional[Process] = None

    def start(self) -> None:
        self._process = Process(
            target=_vision_worker_main,
            args=(self._bus, self._config, self._headless),
            daemon=True,
            name="vision_worker",
        )
        self._process.start()
        logger.info("VisionWorker started (pid=%s)", self._process.pid)

    def stop(self) -> None:
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3)
            logger.info("VisionWorker stopped")

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _vision_worker_main(bus: QueueBus, config: Dict[str, Any], headless: bool) -> None:
    """워커 프로세스 메인 루프."""
    vision_cfg = config.get("vision", {})
    presence_cfg = config.get("presence", {})

    webcam_cfg = config.get("webcam", {})
    device_index = webcam_cfg.get("device_index", 0)

    camera = CameraStream(device_index=device_index, headless=headless)
    face_detector = FaceDetector(
        min_confidence=vision_cfg.get("face_confidence_min", 0.6),
        headless=headless,
    )
    face_tracker = FaceTracker(
        lost_timeout_ms=presence_cfg.get("face_lost_timeout_ms", 800),
        sample_hz=presence_cfg.get("face_moved_sample_hz", 10),
    )
    gesture_detector = GestureDetector(
        min_confidence=vision_cfg.get("gesture_confidence_min", 0.75),
        headless=headless,
    )

    face_detector.initialize()
    gesture_detector.initialize()

    last_heartbeat = time.time()

    def on_frame(frame) -> None:
        nonlocal last_heartbeat
        now = time.time()

        # heartbeat
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            bus.publish(Event(
                topic=Topics.SYSTEM_WORKER_HEARTBEAT,
                source="vision_worker",
                payload={"worker": "vision_worker", "status": "ok"},
                timestamp=now,
            ))
            last_heartbeat = now

        # face detection + tracking
        detections = face_detector.detect(frame)
        face_events = face_tracker.update(detections)
        for ev in face_events:
            bus.publish(ev)

        # gesture detection
        gesture_events = gesture_detector.detect(frame)
        for ev in gesture_events:
            bus.publish(ev)

    camera.start(on_frame)

    # headless: heartbeat만 유지
    if headless:
        try:
            while True:
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    bus.publish(Event(
                        topic=Topics.SYSTEM_WORKER_HEARTBEAT,
                        source="vision_worker",
                        payload={"worker": "vision_worker", "status": "ok"},
                        timestamp=now,
                    ))
                    last_heartbeat = now
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
