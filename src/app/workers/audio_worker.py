"""Audio worker — separate process hosting the mic → VAD → STT chain.

Architecture §2: the main orchestrator stays single-threaded; heavy audio
inference runs here and emits events through a shared
:class:`multiprocessing.Queue`. The worker also publishes a periodic
``system.worker.heartbeat`` so :class:`HeartbeatMonitor` can declare the
pipeline degraded on silence.

Entry point: :func:`run`. Expected to be launched as the target of a
``multiprocessing.Process`` with the parent's EventBus queue passed in.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import time
from typing import Optional

from ..adapters.audio import (
    FRAME_DURATION_MS,
    IntentNormalizer,
    make_capture,
    make_stt_backend,
    make_vad_backend,
)
from ..adapters.audio.vad import VADSegmenter
from ..core.events import topics
from ..core.events.models import Event, new_trace_id
from ..domains.speech.dedupe import IntentDedupe
from ..domains.speech.intent_parser import IntentParser

_log = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_INTERVAL_S = 2.0
DEFAULT_MIN_UTTER_MS = 200
DEFAULT_MAX_UTTER_MS = 8_000


def run(
    event_queue: "mp.Queue[Event]",
    stop_event,
    aliases: dict,
    stt_confidence_min: float = 0.5,
    intent_match_min: float = 0.6,
    intent_cooldown_ms: int = 1_500,
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> None:
    """Long-running audio worker loop."""
    capture = make_capture()
    vad_backend = make_vad_backend()
    stt = make_stt_backend()
    parser = IntentParser(aliases, min_confidence=intent_match_min)
    dedupe = IntentDedupe(cooldown_ms=intent_cooldown_ms)
    normalizer = IntentNormalizer(
        parser=parser,
        dedupe=dedupe,
        stt_confidence_min=stt_confidence_min,
    )
    segmenter = VADSegmenter(backend=vad_backend)

    utter_buf = bytearray()
    last_heartbeat = 0.0
    utter_started_at: Optional[float] = None
    last_trace_id: Optional[str] = None

    _log.info("audio_worker starting")
    try:
        for frame in capture.frames():
            if stop_event.is_set():
                break

            now = time.monotonic()

            # Heartbeat.
            if now - last_heartbeat >= heartbeat_interval_s:
                _publish(
                    event_queue,
                    Event(
                        topic=topics.SYSTEM_WORKER_HEARTBEAT,
                        payload={"worker": "audio_worker", "status": "ok"},
                        timestamp=now,
                        source="audio_worker",
                    ),
                )
                last_heartbeat = now

            started, ended = segmenter.push(frame)

            if started:
                utter_buf.clear()
                utter_started_at = now
                last_trace_id = new_trace_id()
                _publish(
                    event_queue,
                    Event(
                        topic=topics.VOICE_ACTIVITY_STARTED,
                        payload={},
                        timestamp=now,
                        trace_id=last_trace_id,
                        source="audio_worker",
                    ),
                )

            if segmenter.in_voice:
                utter_buf.extend(frame)
                # cap utterance length to avoid unbounded buffers
                if utter_started_at is not None and (now - utter_started_at) * 1000 >= DEFAULT_MAX_UTTER_MS:
                    ended = True  # force-close
                    segmenter._in_voice = False  # type: ignore[attr-defined]

            if ended:
                trace_id = last_trace_id or new_trace_id()
                _publish(
                    event_queue,
                    Event(
                        topic=topics.VOICE_ACTIVITY_ENDED,
                        payload={},
                        timestamp=now,
                        trace_id=trace_id,
                        source="audio_worker",
                    ),
                )
                duration_ms = (now - (utter_started_at or now)) * 1000
                if duration_ms >= DEFAULT_MIN_UTTER_MS and utter_buf:
                    _handle_utterance(
                        event_queue, normalizer, stt, bytes(utter_buf), now, trace_id
                    )
                utter_buf.clear()
                utter_started_at = None

    except Exception:
        _log.exception("audio_worker crashed")
    finally:
        try:
            capture.stop()
        except Exception:
            pass
        _log.info("audio_worker stopped")


def _handle_utterance(
    event_queue,
    normalizer: IntentNormalizer,
    stt,
    pcm: bytes,
    now: float,
    trace_id: str,
) -> None:
    try:
        text, confidence = stt.transcribe(pcm)
    except Exception:
        _log.exception("STT failed")
        text, confidence = "", 0.0
    event = normalizer.normalize(text, stt_confidence=confidence, now=now)
    if event is None:
        return
    # Preserve the trace id established at voice.activity.started.
    event = Event(
        topic=event.topic,
        payload=event.payload,
        timestamp=event.timestamp,
        trace_id=trace_id,
        source="audio_worker",
    )
    _publish(event_queue, event)


def _publish(event_queue, event: Event) -> None:
    try:
        event_queue.put_nowait(event)
    except Exception:
        # On overflow, discard — parent EventBus uses drop_oldest which we
        # cannot invoke from the worker without racing; a dropped worker
        # event is less harmful than blocking the loop.
        _log.warning("audio_worker event queue full; dropped %s", event.topic)
