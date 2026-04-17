"""RIO 상태 머신 GUI 데모 – 클릭으로 직접 상태 전환 (develop 아키텍처).

FSM 노드를 클릭하면 해당 상태로 즉시 전환되고,
Scene Selector 가 Mood / UI 를 실시간 파생.
실행: D:\\python\\python.exe tools/state_gui.py
"""
from __future__ import annotations

import sys
import tkinter as tk
from datetime import datetime, timezone
from tkinter import font as tkfont

sys.path.insert(0, ".")

from src.app.core.state.models import (
    ActionKind,
    ActivityState,
    ContextState,
    ExtendedState,
    Mood,
    Oneshot,
    OneshotName,
    RuntimeState,
    UIState,
)
from src.app.core.state.scene_selector import select_scene

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
        # develop은 RuntimeStore/ReducerPipeline 대신 RuntimeState를 직접 조작
        # (데모 목적, reducer 우회)
        self.state = RuntimeState()

        self.root = tk.Tk()
        self.root.title("RIO State Machine Demo (develop)")
        self.root.configure(bg=BG)
        self.root.geometry("780x740")
        self.root.minsize(700, 600)

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
        tk.Label(
            self.root, text="RIO State Machine", font=self.fn_title,
            bg=BG, fg=ACCENT, pady=12,
        ).pack(fill="x", padx=20)

        # ── Context FSM ─────────────────────────────────────
        self._make_section("Context State  (click to switch)")
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
        self._make_section("Activity State  (click to switch)")
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

        # ── ActionKind (Executing Kind) ─────────────────────
        self._make_section("Action Kind  (select when Executing)")
        ak_frame = tk.Frame(self.root, bg=BG)
        ak_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.ak_btns = {}
        for kind in ["None", "weather", "photo", "smarthome", "timer_setup", "game", "dance"]:
            btn = tk.Button(
                ak_frame, text=kind, font=self.fn_label,
                bg=BG_BTN, fg=FG, activebackground=BG_BTN_HOVER, activeforeground=FG,
                bd=0, padx=8, pady=5, cursor="hand2",
                command=lambda k=kind: self._set_action_kind(k),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.ak_btns[kind] = btn

        # ── Oneshot ─────────────────────────────────────────
        self._make_section("Oneshot  (click to toggle)")
        os_frame = tk.Frame(self.root, bg=BG)
        os_frame.pack(fill="x", padx=20, pady=(0, 6))
        self.os_btns = {}
        for name in ["None", "startled", "confused", "welcome", "happy"]:
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
            face_frame, text="○ No face", font=self.fn_node,
            bg="#45475a", fg="#f38ba8", activebackground=BG_BTN_HOVER, activeforeground=FG,
            bd=0, padx=20, pady=8, cursor="hand2",
            command=self._toggle_face,
        )
        self.face_btn.pack(fill="x")

        tk.Frame(self.root, bg="#45475a", height=2).pack(fill="x", padx=20, pady=6)

        # ── 파생 결과 (Mood + UI) ───────────────────────────
        result_frame = tk.Frame(self.root, bg=BG)
        result_frame.pack(fill="x", padx=20, pady=(4, 6))

        mood_cell = tk.Frame(result_frame, bg=BG_CARD, padx=20, pady=12)
        mood_cell.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(mood_cell, text="Mood (derived)", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.mood_label = tk.Label(mood_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.mood_label.pack(anchor="w")

        ui_cell = tk.Frame(result_frame, bg=BG_CARD, padx=20, pady=12)
        ui_cell.pack(side="left", expand=True, fill="both", padx=4)
        tk.Label(ui_cell, text="UI State (derived)", font=self.fn_result_label, bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self.ui_label = tk.Label(ui_cell, text="-", font=self.fn_result, bg=BG_CARD, fg=FG)
        self.ui_label.pack(anchor="w")

        # ── 로그 ────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        tk.Label(log_frame, text="Change log", font=self.fn_section, bg=BG, fg=FG_DIM, anchor="w").pack(fill="x")
        self.log_text = tk.Text(
            log_frame, font=self.fn_log, bg="#181825", fg=FG,
            insertbackground=FG, bd=0, padx=8, pady=6,
            state="disabled", height=8, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("change", foreground="#a6e3a1")
        self.log_text.tag_configure("dim", foreground=FG_DIM)

        # ── 리셋 버튼 ───────────────────────────────────────
        tk.Button(
            self.root, text="↺ Reset", font=self.fn_label,
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
        prev = self.state.context_state.value
        self.state.context_state = ContextState(name)
        if name == "Away":
            self.state.extended.away_started_at = datetime.now(timezone.utc)
        self._log(f"Context: {prev} → {name}")
        self._refresh()

    def _set_activity(self, name):
        prev = self.state.activity_state.value
        self.state.activity_state = ActivityState(name)
        if name != "Executing":
            self.state.extended.active_executing_kind = None
        self._log(f"Activity: {prev} → {name}")
        self._refresh()

    def _set_action_kind(self, kind):
        if kind == "None":
            self.state.extended.active_executing_kind = None
            self._log("ActionKind: cleared")
        else:
            self.state.extended.active_executing_kind = ActionKind(kind)
            if self.state.activity_state != ActivityState.EXECUTING:
                self.state.activity_state = ActivityState.EXECUTING
            self._log(f"ActionKind: {kind}")
        self._refresh()

    def _set_oneshot(self, name):
        if name == "None":
            self.state.active_oneshot = None
            self._log("Oneshot: cleared")
        else:
            os_name = OneshotName(name)
            self.state.active_oneshot = Oneshot(
                name=os_name,
                priority=ONESHOT_PRIORITIES[name],
                duration_ms=ONESHOT_DURATIONS[name],
                started_at=datetime.now(timezone.utc),
            )
            self._log(f"Oneshot: {name} (pri={ONESHOT_PRIORITIES[name]})")
        self._refresh()

    def _toggle_face(self):
        self.state.extended.face_present = not self.state.extended.face_present
        if self.state.extended.face_present:
            self.state.extended.last_face_seen_at = datetime.now(timezone.utc)
        self._log(f"Face: {'Detected' if self.state.extended.face_present else 'None'}")
        self._refresh()

    def _reset(self):
        self.state = RuntimeState()
        self._log("── Reset ──")
        self._refresh()

    # ── 로그 ─────────────────────────────────────────────────
    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"▸ {msg}\n", "change")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ── 화면 갱신 ────────────────────────────────────────────
    def _refresh(self):
        s = self.state
        scene = select_scene(
            s.context_state,
            s.activity_state,
            s.extended,
            s.active_oneshot,
        )

        ctx_val = s.context_state.value
        act_val = s.activity_state.value
        ak_val = s.extended.active_executing_kind.value if s.extended.active_executing_kind else "None"
        os_val = s.active_oneshot.name.value if s.active_oneshot else "None"

        for name, btn in self.ctx_btns.items():
            if name == ctx_val:
                btn.configure(bg=CONTEXT_COLORS[name], fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        for name, btn in self.act_btns.items():
            if name == act_val:
                btn.configure(bg=ACTIVITY_COLORS[name], fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        for kind, btn in self.ak_btns.items():
            if kind == ak_val:
                btn.configure(bg="#cba6f7", fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        for name, btn in self.os_btns.items():
            if name == os_val:
                btn.configure(bg="#cba6f7", fg="#1e1e2e", relief="sunken")
            else:
                btn.configure(bg=BG_BTN, fg=FG, relief="flat")

        if s.extended.face_present:
            self.face_btn.configure(text="● Face detected", bg="#a6e3a1", fg="#1e1e2e")
        else:
            self.face_btn.configure(text="○ No face", bg="#45475a", fg="#f38ba8")

        # DerivedScene: mood, ui, dimmed, search_indicator
        mood_str = scene.mood.value
        ui_str = scene.ui.value
        if scene.dimmed:
            ui_str = f"{ui_str}(dim)"
        if scene.search_indicator:
            ui_str = f"{ui_str} + search"

        self.mood_label.configure(text=mood_str, fg=MOOD_COLORS.get(mood_str, FG))
        self.ui_label.configure(text=ui_str, fg=UI_COLORS.get(scene.ui.value, FG))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    StateGUI().run()
