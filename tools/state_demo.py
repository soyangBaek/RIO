"""RIO 상태 머신 인터랙티브 데모 (develop 아키텍처).

외부 하드웨어 없이 강제 이벤트를 주입하여 상태 전이를 확인.
실행: D:\\python\\python.exe tools/state_demo.py

develop의 ReducerPipeline을 사용하여 실제 reducer 규칙을 그대로 적용.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import (
    ActionKind,
    ActivityState,
    ContextState,
    Mood,
    OneshotName,
    ReductionResult,
    UIState,
)
from src.app.core.state.reducers import ReducerPipeline
from src.app.core.state.store import RuntimeStore


# ── 주입 가능한 이벤트 목록 ──────────────────────────────────
EVENTS = [
    ("1", "얼굴 감지 (face detected)", topics.VISION_FACE_DETECTED, {"x": 0.5, "y": 0.5, "size": 0.3}),
    ("2", "얼굴 사라짐 (face lost)", topics.VISION_FACE_LOST, {}),
    ("3", "음성 시작 (voice started)", topics.VOICE_ACTIVITY_STARTED, {}),
    ("4", "음성 종료 (voice ended)", topics.VOICE_ACTIVITY_ENDED, {}),
    ("5", "날씨 인텐트 (intent: weather)", topics.VOICE_INTENT_DETECTED, {"intent": "weather.current", "raw": "오늘 날씨 어때?"}),
    ("6", "사진 인텐트 (intent: photo)", topics.VOICE_INTENT_DETECTED, {"intent": "camera.capture", "raw": "사진 찍어"}),
    ("7", "스마트홈 인텐트 (intent: smarthome)", topics.VOICE_INTENT_DETECTED, {"intent": "smarthome.light.on", "raw": "불 꺼줘", "device": "light", "action": "off"}),
    ("8", "타이머 인텐트 (intent: timer)", topics.VOICE_INTENT_DETECTED, {"intent": "timer.create", "raw": "3분 타이머", "seconds": 180}),
    ("9", "게임 인텐트 (intent: game)", topics.VOICE_INTENT_DETECTED, {"intent": "ui.game_mode.enter", "raw": "게임하자"}),
    ("10", "댄스 인텐트 (intent: dance)", topics.VOICE_INTENT_DETECTED, {"intent": "dance.start", "raw": "춤 춰"}),
    ("11", "알 수 없는 인텐트 (unknown)", topics.VOICE_INTENT_UNKNOWN, {"raw": "알아듣지 못함"}),
    ("12", "태스크 성공 (task succeeded)", topics.TASK_SUCCEEDED, {"kind": "weather"}),
    ("13", "태스크 실패 (task failed)", topics.TASK_FAILED, {"kind": "weather", "error": "timeout"}),
    ("14", "터치 탭 (tap)", topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
    ("15", "터치 쓰다듬기 (stroke)", topics.TOUCH_STROKE_DETECTED, {"direction": "left_right"}),
    ("16", "제스처 V사인 (gesture v_sign)", topics.VISION_GESTURE_DETECTED, {"gesture": "v_sign"}),
    ("17", "타이머 만료 (timer expired)", topics.TIMER_EXPIRED, {"timer_id": "demo_timer", "label": "3분 타이머"}),
    ("18", "얼굴 이동 (face moved)", topics.VISION_FACE_MOVED, {"x": 0.7, "y": 0.3}),
]


# ── 컬러 헬퍼 ────────────────────────────────────────────────
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    DIM = "\033[2m"


def color_state(state) -> str:
    name = state.value if hasattr(state, "value") else str(state)
    colors = {
        "Away": C.DIM, "Idle": C.CYAN, "Engaged": C.GREEN, "Sleepy": C.YELLOW,
        "Listening": C.BLUE, "Executing": C.MAGENTA, "Alerting": C.RED,
    }
    c = colors.get(name, C.RESET)
    return f"{c}{C.BOLD}{name}{C.RESET}"


def color_mood(mood: Mood) -> str:
    colors = {
        "alert": C.RED, "startled": C.RED, "happy": C.GREEN, "welcome": C.GREEN,
        "confused": C.YELLOW, "attentive": C.BLUE, "calm": C.CYAN,
        "sleepy": C.DIM, "inactive": C.DIM,
    }
    c = colors.get(mood.value, C.RESET)
    return f"{c}{mood.value}{C.RESET}"


def print_state(result: ReductionResult):
    """현재 상태 + 파생 scene을 출력."""
    state = result.current
    scene = result.scene

    os_str = f"{C.MAGENTA}{state.active_oneshot.name.value}{C.RESET}" if state.active_oneshot else "-"
    ak_str = f"{C.CYAN}{state.extended.active_executing_kind.value}{C.RESET}" if state.extended.active_executing_kind else "-"
    face_str = f"{C.GREEN}●{C.RESET}" if state.extended.face_present else f"{C.RED}○{C.RESET}"

    ui_str = scene.ui.value
    if scene.dimmed:
        ui_str = f"{ui_str}(dim)"
    if scene.search_indicator:
        ui_str = f"{ui_str} + search"

    print(f"""
