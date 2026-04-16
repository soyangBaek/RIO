"""T-050: Audio Worker – 별도 프로세스 진입점.

마이크 캡처 → VAD → STT → intent normalization → voice.* 이벤트 발행.
multiprocessing 기반.
"""
from __future__ import annotations

import logging
import time
from multiprocessing import Process
from typing import Any, Dict, Optional

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.stt import SttAdapter
from src.app.adapters.audio.vad import VoiceActivityDetector
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 2.0  # seconds


class AudioWorker:
    """Audio Worker 프로세스."""

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
        self._running = False

    def start(self) -> None:
        """워커 프로세스 시작."""
        self._process = Process(
            target=_audio_worker_main,
            args=(self._bus, self._config, self._headless),
            daemon=True,
            name="audio_worker",
        )
        self._process.start()
        logger.info("AudioWorker started (pid=%s)", self._process.pid)

    def stop(self) -> None:
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3)
            logger.info("AudioWorker stopped")

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _audio_worker_main(bus: QueueBus, config: Dict[str, Any], headless: bool) -> None:
    """워커 프로세스 메인 루프."""
    voice_cfg = config.get("voice", {})
    triggers_cfg = config.get("triggers", None)

    capture = AudioCapture(headless=headless)
    vad = VoiceActivityDetector(sensitivity=voice_cfg.get("vad_sensitivity", 2))
    stt = SttAdapter(headless=headless)
    normalizer = IntentNormalizer(
        triggers_config=triggers_cfg,
        min_confidence=voice_cfg.get("stt_confidence_min", 0.5),
    )

    stt.initialize()

    audio_buffer = bytearray()
    last_heartbeat = time.time()

    def on_chunk(data: bytes) -> None:
        nonlocal audio_buffer, last_heartbeat
        now = time.time()

        # heartbeat
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            bus.publish(Event(
                topic=Topics.SYSTEM_WORKER_HEARTBEAT,
                source="audio_worker",
                payload={"worker": "audio_worker", "status": "ok"},
                timestamp=now,
            ))
            last_heartbeat = now

        # VAD
        result = vad.process_chunk(data)

        if result == "started":
            audio_buffer = bytearray()
            bus.publish(Event(
                topic=Topics.VOICE_ACTIVITY_STARTED,
                source="audio_worker",
                payload={},
                timestamp=now,
            ))

        if vad.is_active:
            audio_buffer.extend(data)

        if result == "ended":
            bus.publish(Event(
                topic=Topics.VOICE_ACTIVITY_ENDED,
                source="audio_worker",
                payload={},
                timestamp=now,
            ))

            # STT
            text, confidence = stt.transcribe(bytes(audio_buffer))
            audio_buffer = bytearray()

            if text:
                intent, adj_confidence = normalizer.normalize(text, confidence)
                if intent:
                    bus.publish(Event(
                        topic=Topics.VOICE_INTENT_DETECTED,
                        source="audio_worker",
                        payload={
                            "intent": intent,
                            "text": text,
                            "confidence": adj_confidence,
                        },
                        timestamp=now,
                    ))
                else:
                    bus.publish(Event(
                        topic=Topics.VOICE_INTENT_UNKNOWN,
                        source="audio_worker",
                        payload={"text": text, "confidence": confidence},
                        timestamp=now,
                    ))

    capture.start(on_chunk)

    # headless 모드면 heartbeat만 유지
    if headless:
        try:
            while True:
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    bus.publish(Event(
                        topic=Topics.SYSTEM_WORKER_HEARTBEAT,
                        source="audio_worker",
                        payload={"worker": "audio_worker", "status": "ok"},
                        timestamp=now,
                    ))
                    last_heartbeat = now
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
