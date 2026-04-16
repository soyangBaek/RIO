#!/usr/bin/env python3
"""Standalone touchscreen debug utility.

Opens the evdev touch device directly and draws coloured circles where
fingers touch. Runs independently from ``app.main`` — use it to verify the
touchscreen works before testing RIO's gesture mapper.

Run::

    python3 scripts/preview_touch.py                  # auto-detect device
    python3 scripts/preview_touch.py --device /dev/input/event0

Controls:
    q / ESC     quit
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


@dataclass
class Finger:
    x: float = 0.0
    y: float = 0.0
    active: bool = False
    color: tuple = (0, 255, 0)


SLOT_COLORS = [
    (0, 255, 0), (255, 100, 100), (100, 100, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (200, 200, 200), (255, 140, 0),
    (140, 255, 0), (0, 140, 255),
]


def find_touch_device() -> Optional[str]:
    from evdev import InputDevice, list_devices, ecodes  # type: ignore

    for path in list_devices():
        d = InputDevice(path)
        caps = d.capabilities()
        if ecodes.EV_ABS not in caps:
            continue
        abs_codes = [code for code, _ in caps[ecodes.EV_ABS]]
        if ecodes.ABS_MT_POSITION_X in abs_codes:
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RIO touch preview")
    parser.add_argument("--device", type=str, default=None, help="evdev device path")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args(argv)

    try:
        from evdev import InputDevice, ecodes  # type: ignore
    except ImportError:
        _fail("evdev required: pip install evdev")

    try:
        import pygame  # type: ignore
    except ImportError:
        _fail("pygame required: pip install pygame")

    device_path = args.device or find_touch_device()
    if device_path is None:
        _fail("no touch device found; pass --device manually")

    dev = InputDevice(device_path)
    caps = dev.capabilities()
    abs_caps = {}
    if ecodes.EV_ABS in caps:
        for code, absinfo in caps[ecodes.EV_ABS]:
            abs_caps[code] = absinfo

    # Axis ranges
    use_mt = ecodes.ABS_MT_POSITION_X in abs_caps
    if use_mt:
        x_info = abs_caps[ecodes.ABS_MT_POSITION_X]
        y_info = abs_caps[ecodes.ABS_MT_POSITION_Y]
    else:
        x_info = abs_caps.get(ecodes.ABS_X)
        y_info = abs_caps.get(ecodes.ABS_Y)
        if not x_info or not y_info:
            _fail("device has no X/Y axes")

    x_min, x_range = float(x_info.min), float(x_info.max - x_info.min) or 1.0
    y_min, y_range = float(y_info.min), float(y_info.max - y_info.min) or 1.0

    print(f"device: {device_path} ({dev.name})")
    print(f"mt={use_mt}  x=[{x_info.min}..{x_info.max}]  y=[{y_info.min}..{y_info.max}]")

    W, H = args.width, args.height
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(f"Touch preview — {dev.name}")
    font = pygame.font.SysFont(None, 24)
    clock = pygame.time.Clock()

    # Grab the device so events don't leak to the desktop
    try:
        dev.grab()
        grabbed = True
    except Exception:
        grabbed = False
        print("WARN: could not grab device (events may also go to desktop)")

    fingers: Dict[int, Finger] = {}
    current_slot = 0
    raw_x = 0.0
    raw_y = 0.0
    btn_pressed = False
    touch_log: list[str] = []

    running = True
    try:
        while running:
            # pygame events (quit / keyboard)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        running = False

            # evdev: read all available events (non-blocking)
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_ABS:
                        if use_mt:
                            if event.code == ecodes.ABS_MT_SLOT:
                                current_slot = event.value
                            elif event.code == ecodes.ABS_MT_POSITION_X:
                                f = fingers.setdefault(current_slot, Finger(color=SLOT_COLORS[current_slot % len(SLOT_COLORS)]))
                                f.x = (event.value - x_min) / x_range
                            elif event.code == ecodes.ABS_MT_POSITION_Y:
                                f = fingers.setdefault(current_slot, Finger(color=SLOT_COLORS[current_slot % len(SLOT_COLORS)]))
                                f.y = (event.value - y_min) / y_range
                            elif event.code == ecodes.ABS_MT_TRACKING_ID:
                                f = fingers.setdefault(current_slot, Finger(color=SLOT_COLORS[current_slot % len(SLOT_COLORS)]))
                                if event.value >= 0:
                                    f.active = True
                                else:
                                    f.active = False
                        else:
                            if event.code == ecodes.ABS_X:
                                raw_x = (event.value - x_min) / x_range
                            elif event.code == ecodes.ABS_Y:
                                raw_y = (event.value - y_min) / y_range
                    elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                        btn_pressed = bool(event.value)
                        if not use_mt:
                            f = fingers.setdefault(0, Finger(color=SLOT_COLORS[0]))
                            f.x = raw_x
                            f.y = raw_y
                            f.active = btn_pressed
                    elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                        if not use_mt:
                            f = fingers.setdefault(0, Finger(color=SLOT_COLORS[0]))
                            f.x = raw_x
                            f.y = raw_y
            except BlockingIOError:
                pass  # no pending events

            # --- draw ---
            screen.fill((20, 20, 28))

            # crosshair grid
            for i in range(1, 10):
                frac = i / 10.0
                pygame.draw.line(screen, (40, 40, 50), (int(frac * W), 0), (int(frac * W), H), 1)
                pygame.draw.line(screen, (40, 40, 50), (0, int(frac * H)), (W, int(frac * H)), 1)

            # fingers
            active_count = 0
            for slot, fg in fingers.items():
                px, py = int(fg.x * W), int(fg.y * H)
                if fg.active:
                    active_count += 1
                    pygame.draw.circle(screen, fg.color, (px, py), 24)
                    pygame.draw.circle(screen, (255, 255, 255), (px, py), 26, 2)
                    label = f"slot={slot} ({fg.x:.3f}, {fg.y:.3f})"
                    surf = font.render(label, True, (255, 255, 255))
                    screen.blit(surf, (px + 30, py - 10))
                else:
                    # ghost of last position
                    pygame.draw.circle(screen, (60, 60, 70), (px, py), 16, 1)

            # HUD
            hud = f"device={dev.name}  mt={use_mt}  active={active_count}  (q: quit)"
            screen.blit(font.render(hud, True, (0, 255, 255)), (10, 10))

            pygame.display.flip()
            clock.tick(60)
    finally:
        if grabbed:
            try:
                dev.ungrab()
            except Exception:
                pass
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
