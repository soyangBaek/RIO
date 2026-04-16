"""RIO 상태 머신 인터랙티브 데모.

외부 하드웨어 없이 강제 이벤트를 주입하여 상태 전이를 확인.
실행: py tools/state_demo.py
"""
import sys
import time

sys.path.insert(0, ".")

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.reducers import ReducerResult, reduce
from src.app.core.state.store import Store

# ── 기본 config (thresholds.yaml 대응) ──────────────────────
DEFAULT_CONFIG = {
    "idle_timeout_sec": 120,
    "sleepy_timeout_sec": 300,
    "face_loss_grace_sec": 3,
    "engaged_face_required": True,
    "oneshots": {
        "startled": {"priority": 30, "duration_ms": 600},
        "confused": {"priority": 25, "duration_ms": 800},
        "welcome": {"priority": 20, "duration_ms": 1500},
        "happy": {"priority": 20, "duration_ms": 1000},
    },
}

# ── 주입 가능한 이벤트 목록 ──────────────────────────────────
EVENTS = [
    ("1", "얼굴 감지 (face detected)", Topics.VISION_FACE_DETECTED, {"x": 0.5, "y": 0.5, "size": 0.3}),
    ("2", "얼굴 사라짐 (face lost)", Topics.VISION_FACE_LOST, {}),
    ("3", "음성 시작 (voice started)", Topics.VOICE_ACTIVITY_STARTED, {}),
    ("4", "음성 종료 (voice ended)", Topics.VOICE_ACTIVITY_ENDED, {}),
    ("5", "날씨 인텐트 (intent: weather)", Topics.VOICE_INTENT_DETECTED, {"intent": "weather.current", "raw": "오늘 날씨 어때?"}),
    ("6", "사진 인텐트 (intent: photo)", Topics.VOICE_INTENT_DETECTED, {"intent": "camera.capture", "raw": "사진 찍어"}),
    ("7", "스마트홈 인텐트 (intent: smarthome)", Topics.VOICE_INTENT_DETECTED, {"intent": "smarthome.light.on", "raw": "불 꺼줘", "device": "light", "action": "off"}),
    ("8", "타이머 인텐트 (intent: timer)", Topics.VOICE_INTENT_DETECTED, {"intent": "timer.create", "raw": "3분 타이머", "seconds": 180}),
    ("9", "게임 인텐트 (intent: game)", Topics.VOICE_INTENT_DETECTED, {"intent": "ui.game_mode.enter", "raw": "게임하자"}),
    ("10", "댄스 인텐트 (intent: dance)", Topics.VOICE_INTENT_DETECTED, {"intent": "dance.start", "raw": "춤 춰"}),
    ("11", "알 수 없는 인텐트 (unknown)", Topics.VOICE_INTENT_UNKNOWN, {"raw": "알아듣지 못함"}),
    ("12", "태스크 성공 (task succeeded)", Topics.TASK_SUCCEEDED, {"kind": "weather"}),
    ("13", "태스크 실패 (task failed)", Topics.TASK_FAILED, {"kind": "weather", "error": "timeout"}),
    ("14", "터치 탭 (tap)", Topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
    ("15", "터치 쓰다듬기 (stroke)", Topics.TOUCH_STROKE_DETECTED, {"direction": "left_right"}),
    ("16", "제스처 V사인 (gesture v_sign)", Topics.VISION_GESTURE_DETECTED, {"gesture": "v_sign"}),
    ("17", "타이머 만료 (timer expired)", Topics.TIMER_EXPIRED, {"timer_id": "demo_timer", "label": "3분 타이머"}),
    ("18", "얼굴 이동 (face moved)", Topics.VISION_FACE_MOVED, {"x": 0.7, "y": 0.3}),
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
    """상태에 따라 다른 색을 입혀 반환."""
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


def print_state(store: Store, mood: Mood, ui: UILayout):
    """현재 상태를 보기 좋게 출력."""
    os_str = f"{C.MAGENTA}{store.active_oneshot.name.value}{C.RESET}" if store.active_oneshot else "-"
    ek_str = f"{C.CYAN}{store.active_executing_kind.value}{C.RESET}" if store.active_executing_kind else "-"
    face_str = f"{C.GREEN}●{C.RESET}" if store.face_present else f"{C.RED}○{C.RESET}"

    print(f"""
┌──────────────────────────────────────────────────┐
│  {C.BOLD}RIO State{C.RESET}                                       │
├──────────────────────────────────────────────────┤
│  Context  : {color_state(store.context_state):>40s}    │
│  Activity : {color_state(store.activity_state):>40s}    │
│  ExecKind : {ek_str:>40s}    │
│  Oneshot  : {os_str:>40s}    │
│  Face     : {face_str:>40s}    │
│  Mood     : {color_mood(mood):>40s}    │
│  UI       : {C.BOLD}{ui.value:>31s}{C.RESET}    │
└──────────────────────────────────────────────────┘""")


def print_transition(result: ReducerResult):
    """전이 결과를 한 줄씩 출력."""
    if result.context_changed:
        print(f"  {C.YELLOW}▸ Context{C.RESET}  {color_state(result.prev_context)} → {color_state(result.new_context)}")
    if result.activity_changed:
        kind = f" ({result.new_executing_kind.value})" if result.new_executing_kind else ""
        print(f"  {C.YELLOW}▸ Activity{C.RESET} {color_state(result.prev_activity)} → {color_state(result.new_activity)}{kind}")
    if result.oneshot_triggered:
        print(f"  {C.MAGENTA}▸ Oneshot{C.RESET}  {result.oneshot_triggered.value} 트리거됨!")
    if result.oneshot_expired:
        print(f"  {C.DIM}▸ Oneshot{C.RESET}  {result.oneshot_expired.value} 만료됨")
    if not result.context_changed and not result.activity_changed and not result.oneshot_triggered:
        print(f"  {C.DIM}(변화 없음){C.RESET}")


def print_menu():
    """이벤트 선택 메뉴."""
    print(f"\n{C.BOLD}── 이벤트 주입 ─────────────────────────────────────{C.RESET}")
    for key, label, _, _ in EVENTS:
        print(f"  {C.CYAN}{key:>2}{C.RESET}. {label}")
    print(f"  {C.CYAN} s{C.RESET}. 시나리오 자동 재생 (전체 상태 순회)")
    print(f"  {C.CYAN} r{C.RESET}. 상태 리셋")
    print(f"  {C.CYAN} q{C.RESET}. 종료")
    print(f"{C.BOLD}───────────────────────────────────────────────────{C.RESET}")


def make_event(topic: str, payload: dict) -> Event:
    return Event(topic=topic, source="demo/forced", payload=payload, timestamp=time.time())


def run_scenario(store: Store, config: dict):
    """주요 상태를 전부 순회하는 시나리오 자동 재생."""
    steps = [
        ("🔵 1. Away → Idle (얼굴 감지)", Topics.VISION_FACE_DETECTED, {"x": 0.5, "y": 0.5, "size": 0.3}),
        ("🔵 2. Idle → Engaged (터치 + 얼굴)", Topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
        ("🔵 3. Idle → Listening (음성 시작)", Topics.VOICE_ACTIVITY_STARTED, {}),
        ("🔵 4. Listening → Executing/weather (날씨 인텐트)", Topics.VOICE_INTENT_DETECTED, {"intent": "weather.current", "raw": "날씨"}),
        ("🔵 5. Executing → Idle (태스크 성공)", Topics.TASK_SUCCEEDED, {"kind": "weather"}),
        ("🔵 6. Idle → Listening (음성 시작)", Topics.VOICE_ACTIVITY_STARTED, {}),
        ("🔵 7. Listening → Executing/photo (사진 인텐트)", Topics.VOICE_INTENT_DETECTED, {"intent": "camera.capture", "raw": "사진"}),
        ("🔵 8. Executing → Idle (태스크 성공)", Topics.TASK_SUCCEEDED, {"kind": "photo"}),
        ("🔵 9. Idle → Alerting (타이머 만료)", Topics.TIMER_EXPIRED, {"timer_id": "t1", "label": "타이머"}),
        ("🔵 10. Alerting → Idle (터치 확인)", Topics.TOUCH_TAP_DETECTED, {"x": 0.5, "y": 0.5}),
        ("🔵 11. 얼굴 사라짐", Topics.VISION_FACE_LOST, {}),
        ("🔵 12. 다시 음성 (startled oneshot 확인)", Topics.VOICE_ACTIVITY_STARTED, {}),
    ]

    print(f"\n{C.BOLD}{C.YELLOW}═══ 시나리오 자동 재생 시작 ═══{C.RESET}\n")

    for label, topic, payload in steps:
        print(f"\n{C.BOLD}{label}{C.RESET}")
        print(f"  {C.DIM}topic: {topic}{C.RESET}")
        evt = make_event(topic, payload)
        result = reduce(store, evt, config)
        print_transition(result)
        print_state(store, result.mood, result.ui)
        time.sleep(0.3)

    print(f"\n{C.BOLD}{C.GREEN}═══ 시나리오 완료 ═══{C.RESET}\n")


def main():
    store = Store()
    config = DEFAULT_CONFIG
    # 초기 scene
    from src.app.core.state.scene_selector import derive_scene
    mood, ui = derive_scene(store.context_state, store.activity_state, store.active_oneshot, store.active_executing_kind)

    print(f"\n{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}║          RIO 상태 머신 인터랙티브 데모           ║{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}╚══════════════════════════════════════════════════╝{C.RESET}")

    print_state(store, mood, ui)

    while True:
        print_menu()
        choice = input(f"  {C.BOLD}선택> {C.RESET}").strip().lower()

        if choice == "q":
            print(f"\n{C.DIM}종료합니다.{C.RESET}")
            break
        elif choice == "r":
            store = Store()
            mood, ui = derive_scene(store.context_state, store.activity_state, store.active_oneshot, store.active_executing_kind)
            print(f"\n{C.GREEN}상태 리셋 완료{C.RESET}")
            print_state(store, mood, ui)
            continue
        elif choice == "s":
            store = Store()
            run_scenario(store, config)
            mood, ui = derive_scene(store.context_state, store.activity_state, store.active_oneshot, store.active_executing_kind)
            continue

        matched = None
        for key, label, topic, payload in EVENTS:
            if choice == key:
                matched = (label, topic, payload)
                break

        if not matched:
            print(f"{C.RED}잘못된 입력입니다.{C.RESET}")
            continue

        label, topic, payload = matched
        print(f"\n  {C.BOLD}주입:{C.RESET} {label}")
        print(f"  {C.DIM}topic: {topic}{C.RESET}")

        evt = make_event(topic, payload)
        result = reduce(store, evt, config)
        print_transition(result)
        print_state(store, result.mood, result.ui)


if __name__ == "__main__":
    main()