┌──────────────────────────────────────────────────┐
│  {C.BOLD}RIO State (develop){C.RESET}                             │
├──────────────────────────────────────────────────┤
│  Context  : {color_state(state.context_state):>40s}    │
│  Activity : {color_state(state.activity_state):>40s}    │
│  ActKind  : {ak_str:>40s}    │
│  Oneshot  : {os_str:>40s}    │
│  Face     : {face_str:>40s}    │
│  Mood     : {color_mood(scene.mood):>40s}    │
│  UI       : {C.BOLD}{ui_str:>31s}{C.RESET}    │
└──────────────────────────────────────────────────┘""")


def print_transition(result: ReductionResult):
    """전이 요약 출력 (previous → current 비교)."""
    prev = result.previous
    curr = result.current
    changed = False

    if prev.context_state != curr.context_state:
        print(f"  {C.YELLOW}▸ Context{C.RESET}  {color_state(prev.context_state)} → {color_state(curr.context_state)}")
        changed = True

    if prev.activity_state != curr.activity_state:
        kind = ""
        if curr.extended.active_executing_kind:
            kind = f" ({curr.extended.active_executing_kind.value})"
        print(f"  {C.YELLOW}▸ Activity{C.RESET} {color_state(prev.activity_state)} → {color_state(curr.activity_state)}{kind}")
        changed = True

    if result.triggered_oneshot is not None:
        print(f"  {C.MAGENTA}▸ Oneshot{C.RESET}  {result.triggered_oneshot.name.value} triggered!")
        changed = True
    elif prev.active_oneshot and not curr.active_oneshot:
        print(f"  {C.DIM}▸ Oneshot{C.RESET}  {prev.active_oneshot.name.value} expired")
        changed = True

    if not changed:
        print(f"  {C.DIM}(no change){C.RESET}")


def print_menu():
    print(f"\n{C.BOLD}── Event injection ─────────────────────────────────{C.RESET}")
    for key, label, _, _ in EVENTS:
        print(f"  {C.CYAN}{key:>2}{C.RESET}. {label}")
    print(f"  {C.CYAN} s{C.RESET}. Auto-play scenario (full state tour)")
    print(f"  {C.CYAN} r{C.RESET}. Reset state")
    print(f"  {C.CYAN} q{C.RESET}. Quit")
    print(f"{C.BOLD}───────────────────────────────────────────────────{C.RESET}")


def make_event(topic: str, payload: dict) -> Event:
    return Event(
        topic=topic,
        source="demo/forced",
        timestamp=datetime.now(timezone.utc),
        payload=payload,
    )


def run_scenario(pipeline: ReducerPipeline):
    """주요 상태를 순회하는 시나리오 자동 재생."""
    steps = [
        ("🔵 1. Away → Idle (얼굴 감지)", topics.VISION_FACE_DETECTED, {"x": 0.5, "y": 0.5, "size": 0.3}),
        ("🔵 2. Idle → Engaged (터치 + 얼굴)", topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
        ("🔵 3. Idle → Listening (음성 시작)", topics.VOICE_ACTIVITY_STARTED, {}),
        ("🔵 4. Listening → Executing/weather (날씨 인텐트)", topics.VOICE_INTENT_DETECTED, {"intent": "weather.current", "raw": "날씨"}),
        ("🔵 5. Executing → Idle (태스크 성공)", topics.TASK_SUCCEEDED, {"kind": "weather"}),
        ("🔵 6. Idle → Listening (음성 시작)", topics.VOICE_ACTIVITY_STARTED, {}),
        ("🔵 7. Listening → Executing/photo (사진 인텐트)", topics.VOICE_INTENT_DETECTED, {"intent": "camera.capture", "raw": "사진"}),
        ("🔵 8. Executing → Idle (태스크 성공)", topics.TASK_SUCCEEDED, {"kind": "photo"}),
        ("🔵 9. Idle → Alerting (타이머 만료)", topics.TIMER_EXPIRED, {"timer_id": "t1", "label": "타이머"}),
        ("🔵 10. Alerting → Idle (터치 확인)", topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
        ("🔵 11. 얼굴 사라짐", topics.VISION_FACE_LOST, {}),
        ("🔵 12. 다시 음성 (startled oneshot 확인)", topics.VOICE_ACTIVITY_STARTED, {}),
    ]

    print(f"\n{C.BOLD}{C.YELLOW}═══ Starting scenario auto-play ═══{C.RESET}\n")

    for label, topic, payload in steps:
        print(f"\n{C.BOLD}{label}{C.RESET}")
        print(f"  {C.DIM}topic: {topic}{C.RESET}")
        evt = make_event(topic, payload)
        result = pipeline.process(evt)
        print_transition(result)
        print_state(result)
        time.sleep(0.3)

    print(f"\n{C.BOLD}{C.GREEN}═══ Scenario complete ═══{C.RESET}\n")


def make_pipeline() -> tuple[RuntimeStore, ReducerPipeline]:
    store = RuntimeStore()
    pipeline = ReducerPipeline(store)
    return store, pipeline


def render_current(store: RuntimeStore):
    """현재 상태를 ReductionResult 형태로 포장하여 출력."""
    from src.app.core.state.scene_selector import select_scene
    state = store.snapshot()
    scene = select_scene(
        state.context_state,
        state.activity_state,
        state.extended,
        state.active_oneshot,
    )
    # ReductionResult-like 객체 없이 직접 출력
    os_str = f"{C.MAGENTA}{state.active_oneshot.name.value}{C.RESET}" if state.active_oneshot else "-"
    ak_str = f"{C.CYAN}{state.extended.active_executing_kind.value}{C.RESET}" if state.extended.active_executing_kind else "-"
    face_str = f"{C.GREEN}●{C.RESET}" if state.extended.face_present else f"{C.RED}○{C.RESET}"
    ui_str = scene.ui.value
    if scene.dimmed:
        ui_str = f"{ui_str}(dim)"
    if scene.search_indicator:
        ui_str = f"{ui_str} + search"
    print(f"""
