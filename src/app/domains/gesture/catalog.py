from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GestureDefinition:
    name: str
    description: str


GESTURE_CATALOG: dict[str, GestureDefinition] = {
    "v_sign": GestureDefinition("v_sign", "V-sign hand gesture that triggers a photo capture."),
    "wave": GestureDefinition("wave", "Waving hand used as a greeting cue."),
    "finger_gun": GestureDefinition("finger_gun", "Finger-gun pose for the 빵야 interaction."),
    "head_left": GestureDefinition("head_left", "Head turned to the left."),
    "head_right": GestureDefinition("head_right", "Head turned to the right."),
}
