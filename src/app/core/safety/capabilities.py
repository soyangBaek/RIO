from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.app.core.state.models import CapabilityState


def detect_capabilities(
    video_globs: Iterable[str] = ("/dev/video0",),
    input_paths: Iterable[str] = ("/proc/bus/input/devices",),
) -> CapabilityState:
    camera_available = any(Path(path).exists() for path in video_globs)
    touch_available = any(Path(path).exists() for path in input_paths)
    return CapabilityState(
        camera_available=camera_available,
        mic_available=True,
        touch_available=touch_available,
        speaker_available=True,
    )

