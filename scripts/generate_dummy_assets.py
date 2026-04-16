#!/usr/bin/env python3
"""Generate dummy placeholder assets under ``assets/_dummy/``.

Produces PNG images (expressions, UI icons, 2-frame animations) with Pillow
and WAV sounds with the stdlib ``wave`` module. The asset loader
(``app.adapters.display.asset_loader``) prefers real assets under the
canonical directories but falls back to ``assets/_dummy/`` — running this
script once is enough to give the renderer something visible during
development.

Run::

    python3 scripts/generate_dummy_assets.py

Outputs go to ``<repo>/assets/_dummy/{expressions,sounds,ui,animations}``.
Existing files are overwritten.
"""
from __future__ import annotations

import math
import os
import struct
import sys
import wave
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:  # pragma: no cover
    print("Pillow is required. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[1]
DUMMY = ROOT / "assets" / "_dummy"


# -- Expressions -------------------------------------------------------------
# Each expression is a simple PNG: colored circle + text label.
EXPRESSIONS = {
    # Keyed by Mood.value — matches AssetLoader.expression(mood.value).
    "calm": (90, 180, 240),
    "attentive": (240, 210, 90),
    "sleepy": (140, 150, 170),
    "alert": (240, 80, 80),
    "surprised": (240, 120, 220),
    "happy": (100, 220, 140),
    "confused": (235, 150, 80),
    "inactive": (40, 40, 50),
}
EXPR_SIZE = (320, 240)


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def write_expressions(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font(24)
    for name, color in EXPRESSIONS.items():
        img = Image.new("RGBA", EXPR_SIZE, (20, 20, 28, 255))
        draw = ImageDraw.Draw(img)
        cx, cy = EXPR_SIZE[0] // 2, EXPR_SIZE[1] // 2
        r = 80
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (255,))
        try:
            w, h = draw.textbbox((0, 0), name, font=font)[2:]
        except AttributeError:
            w, h = draw.textsize(name, font=font)
        draw.text((cx - w // 2, cy + r + 6), name, fill=(230, 230, 230), font=font)
        img.save(out_dir / f"{name}.png")


# -- UI icons ---------------------------------------------------------------
UI_ICONS = {
    "weather_sunny": ((250, 200, 60), "sun"),
    "weather_cloudy": ((180, 180, 200), "cloud"),
    "weather_rain": ((90, 140, 220), "rain"),
    "timer": ((220, 100, 100), "timer"),
    "game_button": ((100, 200, 200), "game"),
    "badge_degraded": ((255, 80, 80), "!"),
}
UI_SIZE = (64, 64)


def write_ui(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font(14)
    for name, (color, label) in UI_ICONS.items():
        img = Image.new("RGBA", UI_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((4, 4, UI_SIZE[0] - 5, UI_SIZE[1] - 5), fill=color + (255,))
        try:
            w, h = draw.textbbox((0, 0), label, font=font)[2:]
        except AttributeError:
            w, h = draw.textsize(label, font=font)
        draw.text(((UI_SIZE[0] - w) // 2, (UI_SIZE[1] - h) // 2), label,
                  fill=(20, 20, 30), font=font)
        img.save(out_dir / f"{name}.png")


# -- Animations (2-frame sprites) -------------------------------------------
ANIMATIONS = {
    "dream": [(50, 60, 120), (80, 90, 160)],
    "dance": [(220, 120, 200), (140, 200, 200)],
    "welcome_wave": [(100, 240, 140), (200, 240, 140)],
    "overlay_flash": [(255, 255, 255), (255, 200, 200)],
}
ANIM_SIZE = (128, 128)


def write_animations(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, frames in ANIMATIONS.items():
        for i, color in enumerate(frames):
            img = Image.new("RGBA", ANIM_SIZE, (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            r = 40 + i * 8
            cx, cy = ANIM_SIZE[0] // 2, ANIM_SIZE[1] // 2
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (220,))
            img.save(out_dir / f"{name}_{i}.png")


# -- Sounds -----------------------------------------------------------------
SOUNDS = {
    "shutter": (600, 0.15),
    "success": (880, 0.25),
    "fail": (220, 0.35),
    "startle": (1200, 0.1),
    "snore": (110, 0.6),
    "satisfaction": (660, 0.4),
}
SR = 16_000


def _write_beep(path: Path, frequency_hz: float, duration_s: float) -> None:
    n = int(SR * duration_s)
    # simple sine with quick fade-in/out to avoid clicks
    buf = bytearray()
    for i in range(n):
        env = 1.0
        fade = int(SR * 0.01)
        if i < fade:
            env = i / fade
        elif i > n - fade:
            env = (n - i) / fade
        sample = int(32767 * 0.25 * env * math.sin(2 * math.pi * frequency_hz * i / SR))
        buf += struct.pack("<h", sample)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(buf))


def write_sounds(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (freq, dur) in SOUNDS.items():
        _write_beep(out_dir / f"{name}.wav", freq, dur)


# -- Entry point ------------------------------------------------------------
def main() -> int:
    for sub in ("expressions", "sounds", "ui", "animations"):
        (DUMMY / sub).mkdir(parents=True, exist_ok=True)
    write_expressions(DUMMY / "expressions")
    write_ui(DUMMY / "ui")
    write_animations(DUMMY / "animations")
    write_sounds(DUMMY / "sounds")
    print(f"dummy assets written to {DUMMY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
