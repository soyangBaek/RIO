"""Gesture catalogue (Phase 2).

Defines the set of gestures RIO recognises and their metadata. The adapter
layer (:mod:`vision.gesture_detector`) produces :class:`GestureResult`
values with a ``gesture`` string; this catalogue is the canonical list of
allowed strings and documents what each should mean behaviourally.

MVP does not route these gestures anywhere (scenarios reach Phase 2); the
catalogue is present so the mapper (T-053) can be wired up without
further refactors when Phase 2 starts.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GestureSpec:
    name: str
    description: str
    confidence_min: float = 0.75


V_SIGN = GestureSpec(
    name="v_sign",
    description="Camera trigger — shutter intent equivalent",
)
WAVE = GestureSpec(
    name="wave",
    description="Friendly greeting — triggers happy oneshot",
)
FINGER_GUN = GestureSpec(
    name="finger_gun",
    description="Play signal — Phase 2 game entry cue",
)
HEAD_LEFT = GestureSpec(
    name="head_left",
    description="Directional input for games (Phase 2)",
)
HEAD_RIGHT = GestureSpec(
    name="head_right",
    description="Directional input for games (Phase 2)",
)

ALL_GESTURES = {
    g.name: g
    for g in (V_SIGN, WAVE, FINGER_GUN, HEAD_LEFT, HEAD_RIGHT)
}


def get(name: str) -> GestureSpec | None:
    return ALL_GESTURES.get(name)
