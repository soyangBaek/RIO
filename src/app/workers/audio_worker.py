from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.stt import SpeechToTextAdapter
from src.app.adapters.audio.vad import VoiceActivityDetector
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.events.models import Event
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor


@dataclass(slots=True)
class AudioWorker:
    bus: QueueBus
    capture: AudioCapture
    vad: VoiceActivityDetector
    stt: SpeechToTextAdapter
    normalizer: IntentNormalizer
    worker_name: str = "audio_worker"

    def run_once(self, *, now: datetime | None = None) -> list[Event]:
        when = now or datetime.now(timezone.utc)
        published: list[Event] = []
        frame = self.capture.read_chunk()
        if frame is not None:
            vad_events = self.vad.process(frame, now=when)
            for event in vad_events:
                self.bus.publish(event)
                published.append(event)
            transcript = self.stt.transcribe(frame)
            if transcript.text:
                intent_event = self.normalizer.normalize(
                    transcript.text,
                    confidence=transcript.confidence,
                    now=when,
                )
                if intent_event is not None:
                    self.bus.publish(intent_event)
                    published.append(intent_event)
        heartbeat = HeartbeatMonitor().heartbeat_event(self.worker_name, now=when)
        self.bus.publish(heartbeat)
        published.append(heartbeat)
        return published
