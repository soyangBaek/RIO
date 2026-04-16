"""RIO Face 통합 데모 – 이미지/코드 모드 + 시나리오 재생.

실행: py tools/face_demo.py

조작:
    1-9, 0  : mood 변경 (9개 primary + secondary)
    F1-F5   : oneshot 시나리오 재생 (startled/confused/welcome/happy/photo)
    F6      : sleep → wake 시나리오
    F7      : 전체 mood 순회 (auto cycle)
    Tab     : 이미지/코드 모드 전환
    D       : dim 토글 (Away 모드)
    마우스   : 시선 추적
    ESC     : 종료
"""
import sys
import time

sys.path.insert(0, ".")

from pathlib import Path

import pygame

from src.app.adapters.display.face_compositor import FaceCompositor

WIDTH, HEIGHT = 1024, 600
ASSETS_DIR = Path("assets/expressions")

# ── Mood 목록 ────────────────────────────────────────────────

MOODS_PRIMARY = [
    (pygame.K_1, "calm", "기본 idle"),
    (pygame.K_2, "attentive", "주목/듣기"),
    (pygame.K_3, "happy", "기쁨 oneshot"),
    (pygame.K_4, "welcome", "반김 oneshot"),
    (pygame.K_5, "startled", "놀람 oneshot"),
    (pygame.K_6, "confused", "혼란 oneshot"),
    (pygame.K_7, "sleepy", "졸림"),
    (pygame.K_8, "alert", "경고/알림"),
    (pygame.K_9, "sleepy", "졸림/Away dim"),
]

MOODS_SECONDARY = [
    (pygame.K_0, "photo_ready", "사진 대기"),
    (pygame.K_MINUS, "photo_snap", "촬영 윙크"),
    (pygame.K_EQUALS, "game_face", "게임 모드"),
    (pygame.K_BACKSPACE, "dance_face", "댄스"),
]

ALL_MOODS = MOODS_PRIMARY + MOODS_SECONDARY

# ── 시나리오 정의 ────────────────────────────────────────────

def scenario_oneshot(face: FaceCompositor, oneshot_mood: str, duration: float, base: str = "calm"):
    """oneshot: base → oneshot → base 복귀."""
    return [
        (base, 0.0),
        (oneshot_mood, 0.3),
        (base, 0.3 + duration),
    ]

SCENARIOS = {
    pygame.K_F1: ("startled oneshot (~600ms)", lambda f: scenario_oneshot(f, "startled", 0.6)),
    pygame.K_F2: ("confused oneshot (~800ms)", lambda f: scenario_oneshot(f, "confused", 0.8)),
    pygame.K_F3: ("welcome oneshot (~1.5s)", lambda f: scenario_oneshot(f, "welcome", 1.5)),
    pygame.K_F4: ("happy oneshot (~1s)", lambda f: scenario_oneshot(f, "happy", 1.0)),
    pygame.K_F5: ("photo sequence", lambda f: [
        ("attentive", 0.0),
        ("photo_ready", 0.5),    # 카운트다운 시작
        ("photo_ready", 1.5),    # 3
        ("photo_ready", 2.5),    # 2
        ("photo_ready", 3.5),    # 1
        ("photo_snap", 4.0),     # 셔터!
        ("happy", 4.5),          # 성공
        ("calm", 5.5),           # 복귀
    ]),
    pygame.K_F6: ("sleep → wake", lambda f: [
        ("calm", 0.0),
        ("sleepy", 1.0),
        ("sleepy", 3.0),         # 완전 수면 (dim)
        ("welcome", 6.0),        # 재등장
        ("calm", 7.5),           # 복귀
    ]),
    pygame.K_F7: ("mood 전체 순회", lambda f: [
        (mood, i * 1.5) for i, (_, mood, _) in enumerate(ALL_MOODS)
    ] + [("calm", len(ALL_MOODS) * 1.5)]),
}


