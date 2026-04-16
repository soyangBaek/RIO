"""Touchscreen raw-event capture.

Reads from a Linux evdev touchscreen device, normalises coordinates to the
``0..1`` range defined in architecture.md §6.4, and forwards
``TouchPoint`` samples to a callback (typically the gesture mapper).

The adapter runs on a background thread because evdev reads are blocking.
A :class:`NullTouchInput` is provided for dev machines without a
touchscreen — it simply does nothing so the rest of the system still wires
up. The gesture mapper (``touch.gesture_mapper``) owns classification and
event emission; this module only produces raw samples.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TouchPoint:
    x: float  # 0..1, left→right
    y: float  # 0..1, top→bottom
    pressed: bool
    timestamp: float  # monotonic seconds


SampleCallback = Callable[[TouchPoint], None]


class NullTouchInput:
    """No-op implementation for hosts without a touchscreen."""

    def start(self, on_sample: SampleCallback) -> None:
        _log.info("NullTouchInput: no hardware, skipping touch capture")

    def stop(self) -> None:
        pass


class EvdevTouchInput:
    """Linux evdev-backed reader. Expects a protocol-B multitouch device."""

    def __init__(
        self,
        device_path: str,
        width_px: int,
        height_px: int,
    ) -> None:
        self._device_path = device_path
        self._width = max(1, int(width_px))
        self._height = max(1, int(height_px))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self, on_sample: SampleCallback) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(on_sample,), daemon=True, name="touch-input"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.0)
            self._thread = None

    def _run(self, on_sample: SampleCallback) -> None:
        try:
            # evdev is an optional dependency — degrade gracefully if missing.
            from evdev import InputDevice, categorize, ecodes  # type: ignore
        except ImportError:
            _log.warning("evdev not installed; touch capture disabled")
            return

        try:
            device = InputDevice(self._device_path)
        except OSError as e:
            _log.warning("cannot open touch device %s: %s", self._device_path, e)
            return

        pos_x = 0
        pos_y = 0
        pressed = False

        try:
            for event in device.read_loop():
                if self._stop.is_set():
                    break
                if event.type == ecodes.EV_ABS:
                    if event.code == ecodes.ABS_X:
                        pos_x = event.value
                    elif event.code == ecodes.ABS_Y:
                        pos_y = event.value
                elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                    pressed = bool(event.value)
                elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                    nx = min(1.0, max(0.0, pos_x / float(self._width)))
                    ny = min(1.0, max(0.0, pos_y / float(self._height)))
                    on_sample(
                        TouchPoint(
                            x=nx, y=ny, pressed=pressed, timestamp=time.monotonic()
                        )
                    )
        except Exception:
            _log.exception("touch capture loop failed")
