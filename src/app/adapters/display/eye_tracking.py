"""Eye / gaze rendering primitives.

Produces :class:`Drawable` instructions for the Core Face layer. The face
tracker (``adapters/vision/face_tracker``) publishes ``vision.face.moved``
with normalized ``center`` coordinates; this module interprets that center
as the user's position relative to the camera and shifts the pupils toward
it so RIO appears to look at the user.

Mood affects eye shape:
- :data:`Mood.INACTIVE` / :data:`Mood.SLEEPY` render closed eyes (lids).
- :data:`Mood.SURPRISED` renders enlarged pupils.
- :data:`Mood.HAPPY` renders slight arcs (curved eyes).
- Other moods use the default circular eye + pupil.

Coordinates in :class:`Drawable.payload` are normalized (0..1) per
``layers.py`` contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from ...core.state.models import Mood
from .layers import Composition, Drawable, Layer


@dataclass(frozen=True)
class EyeStyle:
    # Eye positions on the face (normalized screen coords).
    left_center: Tuple[float, float] = (0.35, 0.45)
    right_center: Tuple[float, float] = (0.65, 0.45)
    sclera_radius: float = 0.08
    pupil_radius: float = 0.035
    # Max distance (normalized) the pupil can shift from the sclera center.
    max_pupil_shift: float = 0.035


def compute_pupil_offset(
    face_center: Optional[Tuple[float, float]],
    max_shift: float,
) -> Tuple[float, float]:
    """Return the pupil offset for a given face center.

    ``face_center`` is ``(x, y)`` in normalized frame coords (origin at top
    left, 0..1 on both axes) — per architecture.md §6.4. When the face is at
    the centre the pupil is centered; offsets from the centre map linearly
    to pupil offsets clamped to ``max_shift``.
    """
    if face_center is None:
        return (0.0, 0.0)
    fx, fy = face_center
    dx = (fx - 0.5) * 2.0  # -1 .. 1
    dy = (fy - 0.5) * 2.0
    # Clamp to unit circle so diagonal gazes look natural.
    length = (dx * dx + dy * dy) ** 0.5
    if length > 1.0:
        dx /= length
        dy /= length
    return (dx * max_shift, dy * max_shift)


def make_eye_drawables(
    mood: Mood,
    face_center: Optional[Tuple[float, float]] = None,
    style: EyeStyle = EyeStyle(),
) -> List[Drawable]:
    """Build the per-eye :class:`Drawable` list for the Core Face layer."""
    # Closed-eye moods short-circuit: render lids regardless of face position.
    if mood in (Mood.INACTIVE, Mood.SLEEPY):
        return [
            Drawable(
                kind="eye_closed",
                payload={
                    "center": style.left_center,
                    "width": style.sclera_radius * 2,
                    "curve": "flat" if mood is Mood.INACTIVE else "arc_down",
                },
                z=0,
            ),
            Drawable(
                kind="eye_closed",
                payload={
                    "center": style.right_center,
                    "width": style.sclera_radius * 2,
                    "curve": "flat" if mood is Mood.INACTIVE else "arc_down",
                },
                z=0,
            ),
        ]

    dx, dy = compute_pupil_offset(face_center, style.max_pupil_shift)

    # Surprised: larger pupil. Happy: smaller pupil + arc.
    pupil_r = style.pupil_radius
    if mood is Mood.SURPRISED:
        pupil_r = style.pupil_radius * 1.4
    elif mood is Mood.HAPPY:
        pupil_r = style.pupil_radius * 0.85

    drawables: List[Drawable] = []
    for side_name, center in (
        ("left", style.left_center),
        ("right", style.right_center),
    ):
        cx, cy = center
        drawables.append(
            Drawable(
                kind="eye_sclera",
                payload={"center": (cx, cy), "radius": style.sclera_radius},
                z=0,
            )
        )
        drawables.append(
            Drawable(
                kind="eye_pupil",
                payload={
                    "center": (cx + dx, cy + dy),
                    "radius": pupil_r,
                    "side": side_name,
                },
                z=1,
            )
        )
        if mood is Mood.HAPPY:
            drawables.append(
                Drawable(
                    kind="eye_arc",
                    payload={"center": (cx, cy), "width": style.sclera_radius * 2},
                    z=2,
                )
            )
    return drawables


def push_eyes(
    composition: Composition,
    mood: Mood,
    face_center: Optional[Tuple[float, float]] = None,
    style: EyeStyle = EyeStyle(),
) -> None:
    """Clear the core face layer and push fresh eye drawables onto it."""
    composition.clear_layer(Layer.CORE_FACE)
    for d in make_eye_drawables(mood, face_center, style):
        composition.layer(Layer.CORE_FACE).add(d)
