"""Touchscreen raw-event capture.

Reads from a Linux evdev touchscreen device, normalises coordinates to the
``0..1`` range defined in architecture.md §6.4, and forwards
``TouchPoint`` samples to a callback (typically the gesture mapper).

Handles both single-touch (``ABS_X``/``ABS_Y`` + ``BTN_TOUCH``) and
multitouch protocol-B (``ABS_MT_POSITION_X``/``ABS_MT_POSITION_Y`` +
``ABS_MT_TRACKING_ID``). Axis ranges are read from the device's
``absinfo`` so normalisation is exact regardless of panel model.

Auto-detection: if ``device_path`` is not given, all ``/dev/input/event*``
nodes are scanned for ``INPUT_PROP_DIRECT`` (capacitive touchscreens).
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


def _find_touch_device() -> Optional[str]:
    """Auto-detect the first device with ``ABS_MT_POSITION_X`` capability."""
    try:
        from evdev import InputDevice, list_devices, ecodes  # type: ignore

        for path in list_devices():
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_ABS not in caps:
                continue
            abs_codes = [code for code, _ in caps[ecodes.EV_ABS]]
            if ecodes.ABS_MT_POSITION_X in abs_codes:
                _log.info("auto-detected touch device: %s (%s)", path, dev.name)
                return path
        _log.info("no multitouch device found")
    except ImportError:
        _log.warning("evdev not installed; touch auto-detect skipped")
    except Exception as e:
        _log.warning("touch auto-detect failed: %s", e)
    return None


class EvdevTouchInput:
    """Linux evdev-backed reader. Supports ST and MT protocol-B."""

    def __init__(self, device_path: Optional[str] = None) -> None:
        self._device_path = device_path
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
            from evdev import InputDevice, ecodes  # type: ignore
        except ImportError:
            _log.warning("evdev not installed; touch capture disabled")
            return

        path = self._device_path or _find_touch_device()
        if path is None:
            _log.warning("no touch device path available")
            return

        try:
            device = InputDevice(path)
        except OSError as e:
            _log.warning("cannot open touch device %s: %s", path, e)
            return

        _log.info("touch capture started on %s (%s)", path, device.name)

        # Read axis ranges from the device capabilities.
        caps = device.capabilities()
        abs_caps = {}
        if ecodes.EV_ABS in caps:
            for code, absinfo in caps[ecodes.EV_ABS]:
                abs_caps[code] = absinfo

        # Determine which ABS codes to use (MT preferred over ST).
        use_mt = ecodes.ABS_MT_POSITION_X in abs_caps
        if use_mt:
            x_code = ecodes.ABS_MT_POSITION_X
            y_code = ecodes.ABS_MT_POSITION_Y
        else:
            x_code = ecodes.ABS_X
            y_code = ecodes.ABS_Y

        x_info = abs_caps.get(x_code)
        y_info = abs_caps.get(y_code)
        x_range = float((x_info.max - x_info.min) or 1) if x_info else 1.0
        y_range = float((y_info.max - y_info.min) or 1) if y_info else 1.0
        x_min = float(x_info.min) if x_info else 0.0
        y_min = float(y_info.min) if y_info else 0.0

        _log.info(
            "touch axes: x=%s [%s..%s] y=%s [%s..%s] mt=%s",
            ecodes.ABS.get(x_code, x_code),
            x_min, x_min + x_range,
            ecodes.ABS.get(y_code, y_code),
            y_min, y_min + y_range,
            use_mt,
        )

        pos_x = 0.0
        pos_y = 0.0
        pressed = False
        # For MT protocol-B, tracking_id >= 0 means finger down, -1 means up.
        mt_tracking_id: Optional[int] = None

        try:
            for event in device.read_loop():
                if self._stop.is_set():
                    break

                if event.type == ecodes.EV_ABS:
                    if event.code == x_code:
                        pos_x = (event.value - x_min) / x_range
                    elif event.code == y_code:
                        pos_y = (event.value - y_min) / y_range
                    elif use_mt and event.code == ecodes.ABS_MT_TRACKING_ID:
                        mt_tracking_id = event.value
                        pressed = mt_tracking_id >= 0

                elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                    pressed = bool(event.value)

                elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                    nx = min(1.0, max(0.0, pos_x))
                    ny = min(1.0, max(0.0, pos_y))
                    on_sample(
                        TouchPoint(
                            x=nx, y=ny, pressed=pressed,
                            timestamp=time.monotonic(),
                        )
                    )
        except Exception:
            _log.exception("touch capture loop failed")
