"""Framework-agnostic 3-layer composition model.

PRD §UI and state-machine.md §6 describe the display as a stack of three
layers:

1. **Core Face** — the base expression: eyes, mouth, general mood colouring.
2. **Action Overlay** — time-bounded animations rendered on top of the face
   (countdowns, flash-on-success, particle effects, oneshot overlays).
3. **System HUD** — chrome around the edges: text, weather icons, timers,
   badges, STT hints.

This module owns the *contract* between producers (eye_tracking, hud,
fallback_primitives) and the renderer (T-019). It intentionally does **not**
touch PyGame/Pillow/Tkinter — the renderer picks a backend and interprets
the :class:`Drawable` payloads. This keeps the compositor unit-testable and
lets the fallback renderer reuse the same surface (T-079).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Iterable, Iterator, List, Tuple


class Layer(IntEnum):
    CORE_FACE = 1
    ACTION_OVERLAY = 2
    SYSTEM_HUD = 3


@dataclass
class Drawable:
    """A render instruction interpreted by the active backend.

    ``kind`` identifies the primitive (e.g. ``"image"``, ``"text"``,
    ``"eye"``, ``"rect"``) and ``payload`` carries backend-neutral fields.
    Coordinates are in normalized screen space ``(0.0 .. 1.0)`` so the
    compositor is resolution-agnostic. ``z`` orders drawables **within** a
    single layer; layers themselves render in :class:`Layer` enum order.
    """
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    z: int = 0


@dataclass
class LayerBuffer:
    layer: Layer
    drawables: List[Drawable] = field(default_factory=list)

    def clear(self) -> None:
        self.drawables.clear()

    def add(self, drawable: Drawable) -> None:
        self.drawables.append(drawable)

    def extend(self, drawables: Iterable[Drawable]) -> None:
        self.drawables.extend(drawables)

    def sorted(self) -> List[Drawable]:
        return sorted(self.drawables, key=lambda d: d.z)


class Composition:
    """Holds the current frame — one :class:`LayerBuffer` per :class:`Layer`."""

    def __init__(self) -> None:
        self._layers: Dict[Layer, LayerBuffer] = {
            layer: LayerBuffer(layer) for layer in Layer
        }

    def layer(self, layer: Layer) -> LayerBuffer:
        return self._layers[layer]

    def clear_layer(self, layer: Layer) -> None:
        self._layers[layer].clear()

    def clear_all(self) -> None:
        for buffer in self._layers.values():
            buffer.clear()

    def draw_order(self) -> Iterator[Tuple[Layer, List[Drawable]]]:
        """Yield ``(layer, drawables)`` in the correct paint order."""
        for layer in Layer:  # IntEnum iterates in ascending numeric order
            yield layer, self._layers[layer].sorted()

    def snapshot(self) -> Dict[Layer, List[Drawable]]:
        """Return a dict copy of drawables keyed by layer (useful for tests)."""
        return {layer: list(buf.sorted()) for layer, buf in self._layers.items()}
