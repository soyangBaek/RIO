"""RIO 상태 머신 GUI 데모 – 클릭으로 직접 상태 전환.

FSM 노드를 클릭하면 해당 상태로 즉시 전환되고,
Scene Selector 가 Mood / UI 를 실시간 파생.
실행: py tools/state_gui.py
"""
import math
import random
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

sys.path.insert(0, ".")

from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.scene_selector import derive_scene
from src.app.core.state.store import ActiveOneshot, Store

# ── 색상 팔레트 ──────────────────────────────────────────────
BG = "#1e1e2e"
BG_CARD = "#2a2a3e"
BG_BTN = "#363650"
BG_BTN_HOVER = "#45475a"
FG = "#cdd6f4"
FG_DIM = "#6c7086"
ACCENT = "#89b4fa"

CONTEXT_COLORS = {
    "Away": "#6c7086", "Idle": "#89dceb", "Engaged": "#a6e3a1", "Sleepy": "#f9e2af",
}
ACTIVITY_COLORS = {
    "Idle": "#89dceb", "Listening": "#89b4fa", "Executing": "#cba6f7", "Alerting": "#f38ba8",
}
MOOD_COLORS = {
    "alert": "#f38ba8", "startled": "#f38ba8", "happy": "#a6e3a1", "welcome": "#a6e3a1",
    "confused": "#f9e2af", "attentive": "#89b4fa", "calm": "#89dceb",
    "sleepy": "#6c7086", "inactive": "#6c7086",
}
UI_COLORS = {
    "NormalFace": "#89dceb", "NormalFace(dim)": "#6c7086", "ListeningUI": "#89b4fa",
    "CameraUI": "#cba6f7", "GameUI": "#f9e2af", "SleepUI": "#6c7086", "AlertUI": "#f38ba8",
}

ONESHOT_DURATIONS = {
    "startled": 600, "confused": 800, "welcome": 1500, "happy": 1000,
}
ONESHOT_PRIORITIES = {
    "startled": 30, "confused": 25, "welcome": 20, "happy": 20,
}

# Mood → face PNG 매핑
FACE_DIR = Path(__file__).resolve().parent.parent / "face"
MOOD_FACE_MAP = {
    "alert": "surprise_angry.png",
    "startled": "surprise.png",
    "happy": "smile.png",
    "welcome": "love.png",
    "confused": "surprise_angry.png",
    "attentive": "idle.png",
    "calm": "idle.png",
    "sleepy": "sleep.png",
    "inactive": "sleep.png",
}

# 얼굴별 눈 위치/크기 (픽셀 절대값: lcx, lcy, rcx, rcy, hw, hh)
# 이미지 원본 크기 기준의 눈 중심(cx,cy)과 반폭(hw), 반높이(hh)
FACE_EYE_POS = {
    #                    lcx   lcy   rcx    rcy   hw    hh     img size
    "idle.png":         (103,   81,  181.5,  81,  39,   29),  # 287x155
    "smile.png":        (104,   87,  182.5,  87,  40,   36),  # 291x156
    "sleep.png":        (100,   76,  186.5,  76,  43,   30),  # 288x156
    "dance.png":        (123,  120,  163.5, 120,  20,   20),  # 288x156
    "surprise.png":     (90.5, 80.5, 195.5, 80.5, 51.5, 55.5), # 286x161
    "surprise_angry.png":(100.5, 75, 181.5,  75,  41.5, 47),  # 287x157
    "love.png":         (72,   80.5, 214.5, 80.5, 71,   61.5), # 289x159
}
# 각 이미지의 원본 크기 (스케일 계산용)
FACE_IMG_SIZE = {
    "idle.png": (287, 155), "smile.png": (291, 156), "sleep.png": (288, 156),
    "dance.png": (288, 156), "surprise.png": (286, 161), "surprise_angry.png": (287, 157),
    "love.png": (289, 159),
}


