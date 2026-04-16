"""System HUD drawables — Layer 3 (chrome around the face).

Each function appends or replaces a logical HUD element on the composition.
Element identity is kept explicit via a ``slot`` payload key so the renderer
can redraw or clear individual widgets without rebuilding the whole layer.
Layouts use the normalized-coord contract from ``layers.py``.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .layers import Composition, Drawable, Layer


# Slot names (use strings rather than enum; HUD is extended frequently).
SLOT_STT = "stt"
SLOT_COUNTDOWN = "countdown"
SLOT_WEATHER = "weather"
SLOT_TIMER = "timer"
SLOT_BADGE_DEGRADED = "badge_degraded"
SLOT_SEARCH = "search_indicator"


def _remove_slot(composition: Composition, slot: str) -> None:
    buf = composition.layer(Layer.SYSTEM_HUD)
    buf.drawables[:] = [d for d in buf.drawables if d.payload.get("slot") != slot]


def clear_slot(composition: Composition, slot: str) -> None:
    _remove_slot(composition, slot)


def set_stt_hint(composition: Composition, text: Optional[str]) -> None:
    """Show the latest STT transcript (partial or final). Pass ``None`` to hide."""
    _remove_slot(composition, SLOT_STT)
    if not text:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="text",
            payload={
                "slot": SLOT_STT,
                "x": 0.5,
                "y": 0.92,
                "text": text,
                "anchor": "center-bottom",
                "size": "sm",
            },
            z=10,
        )
    )


def set_countdown(composition: Composition, seconds_left: Optional[int]) -> None:
    """Big centre-screen countdown number. ``None`` hides the element."""
    _remove_slot(composition, SLOT_COUNTDOWN)
    if seconds_left is None:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="text",
            payload={
                "slot": SLOT_COUNTDOWN,
                "x": 0.5,
                "y": 0.5,
                "text": str(seconds_left),
                "anchor": "center",
                "size": "xl",
            },
            z=20,
        )
    )


def set_weather(
    composition: Composition,
    icon: Optional[str] = None,
    temperature_c: Optional[float] = None,
    condition: Optional[str] = None,
) -> None:
    """Top-right weather widget. Pass all ``None`` to clear."""
    _remove_slot(composition, SLOT_WEATHER)
    if icon is None and temperature_c is None and condition is None:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="weather",
            payload={
                "slot": SLOT_WEATHER,
                "x": 0.92,
                "y": 0.08,
                "icon": icon,
                "temperature_c": temperature_c,
                "condition": condition,
                "anchor": "right-top",
            },
            z=5,
        )
    )


def set_timers(composition: Composition, timers: Iterable[dict]) -> None:
    """List of active timers (shown as stacked rows top-left).

    Each element of ``timers`` is a dict with at least ``label`` and
    ``seconds_left`` keys. Empty iterable clears the slot.
    """
    _remove_slot(composition, SLOT_TIMER)
    rows = list(timers)
    if not rows:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="timer_list",
            payload={
                "slot": SLOT_TIMER,
                "x": 0.02,
                "y": 0.08,
                "rows": rows,
                "anchor": "left-top",
            },
            z=5,
        )
    )


def set_degraded_badge(composition: Composition, lost_capabilities: Iterable[str]) -> None:
    """Small red badge listing lost capabilities (bottom-left)."""
    _remove_slot(composition, SLOT_BADGE_DEGRADED)
    caps = list(lost_capabilities)
    if not caps:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="badge",
            payload={
                "slot": SLOT_BADGE_DEGRADED,
                "x": 0.02,
                "y": 0.95,
                "text": "degraded: " + ", ".join(caps),
                "anchor": "left-bottom",
                "color": "warn",
            },
            z=8,
        )
    )


def set_search_indicator(composition: Composition, active: bool) -> None:
    """Spinner / dotted circle used by ``is_searching_for_user`` state."""
    _remove_slot(composition, SLOT_SEARCH)
    if not active:
        return
    composition.layer(Layer.SYSTEM_HUD).add(
        Drawable(
            kind="spinner",
            payload={
                "slot": SLOT_SEARCH,
                "x": 0.5,
                "y": 0.82,
                "anchor": "center",
            },
            z=6,
        )
    )