┌──────────────────────────────────────────────────┐
│  {C.BOLD}RIO State (develop){C.RESET}                             │
├──────────────────────────────────────────────────┤
│  Context  : {color_state(state.context_state):>40s}    │
│  Activity : {color_state(state.activity_state):>40s}    │
│  ActKind  : {ak_str:>40s}    │
│  Oneshot  : {os_str:>40s}    │
│  Face     : {face_str:>40s}    │
│  Mood     : {color_mood(scene.mood):>40s}    │
│  UI       : {C.BOLD}{ui_str:>31s}{C.RESET}    │
└──────────────────────────────────────────────────┘""")


def main():
    store, pipeline = make_pipeline()

    print(f"\n{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}║    RIO State Machine Interactive Demo (develop)  ║{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}╚══════════════════════════════════════════════════╝{C.RESET}")

    render_current(store)

    while True:
        print_menu()
        choice = input(f"  {C.BOLD}Select> {C.RESET}").strip().lower()

        if choice == "q":
            print(f"\n{C.DIM}Exiting.{C.RESET}")
            break
        elif choice == "r":
            store, pipeline = make_pipeline()
            print(f"\n{C.GREEN}State reset complete{C.RESET}")
            render_current(store)
            continue
        elif choice == "s":
            store, pipeline = make_pipeline()
            run_scenario(pipeline)
            continue

        matched = None
        for key, label, topic, payload in EVENTS:
            if choice == key:
                matched = (label, topic, payload)
                break

        if not matched:
            print(f"{C.RED}Invalid input.{C.RESET}")
            continue

        label, topic, payload = matched
        print(f"\n  {C.BOLD}Inject:{C.RESET} {label}")
        print(f"  {C.DIM}topic: {topic}{C.RESET}")

        evt = make_event(topic, payload)
        result = pipeline.process(evt)
        print_transition(result)
        print_state(result)


if __name__ == "__main__":
    main()
