"""BMO-style face compositor – 이미지 기반 + 코드 fallback.

assets/expressions/<mood>.png 이미지가 있으면 그대로 blit.
이미지가 없으면 기존 pygame 벡터 드로잉으로 fallback.

calm/attentive는 파츠 분리 시 gaze tracking 가능 (parts/ 하위).
파츠가 없어도 full-frame 이미지로 동작.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import pygame
except ImportError:
    pygame = None


# ── 색상 (Figma 팔레트) ───────────────────────────────────────
COLOR_BG = (201, 228, 195)          # #C9E4C3
COLOR_EYE = (0, 0, 0)
COLOR_MOUTH = (57, 99, 55)          # #396337
COLOR_TONGUE = (162, 178, 106)      # #A2B26A
COLOR_HIGHLIGHT = (255, 255, 255)
COLOR_BLUSH = (255, 200, 216)

# ── Mood alias ───────────────────────────────────────────────
# 같은 표정 파일을 공유하는 mood들. 밝기(opacity)는 caller가 제어.
# 예) inactive == sleepy 표정 + dim overlay (Away+Idle에서 사용)
_MOOD_ALIASES = {
    "inactive": "sleepy",
}


# ── Figma 비율 (코드 fallback용) ─────────────────────────────
_EYE_CY = 0.376
_EYE_LEFT_CX = 0.261
_EYE_RIGHT_CX = 0.739
_EYE_W = 0.059
_EYE_H = 0.120
_MOUTH_CX = 0.500
_MOUTH_CY = 0.687
_MOUTH_W = 0.113
_MOUTH_H = 0.074


@dataclass
class BlinkConfig:
    min_interval: float = 2.0
    max_interval: float = 6.0
    close_duration: float = 0.06
    hold_duration: float = 0.04
    open_duration: float = 0.10


@dataclass
class BreathingConfig:
    amplitude: float = 0.012
    period: float = 4.0
    y_shift_px: float = 3.0


# ── Blink controller ─────────────────────────────────────────

class _BlinkState:
    OPEN = 0
    CLOSING = 1
    HOLD = 2
    OPENING = 3


class _BlinkController:
    def __init__(self, config: BlinkConfig) -> None:
        self._cfg = config
        self._state = _BlinkState.OPEN
        self._phase_start = time.monotonic()
        self._next_blink = self._schedule()

    def _schedule(self) -> float:
        return time.monotonic() + random.uniform(
            self._cfg.min_interval, self._cfg.max_interval
        )

    def tick(self) -> float:
        """Return eye Y-scale [0.05 .. 1.0]."""
        now = time.monotonic()
        dt = now - self._phase_start

        if self._state == _BlinkState.OPEN:
            if now >= self._next_blink:
                self._state = _BlinkState.CLOSING
                self._phase_start = now
            return 1.0

        if self._state == _BlinkState.CLOSING:
            t = min(1.0, dt / self._cfg.close_duration)
            if t >= 1.0:
                self._state = _BlinkState.HOLD
                self._phase_start = now
            return max(0.05, 1.0 - t * 0.95)

        if self._state == _BlinkState.HOLD:
            if dt >= self._cfg.hold_duration:
                self._state = _BlinkState.OPENING
                self._phase_start = now
            return 0.05

        # OPENING
        t = min(1.0, dt / self._cfg.open_duration)
        if t >= 1.0:
            self._state = _BlinkState.OPEN
            self._phase_start = now
            self._next_blink = self._schedule()
        return 0.05 + t * 0.95


# ── Oneshot transition ───────────────────────────────────────

@dataclass
class _OneshotTransition:
    """진행 중인 oneshot 전환 애니메이션."""
    from_mood: str
    to_mood: str
    started_at: float
    duration: float          # 전체 지속 (초)
    fade_in: float = 0.15    # 진입 fade 시간
    fade_out: float = 0.20   # 퇴장 fade 시간


# ── Face Compositor ──────────────────────────────────────────

class FaceCompositor:
    """BMO 얼굴 합성기.

    이미지 모드: assets/expressions/<mood>.png blit
    코드 모드 (fallback): pygame 벡터 드로잉
    """

    def __init__(
        self,
        width: int = 1024,
        height: int = 600,
        blink_config: Optional[BlinkConfig] = None,
        breathing_config: Optional[BreathingConfig] = None,
    ) -> None:
        self._w = width
        self._h = height
        self._blink = _BlinkController(blink_config or BlinkConfig())
        self._breath = breathing_config or BreathingConfig()

        # 코드 fallback 좌표
        self._eye_left_cx = int(width * _EYE_LEFT_CX)
        self._eye_right_cx = int(width * _EYE_RIGHT_CX)
        self._eye_cy = int(height * _EYE_CY)
        self._eye_w = int(width * _EYE_W)
        self._eye_h = int(height * _EYE_H)
        self._mouth_cx = int(width * _MOUTH_CX)
        self._mouth_cy = int(height * _MOUTH_CY)
        self._mouth_w = int(width * _MOUTH_W)
        self._mouth_h = int(height * _MOUTH_H)
        self._saccade_max = int(self._eye_w * 0.5)

        # 상태
        self._mood = "calm"
        self._saccade_x = 0.0
        self._saccade_y = 0.0
        self._opacity = 1.0
        self._start_time = time.monotonic()

        # 이미지 에셋
        self._images: Dict[str, "pygame.Surface"] = {}
        self._has_images = False

        # oneshot 전환
        self._transition: Optional[_OneshotTransition] = None

    # ── 에셋 로딩 ──────────────────────────────────────────────

    def load_assets(self, faces_dir: Path) -> None:
        """assets/expressions/ 에서 PNG 로딩."""
        if pygame is None:
            return

        self._images.clear()
        if not faces_dir.exists():
            return

        for png in faces_dir.glob("*.png"):
            name = png.stem  # e.g. "calm", "startled"
            try:
                img = pygame.image.load(str(png)).convert_alpha()
                if img.get_size() != (self._w, self._h):
                    img = pygame.transform.smoothscale(img, (self._w, self._h))
                self._images[name] = img
            except Exception as e:
                print(f"  WARN  이미지 로딩 실패: {png.name} ({e})")

        self._has_images = len(self._images) > 0
        if self._has_images:
            print(f"  OK    표정 이미지 {len(self._images)}개 로딩: {sorted(self._images.keys())}")

    def has_assets(self) -> bool:
        return self._has_images

    def get_loaded_moods(self) -> list:
        return sorted(self._images.keys())

    # ── 상태 업데이트 ──────────────────────────────────────────

    def set_mood(self, mood: str) -> None:
        # alias 해석: inactive → sleepy (표정은 같고 밝기만 다름, opacity는 caller 제어)
        resolved = _MOOD_ALIASES.get(mood, mood)
        old = self._mood
        self._mood = resolved
        # oneshot 전환 감지
        if old != resolved and old in self._images and resolved in self._images:
            self._transition = _OneshotTransition(
                from_mood=old,
                to_mood=resolved,
                started_at=time.monotonic(),
                duration=0.35,
            )

    def set_saccade(self, x: float, y: float) -> None:
        self._saccade_x = max(-1.0, min(1.0, x))
        self._saccade_y = max(-1.0, min(1.0, y))

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.0, min(1.0, opacity))

    # ── 메인 렌더 ──────────────────────────────────────────────

    def render(self, target: "pygame.Surface") -> None:
        if pygame is None:
            return

        now = time.monotonic()
        blink_y_scale = self._blink.tick()

        # breathing
        breath_phase = ((now - self._start_time) / self._breath.period) * 2 * math.pi
        breath_scale = 1.0 + self._breath.amplitude * math.sin(breath_phase)
        breath_y_shift = self._breath.y_shift_px * math.sin(breath_phase)

        # 이미지 모드
        if self._has_images and self._mood in self._images:
            self._render_image(target, now, breath_scale, breath_y_shift, blink_y_scale)
        else:
            # 코드 fallback
            self._render_code(target, blink_y_scale, breath_scale, breath_y_shift)

    def _render_image(
        self,
        target: "pygame.Surface",
        now: float,
        breath_scale: float,
        breath_y_shift: float,
        blink_y_scale: float,
    ) -> None:
        """이미지 기반 렌더링."""
        target.fill(COLOR_BG)

        img = self._images[self._mood]

        # cross-fade 전환 처리
        if self._transition is not None:
            t = (now - self._transition.started_at) / self._transition.duration
            if t >= 1.0:
                self._transition = None
            else:
                old_img = self._images.get(self._transition.from_mood)
                if old_img is not None:
                    alpha_old = max(0, int(255 * (1.0 - t)))
                    alpha_new = min(255, int(255 * t))

                    surf_old = old_img.copy()
                    surf_old.set_alpha(alpha_old)

                    surf_new = img.copy()
                    surf_new.set_alpha(alpha_new)

                    self._blit_with_breathing(target, surf_old, breath_scale, breath_y_shift)
                    self._blit_with_breathing(target, surf_new, breath_scale, breath_y_shift)

                    # dim
                    if self._opacity < 1.0:
                        self._apply_dim(target)
                    return

        # 단일 이미지 blit
        surf = img
        if self._opacity < 1.0:
            surf = img.copy()
            surf.set_alpha(int(255 * self._opacity))

        self._blit_with_breathing(target, surf, breath_scale, breath_y_shift)

        # dim overlay
        if self._opacity < 1.0:
            self._apply_dim(target)

        # blink overlay (이미지 위에 눈 영역 가림)
        if blink_y_scale < 0.9 and self._mood in ("calm", "attentive"):
            self._render_image_blink(target, blink_y_scale)

    def _blit_with_breathing(
        self,
        target: "pygame.Surface",
        surf: "pygame.Surface",
        breath_scale: float,
        breath_y_shift: float,
    ) -> None:
        """breathing 효과 적용하여 blit."""
        if abs(breath_scale - 1.0) < 0.002:
            # 거의 차이 없으면 그냥 blit
            y_off = int(breath_y_shift)
            target.blit(surf, (0, y_off))
        else:
            new_w = int(self._w * breath_scale)
            new_h = int(self._h * breath_scale)
            scaled = pygame.transform.smoothscale(surf, (new_w, new_h))
            x_off = (self._w - new_w) // 2
            y_off = (self._h - new_h) // 2 + int(breath_y_shift)
            target.blit(scaled, (x_off, y_off))

    def _render_image_blink(
        self, target: "pygame.Surface", blink_y_scale: float,
    ) -> None:
        """이미지 모드 blink: 눈 영역에 배경색 바를 오버레이."""
        close_ratio = 1.0 - blink_y_scale  # 0=열림, 1=완전감김
        eye_h = int(self._h * _EYE_H * 1.4)
        bar_h = int(eye_h * close_ratio)
        if bar_h < 2:
            return

        for cx_ratio in (_EYE_LEFT_CX, _EYE_RIGHT_CX):
            cx = int(self._w * cx_ratio)
            cy = int(self._h * _EYE_CY)
            eye_w = int(self._w * _EYE_W * 1.6)
            bar_rect = pygame.Rect(
                cx - eye_w // 2, cy - bar_h // 2,
                eye_w, bar_h,
            )
            pygame.draw.rect(target, COLOR_BG, bar_rect)

    def _apply_dim(self, target: "pygame.Surface") -> None:
        """화면 전체 어둡게."""
        dim_alpha = int(255 * (1.0 - self._opacity))
        overlay = pygame.Surface((self._w, self._h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, dim_alpha))
        target.blit(overlay, (0, 0))

    # ── 코드 fallback (기존 벡터 드로잉) ──────────────────────

    def _render_code(
        self, target: "pygame.Surface",
        blink_y_scale: float, breath_scale: float, breath_y_shift: float,
    ) -> None:
        sx = self._saccade_x * self._saccade_max
        sy = self._saccade_y * self._saccade_max * 0.6

        bg = COLOR_BG
        if self._opacity < 1.0:
            bg = tuple(int(c * self._opacity) for c in COLOR_BG)
        target.fill(bg)

        ey = self._eye_cy + int(breath_y_shift)
        self._draw_eyes(
            target,
            left_cx=self._eye_left_cx + int(sx),
            right_cx=self._eye_right_cx + int(sx),
            cy=ey + int(sy),
            blink=blink_y_scale, breath=breath_scale,
        )

        my = self._mouth_cy + int(breath_y_shift)
        self._draw_mouth(target, cx=self._mouth_cx, cy=my, breath=breath_scale)

        if self._mood in ("happy", "welcome"):
            self._draw_blush(target, ey + int(sy))

    # ── 눈 (코드) ─────────────────────────────────────────────

    def _draw_eyes(self, target, left_cx, right_cx, cy, blink, breath):
        mood = self._mood
        for cx in (left_cx, right_cx):
            if mood in ("happy", "welcome"):
                self._draw_eye_happy(target, cx, cy, breath)
            elif mood == "sleepy":
                self._draw_eye_sleepy(target, cx, cy, breath)
            elif mood in ("startled", "alert"):
                self._draw_eye_wide(target, cx, cy, blink, breath)
            elif mood == "confused":
                is_left = (cx == left_cx)
                self._draw_eye_confused(target, cx, cy, blink, breath, is_left)
            else:
                self._draw_eye_normal(target, cx, cy, blink, breath)

    def _draw_eye_normal(self, target, cx, cy, blink, breath):
        w = int(self._eye_w * breath)
        h = max(3, int(self._eye_h * blink * breath))
        rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        pygame.draw.ellipse(target, COLOR_EYE, rect)
        if blink > 0.5:
            hl_r = max(2, w // 5)
            pygame.draw.circle(target, COLOR_HIGHLIGHT, (cx - w // 4, cy - h // 4), hl_r)

    def _draw_eye_happy(self, target, cx, cy, breath):
        w = int(self._eye_w * breath * 1.1)
        h = int(self._eye_h * breath * 0.5)
        thickness = max(4, self._eye_w // 8)
        rect = pygame.Rect(cx - w // 2, cy - h, w, h * 2)
        pygame.draw.arc(target, COLOR_EYE, rect, 0.15, math.pi - 0.15, thickness)

    def _draw_eye_sleepy(self, target, cx, cy, breath):
        w = int(self._eye_w * breath)
        h = max(3, int(self._eye_h * 0.2 * breath))
        rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        pygame.draw.ellipse(target, COLOR_EYE, rect)

    def _draw_eye_closed(self, target, cx, cy):
        w = int(self._eye_w * 0.9)
        thickness = max(3, self._eye_w // 10)
        pygame.draw.line(target, COLOR_EYE, (cx - w // 2, cy), (cx + w // 2, cy), thickness)

    def _draw_eye_wide(self, target, cx, cy, blink, breath):
        r = int(self._eye_w * breath * 0.75)
        h_scale = max(0.3, blink)
        pygame.draw.circle(target, COLOR_HIGHLIGHT, (cx, cy), r)
        pygame.draw.circle(target, COLOR_EYE, (cx, cy), r, max(3, r // 8))
        pupil_r = max(3, int(r * 0.45 * h_scale))
        pygame.draw.circle(target, COLOR_EYE, (cx, cy), pupil_r)
        hl_r = max(2, r // 5)
        pygame.draw.circle(target, COLOR_HIGHLIGHT, (cx - r // 3, cy - r // 3), hl_r)

    def _draw_eye_confused(self, target, cx, cy, blink, breath, is_left):
        if is_left:
            self._draw_eye_normal(target, cx, cy, blink, breath)
        else:
            w = int(self._eye_w * breath * 0.7)
            h = max(3, int(self._eye_h * blink * breath * 0.7))
            rect = pygame.Rect(cx - w // 2, cy - h // 2 - 5, w, h)
            pygame.draw.ellipse(target, COLOR_EYE, rect)

    # ── 입 (코드) ──────────────────────────────────────────────

    def _draw_mouth(self, target, cx, cy, breath):
        mood = self._mood
        if mood in ("happy", "welcome"):
            self._draw_mouth_smile(target, cx, cy, breath)
        elif mood in ("startled", "alert"):
            self._draw_mouth_o(target, cx, cy, breath)
        elif mood == "confused":
            self._draw_mouth_zigzag(target, cx, cy, breath)
        elif mood == "sleepy":
            self._draw_mouth_sleepy(target, cx, cy, breath)
        else:
            self._draw_mouth_neutral(target, cx, cy, breath)

    def _draw_mouth_neutral(self, target, cx, cy, breath):
        w = int(self._mouth_w * breath * 0.7)
        thickness = max(4, self._mouth_h // 8)
        pygame.draw.line(target, COLOR_MOUTH, (cx - w // 2, cy), (cx + w // 2, cy), thickness)

    def _draw_mouth_smile(self, target, cx, cy, breath):
        w = int(self._mouth_w * breath * 1.8)
        h = int(self._mouth_h * breath * 0.8)
        thickness = max(4, self._mouth_h // 7)
        rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        pygame.draw.arc(target, COLOR_MOUTH, rect, math.pi + 0.2, -0.2, thickness)

    def _draw_mouth_o(self, target, cx, cy, breath):
        rw = int(self._mouth_w * breath * 0.35)
        rh = int(self._mouth_h * breath * 0.7)
        rect = pygame.Rect(cx - rw, cy - rh, rw * 2, rh * 2)
        pygame.draw.ellipse(target, COLOR_MOUTH, rect, max(4, rw // 4))

    def _draw_mouth_zigzag(self, target, cx, cy, breath):
        w = int(self._mouth_w * breath * 1.2)
        seg_h = int(self._mouth_h * 0.3)
        thickness = max(4, self._mouth_h // 8)
        x_start = cx - w // 2
        segs = 5
        seg_w = w // segs
        points = []
        for i in range(segs + 1):
            px = x_start + i * seg_w
            py = cy + (seg_h if i % 2 == 0 else -seg_h)
            points.append((px, py))
        if len(points) >= 2:
            pygame.draw.lines(target, COLOR_MOUTH, False, points, thickness)

    def _draw_mouth_sleepy(self, target, cx, cy, breath):
        w = int(self._mouth_w * breath * 0.4)
        thickness = max(3, self._mouth_h // 10)
        pygame.draw.line(target, COLOR_MOUTH, (cx - w // 2, cy), (cx + w // 2, cy), thickness)
        try:
            font_size = max(14, self._mouth_h // 2)
            now = time.monotonic()
            bob = int(3 * math.sin(now * 1.5))
            for i, ch in enumerate("Zzz"):
                size = max(10, font_size - i * 4)
                f = pygame.font.SysFont("consolas", size)
                s = f.render(ch, True, COLOR_MOUTH)
                zx = cx + self._mouth_w + i * (size + 2)
                zy = cy - 30 - i * (size + 2) + bob
                target.blit(s, (zx, zy))
        except Exception:
            pass

    def _draw_blush(self, target, eye_cy):
        blush_w = int(self._eye_w * 1.2)
        blush_h = int(self._eye_w * 0.5)
        blush_y = eye_cy + self._eye_h
        alpha_surf = pygame.Surface((blush_w, blush_h), pygame.SRCALPHA)
        pygame.draw.ellipse(alpha_surf, (*COLOR_BLUSH, 100), (0, 0, blush_w, blush_h))
        for cx in (self._eye_left_cx, self._eye_right_cx):
            target.blit(alpha_surf, (cx - blush_w // 2, blush_y - blush_h // 2))
