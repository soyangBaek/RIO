"""Main display renderer — composes layers and drives a rendering backend.

Responsibilities:

* Own the active :class:`Composition` and the last known :class:`Scene` /
  face centre so repaints stay consistent frame to frame.
* Translate bus events into composition mutations — scene changes, face
  movement, oneshot overlays, HUD updates (weather, timers, STT hints).
* Delegate actual pixel output to a :class:`RendererBackend`.

Backends:

* :class:`NullBackend` — drops frames. Used on machines without a display;
  keeps tests and worker-less dev loops running.
* :class:`PygameBackend` — deferred initialisation of ``pygame``. Creates
  a windowed surface and interprets :class:`Drawable` primitives. If
  ``pygame`` is not importable the factory transparently falls back to
  :class:`NullBackend`.

Framework decision (per T-016 note): **pygame** is the default, chosen for
its maturity on Raspberry Pi, built-in SDL2 backend, and a thick mixer we
already rely on for :mod:`sfx`.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol, Tuple

from ...core.events import topics
from ...core.events.models import Event
from ...core.state.models import Mood, UI, Scene
from . import fallback_primitives
from .asset_loader import AssetLoader
from .eye_tracking import EyeStyle, push_eyes
from .hud import (
    set_degraded_badge,
    set_search_indicator,
    set_stt_hint,
    set_timers,
    set_weather,
)
from .layers import Composition, Drawable, Layer

_log = logging.getLogger(__name__)


class RendererBackend(Protocol):
    def begin_frame(self) -> None: ...
    def draw(self, layer: Layer, drawable: Drawable) -> None: ...
    def end_frame(self) -> None: ...
    def shutdown(self) -> None: ...


class NullBackend:
    def begin_frame(self) -> None: pass
    def draw(self, layer: Layer, drawable: Drawable) -> None: pass
    def end_frame(self) -> None: pass
    def shutdown(self) -> None: pass


class PygameBackend:
    """Pygame-backed renderer. Lazily initialised; falls back gracefully."""

    def __init__(self, width_px: int = 800, height_px: int = 480,
                 title: str = "RIO") -> None:
        self._w = width_px
        self._h = height_px
        self._pg = None  # type: ignore[assignment]
        self._screen = None
        try:
            import pygame  # type: ignore
            pygame.display.init()
            pygame.font.init()
            self._pg = pygame
            self._screen = pygame.display.set_mode((width_px, height_px))
            pygame.display.set_caption(title)
            self._font = pygame.font.SysFont(None, 24)
            self._font_xl = pygame.font.SysFont(None, 96)
        except Exception as e:  # pragma: no cover
            _log.warning("pygame unavailable (%s); rendering disabled", e)

    def begin_frame(self) -> None:
        if self._pg is None:
            return
        self._screen.fill((10, 10, 16))

    def _nx(self, v: float) -> int:
        return int(round(v * self._w))

    def _ny(self, v: float) -> int:
        return int(round(v * self._h))

    def draw(self, layer: Layer, drawable: Drawable) -> None:  # pragma: no cover - needs display
        if self._pg is None:
            return
        kind = drawable.kind
        p = drawable.payload
        color = p.get("color", (230, 230, 240))
        try:
            if kind == "rect":
                x, y, w, h = p["bounds"]
                rect = (self._nx(x), self._ny(y), self._nx(w), self._ny(h))
                self._pg.draw.rect(self._screen, color, rect)
            elif kind == "rect_label":
                x, y, w, h = p["bounds"]
                rect = (self._nx(x), self._ny(y), self._nx(w), self._ny(h))
                self._pg.draw.rect(self._screen, color, rect)
                if p.get("text"):
                    surf = self._font.render(p["text"], True, p.get("text_color", (240, 240, 240)))
                    self._screen.blit(surf, (self._nx(x) + 6, self._ny(y) + 4))
            elif kind == "eye_sclera":
                cx, cy = p["center"]
                r = max(2, self._nx(p["radius"]))
                self._pg.draw.circle(self._screen, (240, 240, 245),
                                     (self._nx(cx), self._ny(cy)), r)
            elif kind == "eye_pupil":
                cx, cy = p["center"]
                r = max(2, self._nx(p["radius"]))
                self._pg.draw.circle(self._screen, (20, 20, 30),
                                     (self._nx(cx), self._ny(cy)), r)
            elif kind == "eye_closed":
                cx, cy = p["center"]
                w = self._nx(p["width"])
                self._pg.draw.line(self._screen, (240, 240, 245),
                                   (self._nx(cx) - w // 2, self._ny(cy)),
                                   (self._nx(cx) + w // 2, self._ny(cy)), 3)
            elif kind == "eye_arc":
                cx, cy = p["center"]
                w = self._nx(p["width"])
                bounds = (self._nx(cx) - w // 2, self._ny(cy) - 4, w, 12)
                self._pg.draw.arc(self._screen, (240, 240, 245), bounds, 3.14, 0, 3)
            elif kind == "mouth":
                cx, cy = p["center"]
                w = self._nx(p["width"])
                bounds = (self._nx(cx) - w // 2, self._ny(cy) - 8, w, 24)
                self._pg.draw.arc(self._screen, p.get("color", (30, 30, 40)),
                                  bounds, 3.14, 0, 3)
            elif kind == "ripple":
                cx, cy = p["center"]
                r = max(4, self._nx(p.get("radius", 0.05)))
                c = p.get("color", (255, 255, 255))
                self._pg.draw.circle(self._screen, c, (self._nx(cx), self._ny(cy)), r, 3)
                self._pg.draw.circle(self._screen, c, (self._nx(cx), self._ny(cy)), r // 2)
            elif kind == "heart":
                cx, cy = p["center"]
                r = max(4, self._nx(p.get("radius", 0.06)))
                c = p.get("color", (255, 120, 160))
                px, py = self._nx(cx), self._ny(cy)
                # simple heart: two circles + triangle
                hr = r // 2
                self._pg.draw.circle(self._screen, c, (px - hr, py - hr), hr)
                self._pg.draw.circle(self._screen, c, (px + hr, py - hr), hr)
                self._pg.draw.polygon(self._screen, c, [
                    (px - r, py - hr // 2), (px + r, py - hr // 2), (px, py + r),
                ])
            elif kind in ("text", "badge", "spinner", "weather", "timer_list"):
                text = p.get("text") or kind
                size_key = p.get("size", "sm")
                font = self._font_xl if size_key == "xl" else self._font
                surf = font.render(str(text), True, color)
                self._screen.blit(surf, (self._nx(p.get("x", 0.5)),
                                         self._ny(p.get("y", 0.5))))
        except Exception:
            _log.exception("draw failed for %s", kind)

    def end_frame(self) -> None:
        if self._pg is None:
            return
        self._pg.display.flip()

    def shutdown(self) -> None:
        if self._pg is None:
            return
        try:
            self._pg.display.quit()
        except Exception:
            pass


def make_backend(width_px: int = 800, height_px: int = 480) -> RendererBackend:
    """Try PygameBackend; if pygame unavailable, fall back to NullBackend."""
    try:
        pg = PygameBackend(width_px, height_px)
        if pg._pg is not None:
            return pg
    except Exception:  # pragma: no cover
        pass
    return NullBackend()


class Renderer:
    def __init__(
        self,
        loader: AssetLoader,
        backend: Optional[RendererBackend] = None,
        eye_style: EyeStyle = EyeStyle(),
    ) -> None:
        self._loader = loader
        self._backend = backend if backend is not None else NullBackend()
        self._eye_style = eye_style
        self._composition = Composition()
        self._scene: Optional[Scene] = None
        self._face_center: Optional[Tuple[float, float]] = None
        self._rebuild_core()

    # -- state hooks --------------------------------------------------------
    @property
    def composition(self) -> Composition:
        return self._composition

    def set_scene(self, scene: Scene) -> None:
        self._scene = scene
        self._rebuild_core()

    def set_face_center(self, center: Optional[Tuple[float, float]]) -> None:
        self._face_center = center
        self._rebuild_core()

    # -- event handler ------------------------------------------------------
    def on_event(self, event: Event) -> None:
        """Plug into ``router.subscribe_all(...)``."""
        topic = event.topic
        if topic == topics.SCENE_DERIVED:
            mood = Mood(event.payload["mood"])
            ui = UI(event.payload["ui"])
            self.set_scene(Scene(mood=mood, ui=ui))
        elif topic in (topics.VISION_FACE_DETECTED, topics.VISION_FACE_MOVED):
            center = event.payload.get("center")
            if isinstance(center, (list, tuple)) and len(center) == 2:
                self.set_face_center((float(center[0]), float(center[1])))
        elif topic == topics.VISION_FACE_LOST:
            self.set_face_center(None)
        elif topic == topics.WEATHER_RESULT:
            data = event.payload.get("data") or {}
            set_weather(
                self._composition,
                icon=data.get("icon"),
                temperature_c=data.get("temperature_c"),
                condition=data.get("condition"),
            )
        elif topic == topics.TOUCH_TAP_DETECTED:
            x = event.payload.get("x")
            y = event.payload.get("y")
            if x is not None and y is not None:
                self._show_touch_ripple(float(x), float(y), "tap")
        elif topic == topics.TOUCH_STROKE_DETECTED:
            path = event.payload.get("path")
            if path and len(path) > 0:
                last = path[-1]
                self._show_touch_ripple(float(last[0]), float(last[1]), "stroke")
        elif topic == topics.SYSTEM_DEGRADED_ENTERED and not event.payload.get("recovered"):
            cap = event.payload.get("lost_capability")
            if cap:
                set_degraded_badge(self._composition, [cap])

    # -- composition rebuild -----------------------------------------------
    def _rebuild_core(self) -> None:
        scene = self._scene
        mood = scene.mood if scene is not None else Mood.INACTIVE
        ui = scene.ui if scene is not None else UI.NORMAL_FACE

        # Try to resolve a full-face asset first; if present, skip primitives.
        face_asset = self._loader.expression(mood.value)
        if face_asset is not None:
            self._composition.clear_layer(Layer.CORE_FACE)
            self._composition.layer(Layer.CORE_FACE).add(
                Drawable(
                    kind="image",
                    payload={
                        "path": str(face_asset),
                        "bounds": (0.1, 0.1, 0.8, 0.8),
                    },
                    z=0,
                )
            )
            # Eyes still overlay the image so gaze tracking works.
            for d in self._eye_drawables(mood):
                self._composition.layer(Layer.CORE_FACE).add(d)
        else:
            fallback_primitives.apply_to_composition(self._composition, mood, ui)
            for d in self._eye_drawables(mood):
                self._composition.layer(Layer.CORE_FACE).add(d)

        set_search_indicator(self._composition, active=False)

    def _eye_drawables(self, mood: Mood):
        from .eye_tracking import make_eye_drawables
        return make_eye_drawables(mood, self._face_center, self._eye_style)

    # -- touch feedback ------------------------------------------------------
    _RIPPLE_SLOT = "touch_ripple"
    _RIPPLE_DURATION_S = 0.4

    def _show_touch_ripple(self, x: float, y: float, kind: str) -> None:
        """Push a brief ripple/heart drawable on the Action Overlay layer."""
        import time as _time
        self._ripple_expire = _time.monotonic() + self._RIPPLE_DURATION_S
        overlay = self._composition.layer(Layer.ACTION_OVERLAY)
        # Remove previous ripple if still present.
        overlay.drawables[:] = [
            d for d in overlay.drawables
            if d.payload.get("slot") != self._RIPPLE_SLOT
        ]
        if kind == "stroke":
            overlay.add(Drawable(
                kind="heart",
                payload={"center": (x, y), "radius": 0.06, "slot": self._RIPPLE_SLOT,
                         "color": (255, 120, 160)},
                z=50,
            ))
        else:
            overlay.add(Drawable(
                kind="ripple",
                payload={"center": (x, y), "radius": 0.05, "slot": self._RIPPLE_SLOT,
                         "color": (255, 255, 255)},
                z=50,
            ))

    def _expire_ripple(self) -> None:
        expire = getattr(self, "_ripple_expire", None)
        if expire is None:
            return
        import time as _time
        if _time.monotonic() >= expire:
            overlay = self._composition.layer(Layer.ACTION_OVERLAY)
            overlay.drawables[:] = [
                d for d in overlay.drawables
                if d.payload.get("slot") != self._RIPPLE_SLOT
            ]
            self._ripple_expire = None

    # -- frame output -------------------------------------------------------
    def render_frame(self) -> None:
        self._expire_ripple()
        self._backend.begin_frame()
        for layer, drawables in self._composition.draw_order():
            for d in drawables:
                self._backend.draw(layer, d)
        self._backend.end_frame()

    def shutdown(self) -> None:
        self._backend.shutdown()
