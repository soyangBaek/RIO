"""OpenCV 기반 RIO 얼굴 프리뷰 창.

Phase 1: live_interaction_test.py 의 face 렌더 파이프라인을 재사용 가능한 모듈로 추출.
live_interaction_test.py 는 여전히 자체 복사본을 쓰고 있고(Phase 2 에서 합류 예정),
지금 당장은 scripts/run_rio_app.py --preview 에서 쓰기 위한 독립 구현.

디버그 사이드바/카메라 인셋/HTTP 스냅샷은 이 모듈에 없다(테스트 하네스 영역).
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from src.app.core.config import REPO_ROOT
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ActivityState, ContextState

if TYPE_CHECKING:
    from src.app.main import RioOrchestrator


# ── 상수 ────────────────────────────────────────────────────────────


def rgb(red: int, green: int, blue: int) -> tuple[int, int, int]:
    # OpenCV 는 BGR 이므로 R/B 를 swap 해서 반환한다.
    return (blue, green, red)


ASSET_FACE_BG = rgb(201, 228, 195)
RECENT_ACTION_HOLD_MS = 1500

_FACE_ASSET_TRANSITION: dict[str, Any] = {"current": None, "previous": None, "changed_at": 0.0}

LISTENING_SPRITE_PATH = "assets/animations/listening_sprite.png"
LISTENING_SPRITE_FRAMES = 24
LISTENING_SPRITE_FPS = 24
LISTENING_SPRITE_SCALE = 0.7
LISTENING_MARGIN_PX = 50


@lru_cache(maxsize=4)
def _load_sprite_frames(
    path: str, frame_count: int, scale: float = 1.0
) -> tuple[np.ndarray, ...] | None:
    sheet = cv2.imread(str(REPO_ROOT / path), cv2.IMREAD_UNCHANGED)
    if sheet is None or sheet.ndim != 3 or sheet.shape[2] != 4:
        return None
    frame_w = sheet.shape[1] // frame_count
    if frame_w <= 0:
        return None
    frames = tuple(
        sheet[:, i * frame_w : (i + 1) * frame_w].copy() for i in range(frame_count)
    )
    if scale == 1.0:
        return frames
    target_w = max(1, int(round(frame_w * scale)))
    target_h = max(1, int(round(sheet.shape[0] * scale)))
    return tuple(
        cv2.resize(f, (target_w, target_h), interpolation=cv2.INTER_AREA) for f in frames
    )


def blit_sprite_rgba(canvas: np.ndarray, sprite_bgra: np.ndarray, top_left: tuple[int, int]) -> None:
    x, y = top_left
    h, w = sprite_bgra.shape[:2]
    ch, cw = canvas.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(cw, x + w), min(ch, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sx0, sy0 = x0 - x, y0 - y
    sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
    region = sprite_bgra[sy0:sy1, sx0:sx1]
    alpha = region[..., 3:4].astype(np.float32) / 255.0
    canvas[y0:y1, x0:x1] = (
        region[..., :3].astype(np.float32) * alpha
        + canvas[y0:y1, x0:x1].astype(np.float32) * (1.0 - alpha)
    ).astype(np.uint8)


# ── 기본 유틸 ───────────────────────────────────────────────────────


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def scale_color(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(int(clamp_float(channel * factor, 0, 255)) for channel in color)


def mix_color(
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    amount = clamp_float(ratio, 0.0, 1.0)
    return tuple(
        int(left[idx] * (1.0 - amount) + right[idx] * amount)
        for idx in range(3)
    )


def alpha_composite(image: np.ndarray, draw_fn, *, alpha: float) -> None:
    overlay = image.copy()
    draw_fn(overlay)
    a = clamp_float(alpha, 0.0, 1.0)
    cv2.addWeighted(overlay, a, image, 1.0 - a, 0, image)


def draw_rounded_rect(
    image: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    color: tuple[int, int, int],
    *,
    radius: int = 24,
    thickness: int = -1,
) -> None:
    x1, y1 = top_left
    x2, y2 = bottom_right
    radius = max(0, min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2))
    if thickness < 0:
        cv2.rectangle(image, (x1 + radius, y1), (x2 - radius, y2), color, -1, cv2.LINE_AA)
        cv2.rectangle(image, (x1, y1 + radius), (x2, y2 - radius), color, -1, cv2.LINE_AA)
        for c in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius), (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
            cv2.circle(image, c, radius, color, -1, cv2.LINE_AA)
        return
    cv2.line(image, (x1 + radius, y1), (x2 - radius, y1), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x1 + radius, y2), (x2 - radius, y2), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x1, y1 + radius), (x1, y2 - radius), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x2, y1 + radius), (x2, y2 - radius), color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def build_gradient_background(
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> np.ndarray:
    top = np.array(top_color, dtype=np.float32)
    bottom = np.array(bottom_color, dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    column = ((1.0 - ramp) * top + ramp * bottom).astype(np.uint8)
    return np.repeat(column[:, None, :], width, axis=1)


def draw_glow_circle(
    image: np.ndarray,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    strength: float = 0.18,
) -> None:
    for idx, factor in enumerate((2.2, 1.6, 1.15), start=1):
        current_alpha = strength / (idx * 0.85)
        current_radius = max(8, int(radius * factor))
        alpha_composite(
            image,
            lambda layer, r=current_radius: cv2.circle(layer, center, r, color, -1, cv2.LINE_AA),
            alpha=current_alpha,
        )


def trim_text(text: str | None, *, limit: int = 44) -> str:
    if not text:
        return "-"
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


# ── 이벤트 스캔 헬퍼 ────────────────────────────────────────────────


def _find_recent_event(rio: "RioOrchestrator", *wanted_topics: str) -> Event | None:
    targets = set(wanted_topics)
    for event in reversed(rio.event_log):
        if event.topic in targets:
            return event
    return None


def _is_recent_event(event: Event | None, *, within_ms: int = RECENT_ACTION_HOLD_MS) -> bool:
    if event is None:
        return False
    age_ms = (datetime.now(timezone.utc) - event.timestamp).total_seconds() * 1000.0
    return 0 <= age_ms <= within_ms


def _recent_task_event(rio: "RioOrchestrator", kind: ActionKind) -> Event | None:
    for event in reversed(rio.event_log):
        if event.topic not in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}:
            continue
        if event.payload.get("kind") == kind.value:
            return event
    return None


# ── mood palette ───────────────────────────────────────────────────


def mood_palette(
    mood: str,
    ui: str,
    *,
    dimmed: bool,
) -> dict[str, tuple[int, int, int]]:
    palettes = {
        "inactive": {
            "bg_top": rgb(16, 24, 35), "bg_bottom": rgb(7, 11, 18), "panel": rgb(24, 32, 46),
            "panel_edge": rgb(74, 92, 118), "accent": rgb(146, 184, 212), "glow": rgb(96, 137, 172),
            "eye": rgb(217, 236, 246), "mouth": rgb(168, 194, 212), "cheek": rgb(90, 116, 136),
        },
        "calm": {
            "bg_top": rgb(23, 52, 83), "bg_bottom": rgb(8, 21, 38), "panel": rgb(18, 41, 64),
            "panel_edge": rgb(84, 180, 236), "accent": rgb(106, 224, 255), "glow": rgb(64, 178, 255),
            "eye": rgb(233, 248, 255), "mouth": rgb(194, 232, 248), "cheek": rgb(255, 176, 138),
        },
        "attentive": {
            "bg_top": rgb(15, 63, 92), "bg_bottom": rgb(5, 24, 40), "panel": rgb(10, 47, 70),
            "panel_edge": rgb(92, 228, 255), "accent": rgb(125, 244, 255), "glow": rgb(66, 208, 255),
            "eye": rgb(239, 252, 255), "mouth": rgb(208, 239, 250), "cheek": rgb(255, 196, 150),
        },
        "sleepy": {
            "bg_top": rgb(30, 40, 78), "bg_bottom": rgb(12, 17, 34), "panel": rgb(22, 28, 55),
            "panel_edge": rgb(155, 166, 255), "accent": rgb(196, 202, 255), "glow": rgb(114, 124, 228),
            "eye": rgb(232, 237, 255), "mouth": rgb(214, 222, 255), "cheek": rgb(176, 164, 228),
        },
        "alert": {
            "bg_top": rgb(118, 31, 15), "bg_bottom": rgb(55, 12, 8), "panel": rgb(82, 22, 15),
            "panel_edge": rgb(255, 176, 107), "accent": rgb(255, 216, 124), "glow": rgb(255, 90, 55),
            "eye": rgb(255, 245, 225), "mouth": rgb(255, 214, 194), "cheek": rgb(255, 134, 102),
        },
        "startled": {
            "bg_top": rgb(14, 66, 100), "bg_bottom": rgb(6, 30, 47), "panel": rgb(10, 52, 79),
            "panel_edge": rgb(255, 202, 120), "accent": rgb(255, 225, 143), "glow": rgb(254, 126, 75),
            "eye": rgb(255, 248, 235), "mouth": rgb(255, 232, 224), "cheek": rgb(255, 164, 144),
        },
        "confused": {
            "bg_top": rgb(78, 63, 22), "bg_bottom": rgb(31, 23, 8), "panel": rgb(61, 46, 16),
            "panel_edge": rgb(244, 217, 120), "accent": rgb(252, 229, 141), "glow": rgb(209, 168, 59),
            "eye": rgb(255, 245, 208), "mouth": rgb(246, 228, 186), "cheek": rgb(210, 162, 112),
        },
        "welcome": {
            "bg_top": rgb(15, 77, 74), "bg_bottom": rgb(6, 37, 35), "panel": rgb(10, 62, 58),
            "panel_edge": rgb(111, 255, 227), "accent": rgb(160, 255, 226), "glow": rgb(76, 237, 193),
            "eye": rgb(240, 255, 247), "mouth": rgb(214, 248, 226), "cheek": rgb(255, 188, 167),
        },
        "happy": {
            "bg_top": rgb(127, 54, 42), "bg_bottom": rgb(63, 20, 22), "panel": rgb(102, 39, 37),
            "panel_edge": rgb(255, 183, 143), "accent": rgb(255, 221, 171), "glow": rgb(255, 119, 96),
            "eye": rgb(255, 245, 236), "mouth": rgb(255, 227, 212), "cheek": rgb(255, 152, 148),
        },
    }
    palette = dict(palettes.get(mood, palettes["calm"]))
    if ui == "AlertUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(255, 128, 92), 0.42)
        palette["accent"] = mix_color(palette["accent"], rgb(255, 220, 170), 0.32)
    elif ui == "GameUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(152, 252, 177), 0.45)
        palette["accent"] = mix_color(palette["accent"], rgb(220, 255, 176), 0.28)
    elif ui == "CameraUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(255, 236, 163), 0.35)
        palette["accent"] = mix_color(palette["accent"], rgb(255, 240, 210), 0.18)
    if dimmed:
        for key, color in list(palette.items()):
            palette[key] = scale_color(color, 0.48 if key.startswith("bg") else 0.55)
    return palette


# ── 표정 이미지 에셋 로더 ───────────────────────────────────────────


@lru_cache(maxsize=1)
def load_expression_assets() -> dict[str, np.ndarray]:
    assets: dict[str, np.ndarray] = {}
    root = REPO_ROOT / "assets" / "expressions"
    if not root.exists():
        return assets
    for path in sorted(root.glob("*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is not None:
            if image.shape[1] != 1024 or image.shape[0] != 600:
                image = cv2.resize(image, (1024, 600), interpolation=cv2.INTER_AREA)
            assets[path.stem] = image
    return assets


def choose_face_asset_key(rio: "RioOrchestrator", render_frame: Any) -> str:
    snapshot = rio.store.snapshot()
    assets = load_expression_assets()
    overlay_key = Path(render_frame.overlay.name).stem if render_frame.overlay.name else ""

    def pick(*candidates: str) -> str:
        for name in candidates:
            if name in assets:
                return name
        return candidates[-1]

    photo_task = _recent_task_event(rio, ActionKind.PHOTO)
    if photo_task is not None and photo_task.topic == topics.TASK_SUCCEEDED and _is_recent_event(photo_task, within_ms=900):
        return pick("photo_snap", "happy")

    smarthome_result = _find_recent_event(rio, topics.SMARTHOME_RESULT)
    if smarthome_result is not None and _is_recent_event(smarthome_result) and not smarthome_result.payload.get("ok", True):
        return pick("smarthome_fail", "confused")

    if snapshot.activity_state == ActivityState.EXECUTING:
        kind = snapshot.extended.active_executing_kind
        if kind == ActionKind.PHOTO:
            return pick("photo_ready", "attentive")
        if kind == ActionKind.GAME:
            return pick("game_face", "attentive")
        if kind == ActionKind.DANCE:
            return pick("dance_face", "happy")
        if kind == ActionKind.WEATHER:
            return pick("weather_face", "attentive")

    if render_frame.ui == "CameraUI":
        return pick("photo_ready", "attentive")
    if render_frame.ui == "GameUI":
        return pick("game_face", "attentive")

    if overlay_key in {"petting", "welcome", "startled"}:
        return pick(overlay_key, render_frame.face.mood)
    if overlay_key == "sleep":
        return pick("sleepy")

    if render_frame.face.mood == "inactive":
        return pick("sleepy")
    return pick(render_frame.face.mood, "calm")


def asset_transition_keys(asset_key: str, *, now_s: float) -> tuple[str | None, str, float]:
    state = _FACE_ASSET_TRANSITION
    if state["current"] != asset_key:
        state["previous"] = state["current"]
        state["current"] = asset_key
        state["changed_at"] = now_s
    progress = clamp_float((now_s - float(state["changed_at"])) / 0.26, 0.0, 1.0)
    previous = state["previous"] if progress < 1.0 else None
    if progress >= 1.0:
        state["previous"] = None
    return previous, asset_key, progress


def composite_panel_rgba(canvas: np.ndarray, panel_rgba: np.ndarray, rect: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = rect
    target = canvas[y1:y2, x1:x2]
    rgb_channels = panel_rgba[:, :, :3].astype(np.float32)
    if panel_rgba.shape[2] == 4:
        alpha = (panel_rgba[:, :, 3:4].astype(np.float32) / 255.0)
    else:
        alpha = np.ones((*panel_rgba.shape[:2], 1), dtype=np.float32)
    target_float = target.astype(np.float32)
    blended = rgb_channels * alpha + target_float * (1.0 - alpha)
    target[:] = blended.astype(np.uint8)


def make_asset_panel(
    asset_rgba: np.ndarray,
    *,
    panel_size: tuple[int, int],
    scale: float,
    shift: tuple[int, int],
    alpha: float,
    dimmed: bool,
) -> np.ndarray:
    panel_w, panel_h = panel_size
    scaled_w = max(8, int(panel_w * scale))
    scaled_h = max(8, int(panel_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(asset_rgba, (scaled_w, scaled_h), interpolation=interpolation)

    panel = np.zeros((panel_h, panel_w, 4), dtype=np.uint8)
    panel[:, :, :3] = ASSET_FACE_BG
    panel[:, :, 3] = 255

    offset_x = (panel_w - scaled_w) // 2 + shift[0]
    offset_y = (panel_h - scaled_h) // 2 + shift[1]
    src_x1 = max(0, -offset_x)
    src_y1 = max(0, -offset_y)
    dst_x1 = max(0, offset_x)
    dst_y1 = max(0, offset_y)
    copy_w = min(scaled_w - src_x1, panel_w - dst_x1)
    copy_h = min(scaled_h - src_y1, panel_h - dst_y1)
    if copy_w > 0 and copy_h > 0:
        src = resized[src_y1:src_y1 + copy_h, src_x1:src_x1 + copy_w]
        panel[dst_y1:dst_y1 + copy_h, dst_x1:dst_x1 + copy_w] = src

    if alpha < 1.0:
        panel[:, :, 3] = (panel[:, :, 3].astype(np.float32) * alpha).astype(np.uint8)
    if dimmed:
        panel[:, :, :3] = (panel[:, :, :3].astype(np.float32) * 0.62).astype(np.uint8)
    return panel


def draw_asset_blink_overlay(image: np.ndarray, rect: tuple[int, int, int, int], *, blink: float) -> None:
    if blink <= 0.08:
        return
    x1, y1, x2, y2 = rect
    eye_cy = int(y1 + (y2 - y1) * 0.376)
    eye_w = int((x2 - x1) * 0.095)
    eye_h = int((y2 - y1) * 0.168)
    bar_h = max(2, int(eye_h * blink))
    for cx_ratio in (0.261, 0.739):
        cx = int(x1 + (x2 - x1) * cx_ratio)
        cv2.rectangle(
            image,
            (cx - eye_w // 2, eye_cy - bar_h // 2),
            (cx + eye_w // 2, eye_cy + bar_h // 2),
            ASSET_FACE_BG,
            -1,
            cv2.LINE_AA,
        )


def draw_face_asset_panel(
    canvas: np.ndarray,
    *,
    rect: tuple[int, int, int, int],
    asset_key: str,
    render_frame: Any,
    now_s: float,
) -> bool:
    assets = load_expression_assets()
    if asset_key not in assets:
        return False

    x1, y1, x2, y2 = rect
    panel_rect = (x1 + 16, y1 + 16, x2 - 16, y2 - 16)
    panel_w = panel_rect[2] - panel_rect[0]
    panel_h = panel_rect[3] - panel_rect[1]
    shift = (
        int(render_frame.face.eye_offset[0] * 1.5),
        int(render_frame.face.eye_offset[1] * 1.2 + math.sin(now_s * 1.4) * 4.0),
    )
    scale = 1.0 + 0.02 * math.sin(now_s * 1.2)

    previous_key, current_key, progress = asset_transition_keys(asset_key, now_s=now_s)
    current_panel = make_asset_panel(
        assets[current_key],
        panel_size=(panel_w, panel_h),
        scale=scale,
        shift=shift,
        alpha=1.0 if previous_key is None else progress,
        dimmed=render_frame.face.dimmed,
    )
    if previous_key is not None and previous_key in assets:
        previous_panel = make_asset_panel(
            assets[previous_key],
            panel_size=(panel_w, panel_h),
            scale=scale,
            shift=shift,
            alpha=1.0 - progress,
            dimmed=render_frame.face.dimmed,
        )
        composite_panel_rgba(canvas, previous_panel, panel_rect)
    composite_panel_rgba(canvas, current_panel, panel_rect)
    if current_key in {"calm", "attentive"}:
        draw_asset_blink_overlay(canvas, panel_rect, blink=blink_amount(now_s, current_key))
    return True


def blink_amount(now_s: float, mood: str) -> float:
    if mood == "inactive":
        return 0.72 + 0.18 * math.sin(now_s * 0.45)
    if mood == "sleepy":
        period = 3.1
        width = 0.22
    elif mood in {"alert", "startled"}:
        period = 6.2
        width = 0.06
    elif mood == "happy":
        period = 4.2
        width = 0.12
    else:
        period = 4.8
        width = 0.09

    phase = (now_s / period) % 1.0
    centers = [0.05]
    if mood in {"happy", "welcome"}:
        centers.append(0.11)
    blink = 0.0
    for center in centers:
        distance = abs(phase - center)
        blink = max(blink, max(0.0, 1.0 - distance / width))
    return clamp_float(blink, 0.0, 1.0)


# ── 벡터 fallback 얼굴 파츠 ────────────────────────────────────────


def draw_heart(image: np.ndarray, center: tuple[int, int], size: int, color: tuple[int, int, int], *, thickness: int = -1) -> None:
    radius = max(4, size // 3)
    left = (center[0] - radius, center[1] - radius // 2)
    right = (center[0] + radius, center[1] - radius // 2)
    bottom = np.array(
        [
            [center[0] - size, center[1] - radius // 2],
            [center[0] + size, center[1] - radius // 2],
            [center[0], center[1] + size],
        ],
        dtype=np.int32,
    )
    cv2.circle(image, left, radius, color, thickness, cv2.LINE_AA)
    cv2.circle(image, right, radius, color, thickness, cv2.LINE_AA)
    cv2.fillConvexPoly(image, bottom, color, cv2.LINE_AA)


def draw_star(image: np.ndarray, center: tuple[int, int], radius: int, color: tuple[int, int, int], *, thickness: int = 2) -> None:
    cv2.line(image, (center[0] - radius, center[1]), (center[0] + radius, center[1]), color, thickness, cv2.LINE_AA)
    cv2.line(image, (center[0], center[1] - radius), (center[0], center[1] + radius), color, thickness, cv2.LINE_AA)
    cv2.line(
        image,
        (center[0] - radius // 2, center[1] - radius // 2),
        (center[0] + radius // 2, center[1] + radius // 2),
        color,
        max(1, thickness - 1),
        cv2.LINE_AA,
    )
    cv2.line(
        image,
        (center[0] - radius // 2, center[1] + radius // 2),
        (center[0] + radius // 2, center[1] - radius // 2),
        color,
        max(1, thickness - 1),
        cv2.LINE_AA,
    )


def draw_mouth(
    image: np.ndarray,
    center: tuple[int, int],
    mood: str,
    palette: dict[str, tuple[int, int, int]],
    *,
    now_s: float,
    width: int,
    height: int,
) -> None:
    mouth_color = palette["mouth"]
    accent = palette["accent"]
    if mood == "startled":
        radius = max(10, width // 8)
        cv2.circle(image, center, radius, mouth_color, 4, cv2.LINE_AA)
        cv2.circle(image, center, max(3, radius // 2), scale_color(palette["panel"], 0.55), -1, cv2.LINE_AA)
        return
    if mood == "sleepy":
        rx = max(16, width // 6)
        ry = max(10, height // 3)
        cv2.ellipse(image, center, (rx, ry), 0, 0, 360, mouth_color, 4, cv2.LINE_AA)
        cv2.ellipse(image, center, (max(6, rx - 6), max(4, ry - 6)), 0, 0, 360, scale_color(palette["panel"], 0.72), -1, cv2.LINE_AA)
        return
    if mood == "confused":
        points = []
        for idx in range(6):
            x = int(center[0] - width // 2 + idx * (width / 5.0))
            y = int(center[1] + math.sin(now_s * 4.0 + idx * 0.9) * 5.0)
            points.append((x, y))
        cv2.polylines(image, [np.array(points, dtype=np.int32)], False, mouth_color, 4, cv2.LINE_AA)
        return
    if mood == "alert":
        cv2.line(image, (center[0] - width // 3, center[1]), (center[0] + width // 3, center[1]), mouth_color, 5, cv2.LINE_AA)
        cv2.circle(image, (center[0] + width // 2, center[1] - height), max(4, width // 10), accent, -1, cv2.LINE_AA)
        return
    if mood in {"happy", "welcome"}:
        rx = max(22, width // 2)
        ry = max(14, height)
        cv2.ellipse(image, center, (rx, ry), 0, 10, 170, mouth_color, 5, cv2.LINE_AA)
        if mood == "happy":
            tongue_center = (center[0], center[1] + max(6, height // 2))
            cv2.ellipse(image, tongue_center, (max(10, width // 6), max(6, height // 3)), 0, 0, 180, palette["cheek"], -1, cv2.LINE_AA)
        return
    curve = 22 if mood == "calm" else 12
    rx = max(18, width // 2)
    ry = max(8, height // 2)
    cv2.ellipse(image, center, (rx, ry), 0, 20, 160, mouth_color, 4, cv2.LINE_AA)
    if mood == "attentive":
        cv2.line(image, (center[0] - rx // 3, center[1] + curve // 10), (center[0] + rx // 3, center[1] + curve // 10), accent, 2, cv2.LINE_AA)


def draw_eye(
    image: np.ndarray,
    center: tuple[int, int],
    mood: str,
    palette: dict[str, tuple[int, int, int]],
    *,
    eye_width: int,
    eye_height: int,
    open_ratio: float,
    pupil_offset: tuple[int, int],
    eyebrow_tilt: int = 0,
) -> None:
    white = palette["eye"]
    accent = palette["accent"]
    panel = palette["panel"]
    eye_open_px = max(4, int(eye_height * clamp_float(open_ratio, 0.08, 1.15)))

    if mood == "happy":
        cv2.ellipse(image, center, (eye_width, max(4, eye_height // 2)), 0, 205, 335, white, 7, cv2.LINE_AA)
    elif mood == "inactive":
        cv2.line(image, (center[0] - eye_width, center[1]), (center[0] + eye_width, center[1]), scale_color(white, 0.8), 6, cv2.LINE_AA)
    else:
        cv2.ellipse(image, center, (eye_width, eye_open_px), 0, 0, 360, white, -1, cv2.LINE_AA)
        cv2.ellipse(image, center, (eye_width, eye_open_px), 0, 0, 360, accent, 3, cv2.LINE_AA)
        if open_ratio > 0.18:
            iris_center = (
                center[0] + int(clamp_float(pupil_offset[0], -eye_width * 0.45, eye_width * 0.45)),
                center[1] + int(clamp_float(pupil_offset[1], -eye_open_px * 0.35, eye_open_px * 0.35)),
            )
            iris_radius = max(7, int(min(eye_width, eye_open_px) * 0.52))
            cv2.circle(image, iris_center, iris_radius, scale_color(accent, 0.95), -1, cv2.LINE_AA)
            cv2.circle(image, iris_center, max(3, iris_radius // 2), scale_color(panel, 0.28), -1, cv2.LINE_AA)
            highlight = (iris_center[0] - max(2, iris_radius // 3), iris_center[1] - max(2, iris_radius // 3))
            cv2.circle(image, highlight, max(2, iris_radius // 4), rgb(255, 255, 255), -1, cv2.LINE_AA)

    brow_y = center[1] - eye_height - 16
    left = (center[0] - eye_width, brow_y + eyebrow_tilt)
    right = (center[0] + eye_width, brow_y - eyebrow_tilt)
    cv2.line(image, left, right, scale_color(accent, 0.86), 5, cv2.LINE_AA)


def draw_ui_overlay(
    image: np.ndarray,
    *,
    face_rect: tuple[int, int, int, int],
    ui: str,
    palette: dict[str, tuple[int, int, int]],
    search_indicator: bool,
    overlay_name: str | None,
    now_s: float,
    gesture: str | None,
    asset_key: str | None = None,
    photo_countdown_remaining: float | None = None,
) -> None:
    x1, y1, x2, y2 = face_rect
    accent = palette["accent"]
    panel_edge = palette["panel_edge"]
    overlay_key = Path(overlay_name).stem if overlay_name else ""
    pulse = 0.5 + 0.5 * math.sin(now_s * 4.2)

    if asset_key == "dance_face":
        dance_colors = (rgb(255, 60, 60), rgb(60, 200, 90), rgb(60, 120, 255))
        phase_idx = int(now_s * 2.0) % len(dance_colors)
        flash_color = dance_colors[phase_idx]
        alpha_composite(
            image,
            lambda layer: cv2.rectangle(layer, (x1, y1), (x2, y2), flash_color, -1, cv2.LINE_AA),
            alpha=0.20,
        )

    if ui == "ListeningUI":
        frames = _load_sprite_frames(
            LISTENING_SPRITE_PATH, LISTENING_SPRITE_FRAMES, LISTENING_SPRITE_SCALE
        )
        if frames is not None:
            frame_idx = int(now_s * LISTENING_SPRITE_FPS) % LISTENING_SPRITE_FRAMES
            sprite = frames[frame_idx]
            sh, sw = sprite.shape[:2]
            canvas_h = image.shape[0]
            blit_x = LISTENING_MARGIN_PX
            blit_y = canvas_h - sh - LISTENING_MARGIN_PX
            blit_sprite_rgba(image, sprite, (blit_x, blit_y))

    if ui == "CameraUI" or overlay_key == "camera_countdown":
        bracket_color = mix_color(panel_edge, rgb(255, 238, 178), 0.4)
        for sx, sy in ((x1 + 34, y1 + 34), (x2 - 34, y1 + 34), (x1 + 34, y2 - 34), (x2 - 34, y2 - 34)):
            dx = 28 if sx < (x1 + x2) // 2 else -28
            dy = 28 if sy < (y1 + y2) // 2 else -28
            cv2.line(image, (sx, sy), (sx + dx, sy), bracket_color, 4, cv2.LINE_AA)
            cv2.line(image, (sx, sy), (sx, sy + dy), bracket_color, 4, cv2.LINE_AA)
        cv2.circle(image, (x2 - 52, y1 + 52), 10, rgb(255, 96, 82), -1, cv2.LINE_AA)
        if photo_countdown_remaining is not None and photo_countdown_remaining > 0:
            count_number = max(1, int(math.ceil(photo_countdown_remaining)))
            count_text = str(count_number)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            pulse_scale = 1.0 + 0.25 * (photo_countdown_remaining - math.floor(photo_countdown_remaining))
            font_scale = 9.0 * pulse_scale
            thickness = 18
            (text_w, text_h), _ = cv2.getTextSize(count_text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness)
            text_org = (cx - text_w // 2, cy + text_h // 2)
            alpha_composite(
                image,
                lambda layer: cv2.circle(layer, (cx, cy), int(max(text_w, text_h) * 0.72), rgb(0, 0, 0), -1, cv2.LINE_AA),
                alpha=0.42,
            )
            cv2.putText(image, count_text, text_org, cv2.FONT_HERSHEY_DUPLEX, font_scale, rgb(0, 0, 0), thickness + 6, cv2.LINE_AA)
            cv2.putText(image, count_text, text_org, cv2.FONT_HERSHEY_DUPLEX, font_scale, rgb(255, 238, 178), thickness, cv2.LINE_AA)

    if ui == "GameUI" or overlay_key == "game_direction":
        arrow_color = mix_color(accent, rgb(184, 255, 168), 0.22)
        cy = (y1 + y2) // 2
        left_arrow = np.array([[x1 + 36, cy], [x1 + 90, cy - 30], [x1 + 90, cy + 30]], dtype=np.int32)
        right_arrow = np.array([[x2 - 36, cy], [x2 - 90, cy - 30], [x2 - 90, cy + 30]], dtype=np.int32)
        cv2.polylines(image, [left_arrow], True, arrow_color, 4, cv2.LINE_AA)
        cv2.polylines(image, [right_arrow], True, arrow_color, 4, cv2.LINE_AA)
        if gesture in {"head_left", "head_right"}:
            badge_x = x1 + 86 if gesture == "head_left" else x2 - 86
            cv2.circle(image, (badge_x, cy), 18, arrow_color, -1, cv2.LINE_AA)

    if ui == "AlertUI":
        alert_color = mix_color(panel_edge, rgb(255, 115, 92), 0.6)
        thickness = 4 + int(pulse * 4)
        draw_rounded_rect(image, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), alert_color, radius=40, thickness=thickness)

    if ui == "SleepUI":
        for idx in range(3):
            pos = (x2 - 150 + idx * 26, y1 + 88 - idx * 18)
            cv2.putText(image, "Z", pos, cv2.FONT_HERSHEY_DUPLEX, 0.9 + idx * 0.12, scale_color(accent, 1.05), 2, cv2.LINE_AA)
        draw_star(image, (x1 + 90, y1 + 78), 12, scale_color(accent, 1.08))

    if overlay_key in {"petting", "welcome", "peekaboo", "wave"}:
        for idx in range(3):
            heart_center = (x1 + 96 + idx * 42, y1 + 96 - int(math.sin(now_s * 2.8 + idx) * 8.0))
            draw_heart(image, heart_center, 16, scale_color(palette["cheek"], 1.06))

    if overlay_key == "smarthome_badge":
        badge_center = (x2 - 84, y2 - 74)
        cv2.circle(image, badge_center, 34, mix_color(panel_edge, rgb(83, 255, 197), 0.25), -1, cv2.LINE_AA)
        home = np.array(
            [
                [badge_center[0] - 18, badge_center[1] + 6],
                [badge_center[0] - 18, badge_center[1] - 6],
                [badge_center[0], badge_center[1] - 22],
                [badge_center[0] + 18, badge_center[1] - 6],
                [badge_center[0] + 18, badge_center[1] + 6],
            ],
            dtype=np.int32,
        )
        cv2.polylines(image, [home], False, rgb(255, 255, 255), 3, cv2.LINE_AA)
        cv2.rectangle(image, (badge_center[0] - 10, badge_center[1] + 2), (badge_center[0] + 10, badge_center[1] + 20), rgb(255, 255, 255), 3, cv2.LINE_AA)

    if overlay_key == "finger_gun":
        cv2.putText(image, "BANG!", (x1 + 52, y1 + 82), cv2.FONT_HERSHEY_DUPLEX, 1.0, rgb(255, 228, 148), 2, cv2.LINE_AA)


# ── 기본 라벨 (details["current_action"] 대체용) ────────────────────


_KIND_LABELS = {
    ActionKind.PHOTO: "Taking photo",
    ActionKind.DANCE: "Dance mode",
    ActionKind.GAME: "Game",
    ActionKind.WEATHER: "Weather",
    ActionKind.SMARTHOME: "Smart home",
    ActionKind.TIMER_SETUP: "Timer",
}


def default_action_label(rio: "RioOrchestrator") -> str:
    snapshot = rio.store.snapshot()
    if snapshot.activity_state == ActivityState.ALERTING:
        return "Alert"
    if snapshot.activity_state == ActivityState.EXECUTING:
        kind = snapshot.extended.active_executing_kind
        if kind is not None:
            return _KIND_LABELS.get(kind, kind.value)
    if snapshot.activity_state == ActivityState.LISTENING:
        return "Listening"
    if snapshot.context_state == ContextState.ENGAGED:
        return "Ready"
    return "Idle"


# ── 메인 draw_robot_face ───────────────────────────────────────────


def draw_robot_face(
    canvas: np.ndarray,
    rio: "RioOrchestrator",
    *,
    face_rect: tuple[int, int, int, int],
    now_s: float,
    render_frame: Any,
    current_action: str = "",
    last_gesture: str | None = None,
) -> None:
    snapshot = rio.store.snapshot()
    palette = mood_palette(render_frame.face.mood, render_frame.ui, dimmed=render_frame.face.dimmed)
    x1, y1, x2, y2 = face_rect
    face_width = x2 - x1
    face_height = y2 - y1
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (x1 + 18, y1 + 26), (x2 + 10, y2 + 36), rgb(4, 10, 18), radius=48),
        alpha=0.32,
    )
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), scale_color(palette["panel"], 0.96), radius=48)
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel_edge"], radius=48, thickness=4)

    asset_key = choose_face_asset_key(rio, render_frame)
    countdown_remaining: float | None = None
    if rio.photo_countdown_end_at is not None:
        delta = (rio.photo_countdown_end_at - datetime.now(timezone.utc)).total_seconds()
        if delta > 0:
            countdown_remaining = delta

    if draw_face_asset_panel(canvas, rect=face_rect, asset_key=asset_key, render_frame=render_frame, now_s=now_s):
        draw_ui_overlay(
            canvas,
            face_rect=face_rect,
            ui=render_frame.ui,
            palette=palette,
            search_indicator=render_frame.hud.search_indicator,
            overlay_name=render_frame.overlay.name,
            now_s=now_s,
            gesture=last_gesture,
            asset_key=asset_key,
            photo_countdown_remaining=countdown_remaining,
        )
        _draw_action_badge(canvas, face_rect, palette, current_action)
        return

    # ── 이미지 에셋 없을 때 벡터 fallback ─────────────────────────
    bob = math.sin(now_s * 1.7) * 5.0 + math.sin(now_s * 0.65 + 0.6) * 3.0
    center_y = int(center_y + bob)

    draw_glow_circle(canvas, (center_x, center_y - 24), int(face_width * 0.26), palette["glow"], strength=0.18)

    ear_color = scale_color(palette["panel"], 1.12)
    ear_glow = scale_color(palette["accent"], 0.72)
    left_ear = (x1 + face_width // 5, y1 + 88 + int(math.sin(now_s * 2.2) * 4.0))
    right_ear = (x2 - face_width // 5, y1 + 88 + int(math.sin(now_s * 2.2 + 1.1) * 4.0))
    for c in (left_ear, right_ear):
        draw_glow_circle(canvas, c, 26, ear_glow, strength=0.12)
        cv2.circle(canvas, c, 26, ear_color, -1, cv2.LINE_AA)
        cv2.circle(canvas, c, 12, scale_color(palette["accent"], 0.92), -1, cv2.LINE_AA)

    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel"], radius=48)
    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (x1 + 14, y1 + 14), (x2 - 14, y2 - 14), scale_color(palette["panel_edge"], 0.34), radius=40),
        alpha=0.14,
    )
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel_edge"], radius=48, thickness=4)

    eye_spacing = face_width // 4
    eye_y = center_y - face_height // 10
    eye_width = max(32, face_width // 11)
    eye_height = max(26, face_height // 10)
    offset_x, offset_y = render_frame.face.eye_offset
    subtle_x = math.sin(now_s * 0.8) * 1.5
    subtle_y = math.cos(now_s * 0.95) * 1.2
    pupil_offset = (int(offset_x * 1.65 + subtle_x), int(offset_y * 1.45 + subtle_y))

    blink = blink_amount(now_s, render_frame.face.mood)
    base_open = {
        "inactive": 0.16, "calm": 0.92, "attentive": 1.0, "sleepy": 0.38,
        "alert": 1.04, "startled": 1.08, "confused": 0.78, "welcome": 0.96, "happy": 0.28,
    }.get(render_frame.face.mood, 0.9)
    open_left = base_open * (1.0 - blink * 0.96)
    open_right = base_open * (1.0 - blink * 0.92)
    if render_frame.face.mood == "confused":
        open_left *= 0.72
    if render_frame.face.mood == "sleepy":
        open_right *= 0.88

    eyebrow_tilt = {
        "calm": -2, "attentive": 1, "sleepy": 8, "alert": -8, "startled": -10,
        "confused": 5, "welcome": -3, "happy": -4, "inactive": 2,
    }.get(render_frame.face.mood, 0)

    left_eye = (center_x - eye_spacing // 2, eye_y)
    right_eye = (center_x + eye_spacing // 2, eye_y)
    draw_eye(
        canvas, left_eye, render_frame.face.mood, palette,
        eye_width=eye_width, eye_height=eye_height, open_ratio=open_left,
        pupil_offset=pupil_offset,
        eyebrow_tilt=eyebrow_tilt if render_frame.face.mood != "confused" else 9,
    )
    draw_eye(
        canvas, right_eye, render_frame.face.mood, palette,
        eye_width=eye_width, eye_height=eye_height, open_ratio=open_right,
        pupil_offset=(pupil_offset[0] - 2, pupil_offset[1]),
        eyebrow_tilt=-eyebrow_tilt if render_frame.face.mood == "confused" else eyebrow_tilt,
    )

    mouth_center = (center_x, center_y + face_height // 6)
    draw_mouth(
        canvas, mouth_center, render_frame.face.mood, palette,
        now_s=now_s, width=face_width // 5, height=face_height // 13,
    )

    if render_frame.face.mood in {"happy", "welcome"}:
        cheek_y = mouth_center[1] - 18
        for cheek_x in (center_x - eye_spacing // 2, center_x + eye_spacing // 2):
            alpha_composite(
                canvas,
                lambda layer, cx=cheek_x: cv2.circle(layer, (cx, cheek_y), 26, palette["cheek"], -1, cv2.LINE_AA),
                alpha=0.22,
            )

    if snapshot.context_state == ContextState.SLEEPY:
        draw_star(canvas, (x1 + 120, y1 + 126), 14, scale_color(palette["accent"], 1.1))
        draw_star(canvas, (x1 + 178, y1 + 88), 10, scale_color(palette["accent"], 0.95))

    if snapshot.active_oneshot is not None and snapshot.active_oneshot.name.value == "happy":
        draw_heart(canvas, (x2 - 92, y1 + 122), 18, scale_color(palette["cheek"], 1.05))
        draw_heart(canvas, (x2 - 138, y1 + 98), 14, scale_color(palette["cheek"], 1.0))

    draw_ui_overlay(
        canvas,
        face_rect=face_rect,
        ui=render_frame.ui,
        palette=palette,
        search_indicator=render_frame.hud.search_indicator,
        overlay_name=render_frame.overlay.name,
        now_s=now_s,
        gesture=last_gesture,
        photo_countdown_remaining=countdown_remaining,
    )
    _draw_action_badge(canvas, face_rect, palette, current_action)


def _draw_action_badge(
    canvas: np.ndarray,
    face_rect: tuple[int, int, int, int],
    palette: dict[str, tuple[int, int, int]],
    badge_text: str,
) -> None:
    if not badge_text:
        return
    x1, y1, x2, y2 = face_rect
    face_width = x2 - x1
    center_x = (x1 + x2) // 2
    badge_w = min(face_width - 60, max(260, len(badge_text) * 11))
    badge_rect = (center_x - badge_w // 2, y2 - 86, center_x + badge_w // 2, y2 - 34)
    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel"], 0.52), radius=24),
        alpha=0.54,
    )
    draw_rounded_rect(canvas, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel_edge"], 0.74), radius=24, thickness=2)
    cv2.putText(
        canvas,
        trim_text(badge_text, limit=38),
        (badge_rect[0] + 18, badge_rect[1] + 34),
        cv2.FONT_HERSHEY_DUPLEX,
        0.75,
        rgb(245, 248, 250),
        1,
        cv2.LINE_AA,
    )


# ── PreviewWindow ──────────────────────────────────────────────────


class PreviewWindow:
    """OpenCV 프리뷰 창 — run_rio_app.py 같은 진입점에서 쓰는 얼굴-only 렌더러.

    사용 예::

        window = PreviewWindow(fullscreen=True)
        try:
            while True:
                rio.run_once()
                if window.update(rio):
                    break  # ESC/q
        finally:
            window.close()
    """

    WINDOW_NAME = "RIO"

    def __init__(self, *, fullscreen: bool = True) -> None:
        self._fullscreen = fullscreen
        self._window_ready = False

    def _ensure_window(self, canvas_w: int, canvas_h: int) -> None:
        if self._window_ready:
            return
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        if self._fullscreen:
            cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.resizeWindow(self.WINDOW_NAME, min(canvas_w, 1440), min(canvas_h, 900))
        self._window_ready = True

    def update(
        self,
        rio: "RioOrchestrator",
        *,
        current_action: str | None = None,
        last_gesture: str | None = None,
    ) -> bool:
        """한 프레임 그리고 키 입력을 폴링.

        반환값: 사용자가 ESC/q 를 눌러 종료 요청을 했으면 True.
        """
        render_frame = rio.renderer.history[-1] if rio.renderer.history else None
        if render_frame is None:
            # 첫 이벤트가 들어오기 전에는 렌더할 게 없음. 그냥 검은 화면 유지.
            return False

        canvas_h = 800
        canvas_w = max(1280, int(canvas_h * 16 / 9))
        palette = mood_palette(render_frame.face.mood, render_frame.ui, dimmed=render_frame.face.dimmed)
        canvas = build_gradient_background(canvas_w, canvas_h, palette["bg_top"], palette["bg_bottom"])

        now_s = time.time()
        for idx in range(3):
            orb_x = int(canvas_w * (0.18 + idx * 0.24) + math.sin(now_s * (0.55 + idx * 0.2)) * 42.0)
            orb_y = int(canvas_h * (0.16 + idx * 0.21) + math.cos(now_s * (0.75 + idx * 0.18)) * 26.0)
            draw_glow_circle(canvas, (orb_x, orb_y), 48 + idx * 18, scale_color(palette["glow"], 0.88), strength=0.11)

        horizontal_margin = max(36, canvas_w // 18)
        vertical_margin = max(30, canvas_h // 20)
        face_rect = (horizontal_margin, vertical_margin, canvas_w - horizontal_margin, canvas_h - vertical_margin)

        label = current_action if current_action is not None else default_action_label(rio)
        draw_robot_face(
            canvas,
            rio,
            face_rect=face_rect,
            now_s=now_s,
            render_frame=render_frame,
            current_action=label,
            last_gesture=last_gesture,
        )

        self._ensure_window(canvas_w, canvas_h)
        cv2.imshow(self.WINDOW_NAME, canvas)
        key = cv2.waitKey(1) & 0xFF
        return key in {27, ord("q")}

    def close(self) -> None:
        if self._window_ready:
            try:
                cv2.destroyWindow(self.WINDOW_NAME)
            except cv2.error:
                pass
            self._window_ready = False


__all__ = ["PreviewWindow", "default_action_label", "draw_robot_face"]
