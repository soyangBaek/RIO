"""Gesture → intent mapping (Phase 2).

Given a ``vision.gesture.detected`` event, decide which canonical intent
(if any) should be raised. For Phase 2 only a handful of gestures map:

- ``v_sign`` → ``camera.capture``
- ``wave``   → (no intent; handled as happy oneshot upstream)
- ``finger_gun`` / head direction → Phase 2 game features

For MVP (Phase 1) the mapping table is empty — the function returns
``None`` for every gesture so current behaviour is unchanged.
"""
from __future__ import annotations

from typing import Optional

# Phase 2 will populate this map. Keeping the keys here documents the
# eventual contract even while the values are unset.
_GESTURE_TO_INTENT: dict[str, str] = {
    # "v_sign": "camera.capture",
    # "finger_gun": "ui.game_mode.enter",
}


def gesture_to_intent(gesture_name: str) -> Optional[str]:
    return _GESTURE_TO_INTENT.get(gesture_name)