class FaceDemo:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("RIO – Face Asset Demo")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 14)
        self.font_big = pygame.font.SysFont("consolas", 18, bold=True)

        self.face = FaceCompositor(width=WIDTH, height=HEIGHT)
        self.current_mood = "calm"
        self.face.set_mood("calm")

        # 이미지 로딩 시도
        self.image_mode = False
        self._assets_loaded = False
        if ASSETS_DIR.exists():
            self.face.load_assets(ASSETS_DIR)
            if self.face.has_assets():
                self.image_mode = True
                self._assets_loaded = True

        self.dim = False
        self.scenario_active = False
        self.scenario_name = ""
        self.scenario_steps = []
        self.scenario_start = 0.0

    def toggle_mode(self):
        """이미지/코드 모드 전환."""
        if not self._assets_loaded:
            return  # 이미지 없으면 전환 불가
        self.image_mode = not self.image_mode
        self.face._has_images = self.image_mode

    def start_scenario(self, key):
        if key not in SCENARIOS:
            return
        name, builder = SCENARIOS[key]
        self.scenario_name = name
        self.scenario_steps = builder(self.face)
        self.scenario_start = time.monotonic()
        self.scenario_active = True
        # 첫 프레임 즉시 적용
        if self.scenario_steps:
            self.current_mood = self.scenario_steps[0][0]
            self.face.set_mood(self.current_mood)

    def update_scenario(self):
        if not self.scenario_active:
            return
        elapsed = time.monotonic() - self.scenario_start
        # 가장 최근 단계 적용
        current_step_mood = self.scenario_steps[0][0]
        for mood, t in self.scenario_steps:
            if elapsed >= t:
                current_step_mood = mood
            else:
                break

        if current_step_mood != self.current_mood:
            self.current_mood = current_step_mood
            self.face.set_mood(current_step_mood)

        # 시나리오 종료 확인
        last_t = self.scenario_steps[-1][1]
        if elapsed > last_t + 0.5:
            self.scenario_active = False

    def render_hud(self):
        """화면 좌측 상단 정보 표시."""
        y = 8
        # 모드 표시
        mode_str = "IMAGE" if self.image_mode else "CODE (fallback)"
        mode_color = (80, 200, 80) if self.image_mode else (200, 200, 80)
        label = self.font_big.render(f"Mode: {mode_str}", True, mode_color)
        self.screen.blit(label, (10, y))
        y += 24

        # 로드된 이미지 수
        if self.face.has_assets():
            count = len(self.face.get_loaded_moods())
            label = self.font.render(f"Loaded: {count} expressions", True, (120, 160, 120))
        else:
            label = self.font.render("No images (run prepare_assets.py)", True, (200, 100, 100))
        self.screen.blit(label, (10, y))
        y += 20

        # dim 상태
        if self.dim:
            label = self.font.render("DIM (Away mode)", True, (180, 180, 100))
            self.screen.blit(label, (10, y))
            y += 20

        # 시나리오 진행 중
        if self.scenario_active:
            elapsed = time.monotonic() - self.scenario_start
            label = self.font_big.render(
                f"Scenario: {self.scenario_name} ({elapsed:.1f}s)",
                True, (255, 200, 80),
            )
            self.screen.blit(label, (10, y))
            y += 24

        # 현재 mood
        y += 4
        label = self.font_big.render(f"Mood: {self.current_mood}", True, (200, 230, 200))
        self.screen.blit(label, (10, y))
        y += 28

        # 키 가이드
        y += 4
        guides = [
            "[1-9] primary moods  [0,-,=,BS] secondary",
            "[F1] startled  [F2] confused  [F3] welcome  [F4] happy",
            "[F5] photo seq  [F6] sleep/wake  [F7] cycle all",
            "[Tab] image/code  [D] dim  [Mouse] gaze  [ESC] quit",
        ]
        for line in guides:
            label = self.font.render(line, True, (100, 120, 100))
            self.screen.blit(label, (10, y))
            y += 16

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_TAB:
                        self.toggle_mode()
                    elif event.key == pygame.K_d:
                        self.dim = not self.dim
                        self.face.set_opacity(0.3 if self.dim else 1.0)
                    elif event.key in SCENARIOS:
                        self.start_scenario(event.key)
                    else:
                        # mood 직접 선택
                        for key, mood, _ in ALL_MOODS:
                            if event.key == key:
                                self.scenario_active = False
                                self.current_mood = mood
                                self.face.set_mood(mood)
                                break

            # 시나리오 업데이트
            self.update_scenario()

            # 마우스 → 시선
            mx, my = pygame.mouse.get_pos()
            sx = (mx / WIDTH - 0.5) * 2.0
            sy = (my / HEIGHT - 0.5) * 2.0
            self.face.set_saccade(sx, sy)

            # 렌더
            self.face.render(self.screen)
            self.render_hud()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


def main():
    demo = FaceDemo()
    demo.run()


if __name__ == "__main__":
    main()
