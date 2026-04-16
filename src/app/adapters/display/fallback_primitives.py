"""Fallback primitive drawables used when no asset resolves.

``asset_loader`` returns ``None`` when neither the production nor ``_dummy``
asset exists. The renderer can then call into this module to build a
recognisable face + HUD using only shapes and colours, so the system still
runs on a bare checkout. The functions emit backend-neutral
:class:`Drawable` objects identical in structure to the ones produced by
:mod:`eye_tracking` and :mod:`hud`, so the renderer does not need a
separate code path.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...core.state.models import Mood, UI
from .layers import Composition, Drawable, Layer

# RGB triplets (0..255) that the renderer can interpret as fill colours.
MOOD_COLORS: Dict[Mood, Tuple[int, int, int]] = {
    Mood.CALM: (90, 180, 240),
    Mood.ATTENTIVE: (240, 210, 90),
    Mood.SLEEPY: (140, 150, 170),
    Mood.ALERT: (240, 80, 80),
    Mood.SURPRISED: (240, 120, 220),
    Mood.HAPPY: (100, 220, 140),
    Mood.CONFUSED: (235, 150, 80),
    Mood.INACTIVE: (40, 40, 50),
}


def mood_to_color(mood: Mood) -> Tuple[int, int, int]:
    return MOOD_COLORS[mood]


def build_background(mood: Mood) -> Drawable:
    """Solid-fill background drawable sized to the whole screen."""
    return Drawable(
        kind="rect",
        payload={
            "bounds": (0.0, 0.0, 1.0, 1.0),
            "color": mood_to_color(mood),
            "alpha": 1.0,
            "slot": "bg",
        },
        z=-100,  # always behind everything else in its layer
    )


def build_mouth(mood: Mood) -> Drawable:
    """A simple mouth shape that reflects the mood."""
    if mood is Mood.HAPPY or mood is Mood.SURPRISED:
        shape = "arc_up"
    elif mood is Mood.CONFUSED or mood is Mood.ALERT:
        shape = "wave"
    elif mood is Mood.SLEEPY or mood is Mood.INACTIVE:
        shape = "flat"
    else:
        shape = "arc_down"
    return Drawable(
        kind="mouth",
        payload={
            "center": (0.5, 0.68),
            "width": 0.24,
            "shape": shape,
            "color": (30, 30, 40),
        },
        z=3,
    )


def build_ui_placeholder(ui: UI) -> Optional[Drawable]:
    """Primitive backdrop for a UI slot when its icon assets are missing."""
    label = ui.value.replace("_", " ").title()
    return Drawable(
        kind="rect_label",
        payload={
            "bounds": (0.02, 0.02, 0.25, 0.08),
            "color": (30, 30, 40),
            "text": label,
            "text_color": (230, 230, 240),
            "slot": f"primitive_ui_{ui.value}",
        },
        z=0,
    )


def apply_to_composition(
    composition: Composition,
    mood: Mood,
    ui: UI,
) -> None:
    """Push a minimal-but-recognisable face + UI into ``composition``.

    This replaces the Core Face **background** drawable and adds a mouth; the
    caller is still responsible for eye drawables (``eye_tracking.push_eyes``)
    which already handle mood-aware shapes.
    """
    core = composition.layer(Layer.CORE_FACE)
    # Remove any prior background/mouth we placed.
    core.drawables[:] = [
        d for d in core.drawables
        if d.payload.get("slot") not in {"bg", None}
        or d.kind not in {"rect", "mouth"}
    ]
    core.add(build_background(mood))
    core.add(build_mouth(mood))

    placeholder = build_ui_placeholder(ui)
    if placeholder is not None:
        hud = composition.layer(Layer.SYSTEM_HUD)
        hud.drawables[:] = [
            d for d in hud.drawables
            if d.payload.get("slot") != placeholder.payload["slot"]
        ]
        hud.add(placeholder)
