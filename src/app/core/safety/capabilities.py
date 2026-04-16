"""Capability flags for the RIO system.

At boot the orchestrator probes the hardware to decide which features are
available; the resulting flags live in ``State.extended.capabilities`` so
reducers/adapters can short-circuit work that would fail (scenarios
``OPS-03``, ``OPS-04``, ``OPS-05``).

Two categories of flags are tracked, both in the same dictionary:

* **Hardware probes** (``camera``, ``mic``, ``touch``): set once at boot by
  cheap file-existence checks. They reflect whether the physical device is
  even reachable.
* **Pipeline health** (``voice``, ``vision``): driven by
  :mod:`app.core.safety.heartbeat_monitor`. The reducer clears the flag
  when ``system.degraded.entered`` arrives with a matching
  ``lost_capability``.

Probes are intentionally trivial so a developer workstation without any of
the peripherals still boots cleanly — they just come up ``False``.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Dict


# Capability names used across the codebase. Treat as authoritative keys.
CAMERA = "camera"
MIC = "mic"
TOUCH = "touch"
VOICE = "voice"
VISION = "vision"

ALL_CAPABILITIES = (CAMERA, MIC, TOUCH, VOICE, VISION)


@dataclass(frozen=True)
class CapabilitySet:
    camera: bool
    mic: bool
    touch: bool
    voice: bool
    vision: bool

    def as_dict(self) -> Dict[str, bool]:
        return {
            CAMERA: self.camera,
            MIC: self.mic,
            TOUCH: self.touch,
            VOICE: self.voice,
            VISION: self.vision,
        }


def probe_camera() -> bool:
    """True if any V4L2 video capture device is present."""
    return any(os.path.exists(p) for p in glob.glob("/dev/video*"))


def probe_mic() -> bool:
    """True if ALSA exposes at least one capture device."""
    # ``pcmC*D*c`` paths are ALSA capture devices; rely on presence only.
    return any(glob.glob("/dev/snd/pcmC*D*c"))


def probe_touch() -> bool:
    """True if any evdev input node advertises touch capability.

    Uses ``/proc/bus/input/devices`` when available because a bare
    ``/dev/input/event*`` existence test would light up every keyboard.
    Falls back to ``False`` if the proc entry cannot be read.
    """
    try:
        with open("/proc/bus/input/devices", "r", encoding="utf-8") as f:
            data = f.read()
    except OSError:
        return False
    # "Handlers=... mouse0 event0" or "H: Handlers=event0 touch"
    for line in data.splitlines():
        if "touchscreen" in line.lower() or "touch" in line.lower():
            return True
    return False


def probe_all() -> CapabilitySet:
    """Run hardware probes. Pipeline health starts optimistic (``True``).

    Pipeline flags (``voice``, ``vision``) assume the corresponding worker
    will publish a heartbeat shortly; :class:`HeartbeatMonitor` will flip
    them to ``False`` if that never arrives.
    """
    return CapabilitySet(
        camera=probe_camera(),
        mic=probe_mic(),
        touch=probe_touch(),
        voice=True,
        vision=True,
    )


def merge_into(state_caps: Dict[str, bool], probed: CapabilitySet) -> None:
    """Merge probe results into ``State.extended.capabilities`` in place."""
    for key, value in probed.as_dict().items():
        state_caps.setdefault(key, value)
        # Do not override an already-stored False (e.g., degraded flag)
        # just because the probe reports True again.
        if not state_caps[key] and value:
            # Keep the more pessimistic flag.
            continue
        if state_caps[key] and not value:
            state_caps[key] = False
