"""RIO 상태 머신 GUI 데모 – 클릭으로 직접 상태 전환.

FSM 노드를 클릭하면 해당 상태로 즉시 전환되고,
Scene Selector 가 Mood / UI 를 실시간 파생.
실행: py tools/state_gui.py
"""
import sys
import time
import tkinter as tk
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


class StateGUI:
    def __init__(self):
        self.store = Store()

        self.root = tk.Tk()
        self.root.title("RIO 상태 머신 데모")
        self.root.configure(bg=BG)
        self.root.geometry("780x740")
        self.root.minsize(700, 600)

        # Fonts
        self.fn_title = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.fn_section = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.fn_node = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.fn_label = tkfont.Font(family="Segoe UI", size=10)
        self.fn_result = tkfont.Font(family="Consolas", size=16, weight="bold")
        self.fn_result_label = tkfont.Font(family="Segoe UI", size=10)
        self.fn_log = tkfont.Font(family="Consolas", size=9)

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # ── Title ────────────────────────────────────────────
        tk.Label(
            self.root, text="RIO State Machine", font=self.fn_title,
            bg=BG, fg=ACCENT, pady=12,
        ).pack(fill="x", padx=20)

        # ── Context FSM ─────────────────────────────────────
        self._make_section("Context State  (클릭하여 전환)")
        ctx_frame = tk.Frame(self.root, bg=BG)
        ctx_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.ctx_btns = {}
        for name in ["Away", "Idle", "Engaged", "Sleepy"]:
            btn = tk.Button(
                ctx_frame, text=name, font=self.fn_node,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=18, pady=8, cursor="hand2", width=10,
                command=lambda n=name: self._set_context(n),
            )
            btn.pack(side="left", padx=4, expand=True, fill="x")
            self.ctx_btns[name] = btn

        # ── Activity FSM ────────────────────────────────────
        self._make_section("Activity State  (클릭하여 전환)")
        act_frame = tk.Frame(self.root, bg=BG)
        act_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.act_btns = {}
        for name in ["Idle", "Listening", "Executing", "Alerting"]:
            btn = tk.Button(
                act_frame, text=name, font=self.fn_node,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=18, pady=8, cursor="hand2", width=10,
                command=lambda n=name: self._set_activity(n),
            )
            btn.pack(side="left", padx=4, expand=True, fill="x")
            self.act_btns[name] = btn

        # ── Executing Kind ──────────────────────────────────
        self._make_section("Executing Kind  (Executing 상태일 때 선택)")
        ek_frame = tk.Frame(self.root, bg=BG)
        ek_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.ek_btns = {}
        for kind in ["없음", "weather", "photo", "smarthome", "timer_setup", "game", "dance"]:
            btn = tk.Button(
                ek_frame, text=kind, font=self.fn_label,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=8, pady=5, cursor="hand2",
                command=lambda k=kind: self._set_exec_kind(k),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.ek_btns[kind] = btn

        # ── Oneshot ─────────────────────────────────────────
        self._make_section("Oneshot  (클릭하여 활성화/해제)")
        os_frame = tk.Frame(self.root, bg=BG)
        os_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.os_btns = {}
        for name in ["없음", "startled", "confused", "welcome", "happy"]:
            btn = tk.Button(
                os_frame, text=name, font=self.fn_label,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=12, pady=5, cursor="hand2",
                command=lambda n=name: self._set_oneshot(n),
            )
            btn.pack(side="left", padx=3, expand=True, fill="x")
            self.os_btns[name] = btn

        # ── Face toggle ─────────────────────────────────────
        self._make_section("Face")
        face_frame = tk.Frame(self.root, bg=BG)
        face_frame.pack(fill="x", padx=20, pady=(0, 10))
        self.face_btn = tk.Button(
            face_frame, text="○ 얼굴 없음", font=self.fn_node,
            bg="#45475a", fg="#f38ba8", activebackground=BG_BTN_HOVER, activeforeground=FG,
            bd=0, padx=20, pady=8, cursor="hand2",
            command=self._toggle_face,
        )
        self.face_btn.pack(fill="x")

        # ── 구분선 ──────────────────────────────────────────
        tk.Frame(self.root, bg="#45475a", height=2).pack(fill="x", padx=20, pady=6)

        # ── 파생 결과 (Mood + UI) ───────────────────────────
        result_frame = tk.Frame(self.root, bg=BG)
        result_frame.pack(fill="x", padx=20, pady=(4, 6))

        # Mood
        mood_cell = tk.Frame(result_frame, bg=BG_CARD, padx=20, pady=12)
        mood_cell.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(mood_cell, text="Mood (파생)", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.mood_label = tk.Label(mood_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.mood_label.pack(anchor="w")

        # UI
        ui_cell = tk.Frame(result_frame, bg=BG_CARD, padx=20, pady=12)
        ui_cell.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(ui_cell, text="UI Layout (파생)", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.ui_label = tk.Label(ui_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.ui_label.pack(anchor="w")

        # ── 로그 ────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        tk.Label(log_frame, text="변경 로그", font=self.fn_section, bg=BG, fg=FG_DIM, anchor="w").pack(fill="x")
        self.log_text = tk.Text(
            log_frame, font=self.fn_log, bg="#181825", fg=FG,
            insertbackground=FG, bd=0, padx=8, pady=6,
            state="disabled", height=8, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("change", foreground="#a6e3a1")
        self.log_text.tag_configure("dim", foreground=FG_DIM)
        self.log_text.tag_configure("accent", foreground=ACCENT)

        # ── 리셋 버튼 ───────────────────────────────────────
        tk.Button(
            self.root, text="↺ 초기화", font=self.fn_label,
            bg="#45475a", fg="#f9e2af", activebackground=BG_BTN_HOVER, activeforeground=FG,
            bd=0, padx=16, pady=6, cursor="hand2",
            command=self._reset,
        ).pack(pady=(0, 12))

    def _make_section(self, text):
        tk.Label(
            self.root, text=text, font=self.fn_section,
            bg=BG, fg=FG_DIM, anchor="w", padx=20,
        ).pack(fill="x", pady=(8, 2))

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

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    StateGUI().run()
