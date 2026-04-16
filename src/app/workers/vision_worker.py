"""Vision worker — separate process hosting camera → face detection/tracking.

Emits ``vision.face.detected`` / ``vision.face.moved`` / ``vision.face.lost``
events plus a periodic ``system.worker.heartbeat``. Gesture detection is
wired in via :class:`GestureDetector` but the default implementation is a
null detector (Phase 2 will light it up).

Debug preview
-------------
``debug_preview=True`` opens a second X11 window (via ``cv2.imshow``)
showing the live camera feed with detection overlays. The worker still
owns the single camera handle, so this flag is the safe way to visualise
what RIO sees while ``app.main`` is running — no second script needs to
fight for ``/dev/video0``. Pressing ``q`` in the preview window only
closes the preview; it never stops the worker.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import time
from typing import Optional

from ..adapters.vision import (
    FaceTracker,
    FaceTrackerConfig,
    TrackEvent,
    make_camera,
    make_face_detector,
    make_gesture_detector,
)
from ..core.events import topics
from ..core.events.models import Event, new_trace_id

_log = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_INTERVAL_S = 2.0
_PREVIEW_WINDOW = "RIO camera preview"


def run(
    event_queue: "mp.Queue[Event]",
    stop_event,
    face_confidence_min: float = 0.6,
    face_lost_timeout_ms: int = 800,
    face_moved_sample_hz: int = 10,
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
    device: int = 0,
    debug_preview: bool = False,
) -> None:
    camera = make_camera(device=device)
    face_det = make_face_detector(min_confidence=face_confidence_min)
    gesture_det = make_gesture_detector()
    tracker = FaceTracker(
        config=FaceTrackerConfig(
            face_lost_timeout_ms=face_lost_timeout_ms,
            face_moved_sample_hz=face_moved_sample_hz,
        )
    )

    preview = _PreviewRenderer() if debug_preview else None

    last_heartbeat = 0.0
    _log.info("vision_worker starting%s", " (preview ON)" if preview else "")
    try:
        for frame in camera.frames():
            if stop_event.is_set():
                break
            now = time.monotonic()

            if now - last_heartbeat >= heartbeat_interval_s:
                _publish(
                    event_queue,
                    Event(
                        topic=topics.SYSTEM_WORKER_HEARTBEAT,
                        payload={"worker": "vision_worker", "status": "ok"},
                        timestamp=now,
                        source="vision_worker",
                    ),
                )
                last_heartbeat = now

            detections = face_det.detect(frame) if frame is not None else []
            event_kind, payload = tracker.update(detections, now=now)

            topic = _track_topic(event_kind)
            if topic is not None and payload is not None:
                _publish(
                    event_queue,
                    Event(
                        topic=topic,
                        payload=payload,
                        timestamp=now,
                        trace_id=new_trace_id(),
                        source="vision_worker",
                    ),
                )

            # Gesture (Phase 2): null detector returns None today.
            if frame is not None:
                g = gesture_det.detect(frame)
                if g is not None:
                    _publish(
                        event_queue,
                        Event(
                            topic=topics.VISION_GESTURE_DETECTED,
                            payload={"gesture": g.gesture, "confidence": g.confidence},
                            timestamp=now,
                            trace_id=new_trace_id(),
                            source="vision_worker",
                        ),
                    )

            if preview is not None and frame is not None:
                preview.show(frame, detections, event_kind, now)

    except Exception:
        _log.exception("vision_worker crashed")
    finally:
        try:
            camera.stop()
        except Exception:
            pass
        if preview is not None:
            preview.close()
        _log.info("vision_worker stopped")


def _track_topic(kind: TrackEvent) -> Optional[str]:
    if kind is TrackEvent.DETECTED:
        return topics.VISION_FACE_DETECTED
    if kind is TrackEvent.MOVED:
        return topics.VISION_FACE_MOVED
    if kind is TrackEvent.LOST:
        return topics.VISION_FACE_LOST
    return None


def _publish(event_queue, event: Event) -> None:
    try:
        event_queue.put_nowait(event)
    except Exception:
        _log.warning("vision_worker event queue full; dropped %s", event.topic)


class _PreviewRenderer:
    """Wraps OpenCV ``imshow`` so the worker loop stays readable."""

    def __init__(self) -> None:
        self._cv2 = None
        self._enabled = False
        self._last_t = time.monotonic()
        self._fps = 0.0
        try:
            import cv2  # type: ignore
            self._cv2 = cv2
            cv2.namedWindow(_PREVIEW_WINDOW, cv2.WINDOW_NORMAL)
            self._enabled = True
        except Exception as e:  # pragma: no cover - env dependent
            _log.warning("debug_preview requested but cv2 unavailable (%s)", e)

    def show(self, frame, detections, track_event: TrackEvent, now: float) -> None:
        if not self._enabled or frame is None:
            return
        cv2 = self._cv2

        h, w = frame.shape[:2]
        # Annotate a copy so the detector does not see the overlays.
        canvas = frame.copy()

        for det in detections:
            bx, by, bw, bh = det.bbox
            x, y = int(bx * w), int(by * h)
            pw, ph = int(bw * w), int(bh * h)
            cv2.rectangle(canvas, (x, y), (x + pw, y + ph), (0, 255, 0), 2)
            cx, cy = det.center
            cv2.circle(canvas, (int(cx * w), int(cy * h)), 4, (0, 255, 255), -1)
            label = f"c=({cx:.2f},{cy:.2f}) p={det.confidence:.2f}"
            cv2.putText(
                canvas, label, (x, max(0, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
            )

        dt = max(1e-3, now - self._last_t)
        self._fps = 0.9 * self._fps + 0.1 / dt if self._fps > 0 else 1.0 / dt
        self._last_t = now
        hud = (
            f"{self._fps:5.1f} fps  faces={len(detections)}  "
            f"event={track_event.value}  (q: hide)"
        )
        cv2.putText(
            canvas, hud, (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA,
        )
        try:
            cv2.imshow(_PREVIEW_WINDOW, canvas)
            # 1 ms is the conventional minimum; must be called for the window
            # event loop to process paints.
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self.close()
        except Exception:
            _log.exception("preview imshow failed; disabling")
            self._enabled = False

    def close(self) -> None:
        if not self._enabled or self._cv2 is None:
            return
        try:
            self._cv2.destroyWindow(_PREVIEW_WINDOW)
        except Exception:
            pass
        self._enabled = False