class StateGUI:
    def __init__(self):
        self.store = Store()

        self.root = tk.Tk()
        self.root.title("RIO 상태 머신 데모")
        self.root.configure(bg=BG)
        self.root.geometry("1024x600")
        self.root.minsize(800, 500)

        # Fonts
        self.fn_title = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.fn_section = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.fn_node = tkfont.Font(family="Consolas", size=10, weight="bold")
        self.fn_label = tkfont.Font(family="Segoe UI", size=8)
        self.fn_result = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.fn_result_label = tkfont.Font(family="Segoe UI", size=8)
        self.fn_log = tkfont.Font(family="Consolas", size=8)

        self._face_images = {}
        self._load_face_images()

        # 애니메이션 상태
        self._anim_tick = 0
        self._blink_phase = 0       # 0=열림, 1~4=닫히는중, 5=감김, 6~9=열리는중
        self._next_blink = 0         # 다음 깜박임 틱
        self._current_face = "idle.png"
        self._current_mood = "calm"

        self._build_ui()
        self._refresh()
        self._schedule_animation()

    def _load_face_images(self):
        """face/ 폴더의 PNG를 tk.PhotoImage로 미리 로드."""
        for png_file in FACE_DIR.glob("*.png"):
            try:
                img = tk.PhotoImage(file=str(png_file))
                self._face_images[png_file.name] = img
            except tk.TclError:
                pass

    def _build_ui(self):
        # ── 좌우 패널 분할 ───────────────────────────────────
        main_pane = tk.Frame(self.root, bg=BG)
        main_pane.pack(fill="both", expand=True, padx=10, pady=4)

        # 왼쪽: 조작 패널
        left = tk.Frame(main_pane, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        # 오른쪽: 미리보기 패널
        right = tk.Frame(main_pane, bg=BG, width=320)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        self._left = left
        self._right = right

        # ── Title ────────────────────────────────────────────
        tk.Label(
            left, text="RIO State Machine", font=self.fn_title,
            bg=BG, fg=ACCENT, pady=4,
        ).pack(fill="x", padx=10)

        # ── Context FSM ─────────────────────────────────────
        self._make_section("Context State", left)
        ctx_frame = tk.Frame(left, bg=BG)
        ctx_frame.pack(fill="x", padx=10, pady=(0, 3))
        self.ctx_btns = {}
        for name in ["Away", "Idle", "Engaged", "Sleepy"]:
            btn = tk.Button(
                ctx_frame, text=name, font=self.fn_node,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=6, pady=4, cursor="hand2",
                command=lambda n=name: self._set_context(n),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.ctx_btns[name] = btn

        # ── Activity FSM ────────────────────────────────────
        self._make_section("Activity State", left)
        act_frame = tk.Frame(left, bg=BG)
        act_frame.pack(fill="x", padx=10, pady=(0, 3))
        self.act_btns = {}
        for name in ["Idle", "Listening", "Executing", "Alerting"]:
            btn = tk.Button(
                act_frame, text=name, font=self.fn_node,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=6, pady=4, cursor="hand2",
                command=lambda n=name: self._set_activity(n),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.act_btns[name] = btn

        # ── Executing Kind ──────────────────────────────────
        self._make_section("Executing Kind", left)
        ek_frame = tk.Frame(left, bg=BG)
        ek_frame.pack(fill="x", padx=10, pady=(0, 3))
        self.ek_btns = {}
        for kind in ["없음", "weather", "photo", "smarthome", "timer_setup", "game", "dance"]:
            btn = tk.Button(
                ek_frame, text=kind, font=self.fn_label,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=4, pady=3, cursor="hand2",
                command=lambda k=kind: self._set_exec_kind(k),
            )
            btn.pack(side="left", padx=1, expand=True, fill="x")
            self.ek_btns[kind] = btn

        # ── Oneshot ─────────────────────────────────────────
        self._make_section("Oneshot", left)
        os_frame = tk.Frame(left, bg=BG)
        os_frame.pack(fill="x", padx=10, pady=(0, 3))
        self.os_btns = {}
        for name in ["없음", "startled", "confused", "welcome", "happy"]:
            btn = tk.Button(
                os_frame, text=name, font=self.fn_label,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=6, pady=3, cursor="hand2",
                command=lambda n=name: self._set_oneshot(n),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.os_btns[name] = btn

        # ── Face toggle ─────────────────────────────────────
        self._make_section("Face", left)
        face_frame = tk.Frame(left, bg=BG)
        face_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.face_btn = tk.Button(
            face_frame, text="○ 얼굴 없음", font=self.fn_node,
            bg="#45475a", fg="#f38ba8", activebackground=BG_BTN_HOVER, activeforeground=FG,
            bd=0, padx=10, pady=4, cursor="hand2",
            command=self._toggle_face,
        )
        self.face_btn.pack(fill="x")

        # ── 구분선 ──────────────────────────────────────────
        tk.Frame(left, bg="#45475a", height=2).pack(fill="x", padx=10, pady=4)

        # ── 파생 결과 (Mood + UI) ───────────────────────────
        result_frame = tk.Frame(left, bg=BG)
        result_frame.pack(fill="x", padx=10, pady=(2, 3))

        # Mood
        mood_cell = tk.Frame(result_frame, bg=BG_CARD, padx=10, pady=6)
        mood_cell.pack(side="left", expand=True, fill="both", padx=2)
        tk.Label(mood_cell, text="Mood", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.mood_label = tk.Label(mood_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.mood_label.pack(anchor="w")

        # UI
        ui_cell = tk.Frame(result_frame, bg=BG_CARD, padx=10, pady=6)
        ui_cell.pack(side="left", expand=True, fill="both", padx=2)
        tk.Label(ui_cell, text="UI Layout", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.ui_label = tk.Label(ui_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.ui_label.pack(anchor="w")

        # ── 로그 ────────────────────────────────────────────
        log_frame = tk.Frame(left, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(2, 4))
        tk.Label(log_frame, text="변경 로그", font=self.fn_section, bg=BG, fg=FG_DIM, anchor="w").pack(fill="x")
        self.log_text = tk.Text(
            log_frame, font=self.fn_log, bg="#181825", fg=FG,
            insertbackground=FG, bd=0, padx=6, pady=4,
            state="disabled", height=5, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("change", foreground="#a6e3a1")
        self.log_text.tag_configure("dim", foreground=FG_DIM)
        self.log_text.tag_configure("accent", foreground=ACCENT)

        # ── 리셋 버튼 ───────────────────────────────────────
        tk.Button(
            left, text="↺ 초기화", font=self.fn_label,
            bg="#45475a", fg="#f9e2af", activebackground=BG_BTN_HOVER, activeforeground=FG,
            bd=0, padx=10, pady=4, cursor="hand2",
            command=self._reset,
        ).pack(pady=(0, 4))

        # ── 오른쪽: Face Preview (Canvas 애니메이션) ─────────
        tk.Label(
            right, text="Face Preview", font=self.fn_title,
            bg=BG, fg=ACCENT, pady=4,
        ).pack(fill="x")

        self.face_canvas = tk.Canvas(
            right, bg=BG_CARD, bd=0, highlightthickness=0,
            width=300, height=400,
        )
        self.face_canvas.pack(fill="both", expand=True, pady=(4, 4))
        self._face_canvas_img = None  # canvas image item id
        self._blink_rects = []        # blink overlay rect ids

        self.face_name_label = tk.Label(
            right, text="", font=self.fn_label,
            bg=BG, fg=ACCENT,
        )
        self.face_name_label.pack(pady=(0, 4))

    def _make_section(self, text, parent=None):
        if parent is None:
            parent = self.root
        tk.Label(
            parent, text=text, font=self.fn_section,
            bg=BG, fg=FG_DIM, anchor="w", padx=10,
        ).pack(fill="x", pady=(4, 1))

    # ── 상태 변경 핸들러 ─────────────────────────────────────
    def _set_context(self, name):
        prev = self.store.context_state.value
        self.store.context_state = ContextState(name)
        if name == "Away":
            self.store.away_started_at = time.time()
        self._log(f"Context: {prev} → {name}")
        self._refresh()

    def _set_activity(self, name):
        prev = self.store.activity_state.value
        self.store.activity_state = ActivityState(name)
        if name != "Executing":
            self.store.active_executing_kind = None
        self._log(f"Activity: {prev} → {name}")
        self._refresh()

    def _set_exec_kind(self, kind):
        if kind == "없음":
            self.store.active_executing_kind = None
            self._log("ExecKind: 해제")
        else:
            self.store.active_executing_kind = ExecutingKind(kind)
            if self.store.activity_state != ActivityState.EXECUTING:
                self.store.activity_state = ActivityState.EXECUTING
            self._log(f"ExecKind: {kind}")
        self._refresh()

    def _set_oneshot(self, name):
        if name == "없음":
            self.store.active_oneshot = None
            self._log("Oneshot: 해제")
        else:
            os_name = OneshotName(name)
            self.store.active_oneshot = ActiveOneshot(
                name=os_name,
                priority=ONESHOT_PRIORITIES[name],
                started_at=time.time(),
                duration_ms=ONESHOT_DURATIONS[name],
            )
            self._log(f"Oneshot: {name} (pri={ONESHOT_PRIORITIES[name]})")
        self._refresh()

    def _toggle_face(self):
        self.store.face_present = not self.store.face_present
        if self.store.face_present:
            self.store.last_face_seen_at = time.time()
        self._log(f"Face: {'감지됨' if self.store.face_present else '없음'}")
        self._refresh()

    def _reset(self):
        self.store = Store()
        self._log("── 초기화 ──")
        self._refresh()

    # ── 로그 ─────────────────────────────────────────────────
    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"▸ {msg}\n", "change")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ── 화면 갱신 ────────────────────────────────────────────
    def _refresh(self):
        s = self.store
        mood, ui = derive_scene(
            s.context_state, s.activity_state,
            s.active_oneshot, s.active_executing_kind,
        )

        ctx_val = s.context_state.value
        act_val = s.activity_state.value
        ek_val = s.active_executing_kind.value if s.active_executing_kind else "없음"
        os_val = s.active_oneshot.name.value if s.active_oneshot else "없음"

        # Context buttons
        for name, btn in self.ctx_btns.items():
            if name == ctx_val:
                btn.configure(bg=CONTEXT_COLORS[name], fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        # Activity buttons
        for name, btn in self.act_btns.items():
            if name == act_val:
                btn.configure(bg=ACTIVITY_COLORS[name], fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        # ExecKind buttons
        for kind, btn in self.ek_btns.items():
            if kind == ek_val:
                btn.configure(bg="#cba6f7", fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        # Oneshot buttons
        for name, btn in self.os_btns.items():
            if name == os_val:
                btn.configure(bg="#cba6f7", fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        # Face
        if s.face_present:
            self.face_btn.configure(text="● 얼굴 감지됨", bg="#a6e3a1", fg="#1e1e2e")
        else:
            self.face_btn.configure(text="○ 얼굴 없음", bg="#45475a", fg="#f38ba8")

        # Derived results
        self.mood_label.configure(text=mood.value, fg=MOOD_COLORS.get(mood.value, FG))
        self.ui_label.configure(text=ui.value, fg=UI_COLORS.get(ui.value, FG))

        # Face image – dance 모드이면 dance.png, 아니면 mood 기반
        ek = s.active_executing_kind
        if ek and ek.value == "dance":
            face_file = "dance.png"
        else:
            face_file = MOOD_FACE_MAP.get(mood.value, "idle.png")

        self._current_face = face_file
        self._current_mood = mood.value
        self._update_face_canvas()
        self.face_name_label.configure(text=face_file)

    # ── 얼굴 Canvas 갱신 ──────────────────────────────────
    def _update_face_canvas(self):
        face_img = self._face_images.get(self._current_face)
        if not face_img:
            return
        cw = self.face_canvas.winfo_width() or 300
        ch = self.face_canvas.winfo_height() or 400
        cx, cy = cw // 2, ch // 2

        # 호흡 애니메이션 (상하 오실레이션)
        is_dance = self._current_mood == "happy" and \
            self.store.active_executing_kind and \
            self.store.active_executing_kind.value == "dance"

        if is_dance:
            dy = int(8 * math.sin(self._anim_tick * 0.5))
            dx = int(6 * math.sin(self._anim_tick * 0.7))
        elif self._current_mood in ("sleepy", "inactive"):
            dy = int(2 * math.sin(self._anim_tick * 0.08))
            dx = 0
        else:
            dy = int(3 * math.sin(self._anim_tick * 0.15))
            dx = 0

        # Canvas 초기화 후 이미지 배치
        self.face_canvas.delete("all")
        self._face_canvas_img = self.face_canvas.create_image(
            cx + dx, cy + dy, image=face_img, anchor="center",
        )

        # 눈 깜빡임: 원래 눈 위에 배경색 타원을 덮고, 찌그러진 눈을 그림
        if self._blink_phase > 0 and self._current_face in FACE_EYE_POS:
            iw = face_img.width()
            ih = face_img.height()
            img_left = cx + dx - iw // 2
            img_top = cy + dy - ih // 2

            eye_info = FACE_EYE_POS[self._current_face]
            lcx_px, lcy_px, rcx_px, rcy_px, hw_px, hh_px = eye_info

            # 원본 이미지와 현재 표시 크기의 스케일 비율
            orig_w, orig_h = FACE_IMG_SIZE[self._current_face]
            sx = iw / orig_w
            sy = ih / orig_h

            # 깜빡임 단계에 따른 눈 세로 비율 (1.0=열림, 0.0=감김)
            blink_table = {1: 0.5, 2: 0.15, 3: 0.0, 4: 0.0, 5: 0.15, 6: 0.5}
            squish = blink_table.get(self._blink_phase, 1.0)

            # 얼굴 배경색 (초록 계열)
            face_bg = "#b4d8b4"

            for ecx_px, ecy_px in [(lcx_px, lcy_px), (rcx_px, rcy_px)]:
                # 실제 canvas 좌표로 변환
                ex = img_left + int(ecx_px * sx)
                ey = img_top + int(ecy_px * sy)
                hw = int(hw_px * sx)
                hh = int(hh_px * sy)

                # 원래 눈 덮기 (배경색 타원, 딱 맞는 크기)
                self.face_canvas.create_oval(
                    ex - hw, ey - hh, ex + hw, ey + hh,
                    fill=face_bg, outline=face_bg,
                )

                # 찌그러진 눈 그리기
                if squish > 0.05:
                    shh = max(1, int(hh * squish))
                    self.face_canvas.create_oval(
                        ex - hw, ey - shh, ex + hw, ey + shh,
                        fill="black", outline="black",
                    )
                else:
                    # 완전히 감은 눈 = 가로 선
                    line_w = max(2, hh // 5)
                    self.face_canvas.create_line(
                        ex - hw, ey, ex + hw, ey,
                        fill="black", width=line_w, capstyle="round",
                    )

    # ── 애니메이션 루프 ─────────────────────────────────
    def _schedule_animation(self):
        self._anim_tick += 1

        # 눈 깜빡임 로직 (phase 기반)
        if self._blink_phase > 0:
            self._blink_phase += 1
            if self._blink_phase > 6:
                self._blink_phase = 0
        else:
            if self._anim_tick >= self._next_blink:
                # sleepy/inactive는 깜빡임 안 함
                if self._current_mood not in ("sleepy", "inactive"):
                    self._blink_phase = 1
                # 다음 깜빡임: 2~5초 후 (40ms 틱 기준)
                self._next_blink = self._anim_tick + random.randint(50, 125)

        self._update_face_canvas()
        self.root.after(40, self._schedule_animation)  # ~25fps

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    StateGUI().run()
