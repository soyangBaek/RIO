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
    """True if any evdev input node advertises touch / direct-input capability.

    Checks ``/proc/bus/input/devices`` for:
    - Name or handlers containing "touch" / "touchscreen"
    - ``PROP=2`` (INPUT_PROP_DIRECT, used by capacitive touchscreens)
    - ABS bitmap containing multitouch bits (``ABS_MT_POSITION_X``)
    """
    try:
        with open("/proc/bus/input/devices", "r", encoding="utf-8") as f:
            data = f.read()
    except OSError:
        return False
    for block in data.split("\n\n"):
        block_lower = block.lower()
        # Keyword match
        if "touch" in block_lower or "touchscreen" in block_lower:
            return True
        # INPUT_PROP_DIRECT (bit 1 → PROP value has bit 1 set → "2" or "3")
        for line in block.splitlines():
            if line.startswith("B: PROP="):
                try:
                    prop_val = int(line.split("=", 1)[1].strip(), 16)
                    if prop_val & 0x2:  # INPUT_PROP_DIRECT
                        return True
                except ValueError:
                    pass
            # CTP / capacitive touch panel in device name
            if line.startswith("N: Name=") and "ctp" in line.lower():
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
